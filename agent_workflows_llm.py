# agent_workflows_llm.py
# Real LLM-powered, RAG-grounded, app-aware agent with fast local fallbacks.

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
                self.llm_client = OpenAI(api_key=api_key, timeout=7.0)
                self.model_name = 'gpt-4o-mini'
                print("✅ OpenAI initialized")
            else:
                print("⚠️ OPENAI_API_KEY not found in .env file")
        elif provider == 'google' and GOOGLE_AVAILABLE:
            api_key = os.getenv('GOOGLE_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.llm_client = genai.GenerativeModel('gemini-1.5-flash')
                self.model_name = 'gemini-1.5-flash'
                print("✅ Google Gemini initialized")
            else:
                print("⚠️ GOOGLE_API_KEY not found in .env file")

        try:
            self.client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
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
        action = self._detect_action(query_lower)

        # Fast direct responses for greetings
        if query_lower in ('hi', 'hello', 'hey', 'hii', 'hola', 'good morning', 'good afternoon', 'good evening'):
            return {
                'response': f"Hi {username}! I'm VisionDesk AI. I can help with PPE compliance, recent violations, specific zones, uploaded documents, or general safety workflows. What would you like to check?",
                'query': query,
                'action': 'greeting',
                'tool_results': [{'type': 'greeting', 'status': 'success'}]
            }

        context = self._gather_context(query_lower, username)
        response_text = self._generate_response(query, context)

        if any(kw in query_lower for kw in ['violation', 'incident', 'hazard']) and self.incidents_col is not None:
            try:
                self.incidents_col.insert_one({
                    'timestamp': datetime.now().isoformat(),
                    'query': query,
                    'user': username,
                    'status': 'reported'
                })
            except Exception:
                pass

        return {
            'response': response_text,
            'query': query,
            'action': action,
            'tool_results': [{'type': 'llm_grounded', 'status': 'success'}]
        }

    def _gather_context(self, query_lower, username):
        context = {
            'rag_results': [], 'ppe_stats': {}, 'zone_data': {}, 'violations': [],
            'dashboard_stats': {}, 'document_list': []
        }

        try:
            context['rag_results'] = rag_system.search(query_lower, top_k=3)
            print(f"📚 RAG retrieved {len(context['rag_results'])} relevant chunks")
        except Exception as e:
            print(f"⚠️ RAG search failed: {e}")

        if self.records_col is None:
            return context

        # 1. PPE Stats
        if any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask', 'compliance']):
            try:
                records = list(self.records_col.find({'uploaded_by': username}).sort('_id', -1).limit(100))
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

        # 2. Zone Lookup
        zone_match = re.search(r'zone\s*([a-z0-9]+)', query_lower, re.IGNORECASE)
        if zone_match:
            zone = zone_match.group(1).upper()
            try:
                records = list(self.records_col.find({
                    'uploaded_by': username,
                    'file_name': {'$regex': f'zone[_ ]*{zone}', '$options': 'i'}
                }))
                total = len(records)
                violations = sum(1 for r in records if r.get('status') == 'VIOLATION DETECTED')
                context['zone_data'] = {'zone': zone, 'total': total, 'violations': violations}
            except Exception as e:
                print(f"⚠️ Zone lookup failed: {e}")

        # 3. Violations Lookup
        if any(kw in query_lower for kw in ['violation', 'incident', 'alert', 'hazard', 'recent']):
            try:
                records = list(self.records_col.find({
                    'uploaded_by': username,
                    'status': 'VIOLATION DETECTED'
                }).sort('_id', -1).limit(5))
                context['violations'] = records
            except Exception as e:
                print(f"⚠️ Violations lookup failed: {e}")

        # 4. Dashboard Stats
        if any(kw in query_lower for kw in ['dashboard', 'overview', 'summary', 'site status', 'general stats']):
            try:
                total = self.records_col.count_documents({'uploaded_by': username})
                violations = self.records_col.count_documents({'uploaded_by': username, 'status': 'VIOLATION DETECTED'})
                safe = total - violations
                compliance_pct = round(safe / total * 100) if total else 100
                context['dashboard_stats'] = {
                    'total': total, 'safe': safe, 'violations': violations,
                    'compliance_pct': compliance_pct,
                    'status': 'Critical' if compliance_pct < 70 else 'Good'
                }
            except Exception as e:
                print(f"⚠️ Dashboard stats lookup failed: {e}")

        # 5. Document List
        if self.documents_col is not None and any(kw in query_lower for kw in ['document', 'documents', 'manual']):
            try:
                docs = list(self.documents_col.find({'uploaded_by': username}).sort('_id', -1).limit(10))
                context['document_list'] = [
                    {'filename': d.get('filename', 'Unknown'), 'upload_date': str(d.get('upload_date', ''))}
                    for d in docs
                ]
            except Exception as e:
                print(f"⚠️ Document list lookup failed: {e}")

        return context

    def _fallback_summary(self, query_lower, context):
        """Generates instant, accurate data responses if LLM fails or is unconfigured."""
        
        # 1. Dashboard / Overview Stats
        dash = context.get('dashboard_stats', {})
        if dash and any(kw in query_lower for kw in ['dashboard', 'overview', 'summary', 'status', 'stats', 'how are we doing']):
            return (
                f"📊 **Dashboard Overview:**\n"
                f"• Total Audits: **{dash.get('total', 0)}**\n"
                f"• Safe Records: **{dash.get('safe', 0)}**\n"
                f"• Violations Flagged: **{dash.get('violations', 0)}**\n"
                f"• Compliance Rate: **{dash.get('compliance_pct', 0)}%**\n"
                f"• Site Health Status: **{dash.get('status', 'Good')}**"
            )

        # 2. Recent Violations
        violations = context.get('violations', [])
        if any(kw in query_lower for kw in ['violation', 'violations', 'recent', 'alert']) and violations:
            items = []
            for v in violations:
                issues = ', '.join(v.get('violations', [])) or 'Safety non-compliance'
                items.append(f"• **{v.get('file_name', 'Audit Image')}**: {issues}")
            return f"🚨 Found **{len(violations)} recent violation(s)** for your account:\n" + "\n".join(items)

        # 3. PPE Breakdown
        ppe = context.get('ppe_stats', {})
        if ppe and any(kw in query_lower for kw in ['ppe', 'compliance', 'helmet', 'vest', 'mask']):
            return (
                f"🛡️ **PPE Compliance Breakdown:**\n"
                f"• Total Workers Tracked: **{ppe.get('workers', 0)}**\n"
                f"• Hard Hat / Helmet: **{ppe.get('helmets', 0)}** ({ppe.get('helmet_pct', 0)}%)\n"
                f"• Hi-Vis Vest: **{ppe.get('vests', 0)}** ({ppe.get('vest_pct', 0)}%)\n"
                f"• Face Masks: **{ppe.get('masks', 0)}** ({ppe.get('mask_pct', 0)}%)"
            )

        # 4. Zone Investigation
        zone = context.get('zone_data', {})
        if zone:
            return f"📍 **Zone {zone.get('zone')} Status:** {zone.get('total', 0)} total audits registered with {zone.get('violations', 0)} violations flagged."

        # 5. Documents / Knowledge Excerpts
        rag = context.get('rag_results', [])
        if rag:
            excerpts = [f"• From *{r.get('metadata', {}).get('filename', 'Document')}*: {r.get('text', '')[:200]}..." for r in rag[:2]]
            return "📖 **Relevant Document Findings:**\n" + "\n".join(excerpts)

        # 6. Document List
        doc_list = context.get('document_list', [])
        if doc_list and any(kw in query_lower for kw in ['document', 'documents', 'manual', 'files']):
            items = [f"• {d.get('filename')}" for d in doc_list]
            return f"📄 **Uploaded Documents ({len(doc_list)}):**\n" + "\n".join(items)

        # 7. General App Information
        if any(kw in query_lower for kw in ['what is', 'how does', 'help', 'features', 'app', 'visiondesk']):
            return (
                "**VisionDesk AI Overview:**\n"
                "VisionDesk AI is an intelligent workplace safety system. It detects workers and PPE (helmets, vests, masks) using computer vision, audits compliance against safety guidelines via document RAG, and generates real-time safety metrics and PDF reports."
            )

        return "No specific records or document excerpts matched your query. You can ask about **recent violations**, **PPE compliance**, **dashboard stats**, or upload safety documents to search."

    def _generate_response(self, query, context):
        query_lower = query.lower()
        context_str = self._format_context(context)

        if not self.llm_client:
            return self._fallback_summary(query_lower, context)

        prompt = f"""You are VisionDesk AI, a workplace safety assistant embedded inside the VisionDesk app. Answer directly and concisely.

ABOUT THIS APP:
{APP_DESCRIPTION}

RULES:
- No markdown titles (#, ##) or divider lines (===).
- 2-5 clear sentences or bullet points.
- Use the retrieved data below if relevant. If no data exists, answer based on the app info or safety standards.

User question: {query}

Data retrieved:
{context_str}"""

        try:
            if self.provider == 'openai':
                response = self.llm_client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=300
                )
                text = response.choices[0].message.content
            else:
                response = self.llm_client.generate_content(
                    prompt,
                    request_options={'timeout': 6.0}
                )
                text = response.text

            text = re.sub(r'^=+$', '', text, flags=re.MULTILINE)
            text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
            return re.sub(r'\n{3,}', '\n\n', text).strip()

        except Exception as e:
            print(f"⚠️ LLM Call timed out/failed ({e}), falling back to direct context summary.")
            return self._fallback_summary(query_lower, context)

    def _format_context(self, context):
        parts = []
        rag_results = context.get('rag_results', [])
        if rag_results:
            parts.append("Knowledge Base Excerpts:")
            for i, r in enumerate(rag_results, 1):
                filename = r.get('metadata', {}).get('filename', 'Document')
                parts.append(f"[{i}] {filename}: {r.get('text', '')[:300]}")

        ppe = context.get('ppe_stats', {})
        if ppe:
            parts.append(f"\nPPE Compliance: Workers={ppe.get('workers', 0)}, Helmets={ppe.get('helmets', 0)} ({ppe.get('helmet_pct', 0)}%), Vests={ppe.get('vests', 0)} ({ppe.get('vest_pct', 0)}%)")

        dash = context.get('dashboard_stats', {})
        if dash:
            parts.append(f"\nDashboard: Total={dash.get('total', 0)}, Safe={dash.get('safe', 0)}, Violations={dash.get('violations', 0)}, Compliance={dash.get('compliance_pct', 0)}%")

        zone = context.get('zone_data', {})
        if zone:
            parts.append(f"\nZone {zone.get('zone')}: {zone.get('total', 0)} audits, {zone.get('violations', 0)} violations")

        violations = context.get('violations', [])
        if violations:
            parts.append(f"\nRecent Violations ({len(violations)}):")
            for v in violations[:5]:
                parts.append(f" - {v.get('file_name', 'Audit')}: {', '.join(v.get('violations', []))}")

        return "\n".join(parts) if parts else "No specific data matched this query."

    def _detect_action(self, query_lower):
        if 'zone' in query_lower:
            return 'zone_investigation'
        elif any(kw in query_lower for kw in ['dashboard', 'overview', 'summary']):
            return 'dashboard_overview'
        elif any(kw in query_lower for kw in ['document', 'documents', 'manual']):
            return 'document_retrieval'
        elif any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask', 'compliance']):
            return 'ppe_compliance'
        elif any(kw in query_lower for kw in ['violation', 'incident', 'alert', 'hazard', 'recent']):
            return 'recent_violations'
        return 'general_query'


visiondesk_agent = VisionDeskLLMAgent(provider='google')