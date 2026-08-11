# agent_workflows_llm.py
# Real LLM-powered, RAG-grounded, app-aware agent. No templates, no "====" dividers.

import os
import re
from datetime import datetime
from pymongo import MongoClient

from rag_system import rag_system

from dotenv import load_dotenv
load_dotenv()

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import google.generativeai as genai
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


# Static primer describing the app itself, so questions like "what is this project",
# "what can you do", "what is history/settings/export for" always get a correct answer
# even when no specific keyword/data trigger matches.
APP_DESCRIPTION = """VisionDesk AI is a workplace safety intelligence platform with these features:
- Dashboard: live overview of total audits, violations, safe records, and overall compliance rate.
- Upload Media: upload site photos/video; a YOLO computer-vision model automatically detects workers and PPE (helmets, vests, masks) and flags violations.
- Documents: upload safety manuals/PDFs; the system extracts and indexes their text for search.
- Search Knowledge: keyword/full-text search across uploaded documents.
- AI Chat (this assistant): ask natural-language questions; answers are grounded in live compliance data and the uploaded documents (RAG).
- Export Reports: generate PDF compliance/safety reports.
- History: past uploaded media and their detection results.
- Settings: account and app configuration."""


class VisionDeskLLMAgent:
    def __init__(self, provider='google'):
        self.provider = provider
        self.llm_client = None
        self.model_name = None

        if provider == 'openai' and OPENAI_AVAILABLE:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.llm_client = OpenAI(api_key=api_key)
                self.model_name = 'gpt-4o-mini'
                print("✅ OpenAI initialized")
            else:
                print("⚠️ OPENAI_API_KEY not found in .env file")
        elif provider == 'google' and GOOGLE_AVAILABLE:
            api_key = os.getenv('GOOGLE_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.llm_client = genai.GenerativeModel('gemini-flash-latest')
                self.model_name = 'gemini-flash-latest'
                print("✅ Google Gemini initialized")
            else:
                print("⚠️ GOOGLE_API_KEY not found in .env file")

        try:
            self.client = MongoClient('mongodb://localhost:27017/')
            self.db = self.client['visiondesk_db']
            self.records_col = self.db['visual_records']
            self.documents_col = self.db['documents']
            self.incidents_col = self.db['incidents']
            print("✅ Agent connected to MongoDB")
        except Exception as e:
            print(f"⚠️ Agent database connection failed: {e}")
            self.records_col = None
            self.documents_col = None
            self.incidents_col = None

    def process_query(self, query, username):
        if not query or not query.strip():
            return {'response': "Please enter a valid question.", 'query': query, 'action': 'error', 'tool_results': []}

        query_lower = query.lower().strip()

        if query_lower in ('hi', 'hello', 'hey', 'hii', 'hola', 'good morning', 'good afternoon', 'good evening'):
            return {
                'response': f"Hi {username}! I'm VisionDesk AI. I can help with PPE compliance, recent violations, specific zones, uploaded documents, or general questions about how this app works. What would you like to know?",
                'query': query,
                'action': 'greeting',
                'tool_results': [{'type': 'greeting', 'status': 'success'}]
            }

        context = self._gather_context(query_lower)
        response_text = self._generate_response(query, context)
        action = self._detect_action(query_lower)

        if any(kw in query_lower for kw in ['violation', 'incident', 'hazard']) and self.incidents_col is not None:
            try:
                self.incidents_col.insert_one({
                    'timestamp': datetime.now().isoformat(),
                    'query': query, 'user': username, 'status': 'reported'
                })
            except Exception:
                pass

        return {
            'response': response_text,
            'query': query,
            'action': action,
            'tool_results': [{'type': 'llm_grounded', 'status': 'success'}]
        }

    def _gather_context(self, query_lower):
        context = {'rag_results': [], 'ppe_stats': {}, 'zone_data': {}, 'violations': [],
                   'dashboard_stats': {}, 'document_list': []}

        try:
            context['rag_results'] = rag_system.search(query_lower, top_k=4)
            print(f"📚 RAG retrieved {len(context['rag_results'])} relevant chunks")
        except Exception as e:
            print(f"⚠️ RAG search failed: {e}")

        if self.records_col is None:
            return context

        if any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask', 'compliance']):
            try:
                records = list(self.records_col.find({}).sort('upload_date', -1).limit(100))
                workers = sum(r.get('summary', {}).get('workers', 0) for r in records)
                helmets = sum(r.get('summary', {}).get('helmets', 0) for r in records)
                vests = sum(r.get('summary', {}).get('vests', 0) for r in records)
                masks = sum(r.get('summary', {}).get('masks', 0) for r in records)
                context['ppe_stats'] = {
                    'workers': workers, 'helmets': helmets, 'vests': vests, 'masks': masks,
                    'helmet_pct': round(helmets / workers * 100) if workers else 0,
                    'vest_pct': round(vests / workers * 100) if workers else 0,
                    'mask_pct': round(masks / workers * 100) if workers else 0,
                }
            except Exception as e:
                print(f"⚠️ PPE stats failed: {e}")

        zone_match = re.search(r'zone\s*([a-z0-9]+)', query_lower, re.IGNORECASE)
        if zone_match:
            zone = zone_match.group(1).upper()
            try:
                records = list(self.records_col.find({'file_name': {'$regex': f'zone[_ ]*{zone}', '$options': 'i'}}))
                total = len(records)
                violations = sum(1 for r in records if r.get('status') == 'VIOLATION DETECTED')
                context['zone_data'] = {'zone': zone, 'total': total, 'violations': violations}
            except Exception as e:
                print(f"⚠️ Zone lookup failed: {e}")

        if any(kw in query_lower for kw in ['violation', 'incident', 'alert', 'hazard', 'recent']):
            try:
                records = list(self.records_col.find({'status': 'VIOLATION DETECTED'}).sort('upload_date', -1).limit(5))
                context['violations'] = records
            except Exception as e:
                print(f"⚠️ Violations lookup failed: {e}")

        if any(kw in query_lower for kw in ['dashboard', 'overview', 'summary', 'site status', 'how are we doing', 'general stats']):
            try:
                total = self.records_col.count_documents({})
                violations = self.records_col.count_documents({'status': 'VIOLATION DETECTED'})
                safe = total - violations
                compliance_pct = round(safe / total * 100) if total else 0
                context['dashboard_stats'] = {
                    'total': total, 'safe': safe, 'violations': violations,
                    'compliance_pct': compliance_pct,
                    'status': 'Critical' if compliance_pct < 70 else 'Good'
                }
            except Exception as e:
                print(f"⚠️ Dashboard stats lookup failed: {e}")

        # Documents-list questions -- "what documents do we have", "list uploaded documents", etc.
        if self.documents_col is not None and any(kw in query_lower for kw in
                ['what documents', 'list documents', 'uploaded documents', 'how many documents',
                 'which documents', 'documents do we have', 'documents uploaded']):
            try:
                docs = list(self.documents_col.find({}).sort('upload_date', -1).limit(20))
                context['document_list'] = [
                    {'filename': d.get('filename', 'Unknown'), 'upload_date': str(d.get('upload_date', ''))}
                    for d in docs
                ]
            except Exception as e:
                print(f"⚠️ Document list lookup failed: {e}")

        return context

    def _generate_response(self, query, context):
        if not self.llm_client:
            return "⚠️ No LLM is configured. Please set OPENAI_API_KEY or GOOGLE_API_KEY in your .env file."

        context_str = self._format_context(context)

        prompt = f"""You are VisionDesk AI, a workplace safety assistant embedded inside the VisionDesk app. Answer the user's question directly and conversationally -- like a knowledgeable colleague, not a generated report.

ABOUT THIS APP (use this to answer any question about what the app/project is or does, its pages, or its features):
{APP_DESCRIPTION}

RULES:
- No "====" dividers, no markdown headers (#, ##), no "REPORT" titles.
- Plain sentences, maybe one short bullet list if it truly helps. Nothing more.
- Length: 3-6 sentences. Medium length -- not a one-liner, not an essay.
- If the question is about THIS system's specific data (compliance numbers, violations, zones, uploaded documents, dashboard stats), you MUST use only the data given below and cite the source filename if from a document. Never invent numbers. If nothing relevant was retrieved for a data question, say so honestly.
- If the question is about the app itself (what it does, what a page/feature is for), answer using the ABOUT THIS APP section above.
- If the question is a general safety knowledge question (e.g. "what is PPE"), answer helpfully from your own knowledge, concisely, and weave in any relevant retrieved excerpt if one exists.
- At most 1-2 emojis, only if they add clarity.

User question: {query}

Data retrieved for this query:
{context_str}

Now answer, following the rules exactly."""

        try:
            if self.provider == 'openai':
                response = self.llm_client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3, max_tokens=350
                )
                text = response.choices[0].message.content
            else:
                response = self.llm_client.generate_content(prompt)
                text = response.text

            text = re.sub(r'^=+$', '', text, flags=re.MULTILINE)
            text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            return text
        except Exception as e:
            error_str = str(e)
            print(f"LLM error: {e}")
            if 'quota' in error_str.lower() or '429' in error_str or 'rate' in error_str.lower():
                return "⏳ I'm getting a lot of requests right now and hit a temporary rate limit. Please wait about a minute and try again."
            return "I hit an error generating a response. Please try again."

    def _format_context(self, context):
        parts = []
        rag_results = context.get('rag_results', [])
        if rag_results:
            parts.append("Knowledge Base Excerpts:")
            for i, r in enumerate(rag_results, 1):
                filename = r.get('metadata', {}).get('filename', 'Unknown Document')
                parts.append(f"[{i}] {filename}: {r.get('text', '')[:350]}")

        ppe = context.get('ppe_stats', {})
        if ppe:
            parts.append(f"\nPPE compliance -- Workers: {ppe.get('workers', 0)}, "
                          f"Helmets: {ppe.get('helmets', 0)} ({ppe.get('helmet_pct', 0)}%), "
                          f"Vests: {ppe.get('vests', 0)} ({ppe.get('vest_pct', 0)}%), "
                          f"Masks: {ppe.get('masks', 0)} ({ppe.get('mask_pct', 0)}%)")

        dash = context.get('dashboard_stats', {})
        if dash:
            parts.append(f"\nDashboard overview -- Total records: {dash.get('total', 0)}, "
                          f"Safe: {dash.get('safe', 0)}, Violations: {dash.get('violations', 0)}, "
                          f"Overall compliance: {dash.get('compliance_pct', 0)}%, "
                          f"Site status: {dash.get('status', 'Unknown')}")

        zone = context.get('zone_data', {})
        if zone:
            parts.append(f"\nZone {zone.get('zone')}: {zone.get('total', 0)} records, {zone.get('violations', 0)} violations")

        violations = context.get('violations', [])
        if violations:
            parts.append(f"\nRecent violations ({len(violations)}):")
            for v in violations[:5]:
                parts.append(f"  - {v.get('file_name', 'Unknown')}: {', '.join(v.get('violations', []))}")

        doc_list = context.get('document_list', [])
        if doc_list:
            parts.append(f"\nUploaded documents ({len(doc_list)}):")
            for d in doc_list[:10]:
                parts.append(f"  - {d.get('filename', 'Unknown')}")

        return "\n".join(parts) if parts else "No specific data matched this query."

    def _detect_action(self, query_lower):
        if 'zone' in query_lower:
            return 'zone_investigation'
        elif any(kw in query_lower for kw in ['dashboard', 'overview', 'summary']):
            return 'dashboard_overview'
        elif any(kw in query_lower for kw in ['document', 'documents']):
            return 'document_retrieval'
        elif any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask', 'compliance']):
            return 'ppe_compliance'
        elif any(kw in query_lower for kw in ['manual', 'policy', 'procedure']):
            return 'document_retrieval'
        elif any(kw in query_lower for kw in ['violation', 'incident', 'alert', 'hazard']):
            return 'recent_violations'
        return 'general_query'


visiondesk_agent = VisionDeskLLMAgent(provider='google')