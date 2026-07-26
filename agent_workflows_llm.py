# agent_workflows_llm.py - LLM-powered agent
import os
import re
import json
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pymongo import MongoClient
from rag_system import rag_system

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Try to import LLM libraries
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("OpenAI not installed. Run: pip install openai")

try:
    import google.generativeai as genai
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    print("Google Gemini not installed. Run: pip install google-generativeai")

class VisionDeskLLMAgent:
    """LLM-powered agent with real-time database access"""
    
    def __init__(self, provider='openai'):
        self.provider = provider
        
        # Initialize LLM client
        self.llm_client = None
        self.model_name = None
        
        if provider == 'openai' and OPENAI_AVAILABLE:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.llm_client = OpenAI(api_key=api_key)
                self.model_name = 'gpt-4o-mini'  # or 'gpt-4'
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
        
        # Connect to MongoDB
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['visiondesk_db']
        self.records_col = self.db['visual_records']
        self.documents_col = self.db['documents']
        self.incidents_col = self.db['incidents']
        self.knowledge_col = self.db['knowledge_repository']
    
    def process_query(self, query: str, user: str) -> Dict[str, Any]:
        """Process user query with LLM"""
        
        query_lower = query.lower().strip()
        tool_results = []
        incident_data = None
        
        # ============================================
        # COLLECT REAL-TIME DATA
        # ============================================
        
        # Get relevant data based on query
        context_data = self._gather_context(query_lower)
        
        # ============================================
        # GENERATE RESPONSE USING LLM
        # ============================================
        
        if self.llm_client and self.provider == 'openai':
            response = self._generate_openai_response(query, context_data)
        elif self.llm_client and self.provider == 'google':
            response = self._generate_google_response(query, context_data)
        else:
            # Fallback to rule-based agent
            from agent_workflows import visiondesk_agent
            return visiondesk_agent.process_query(query, user)
        
        # ============================================
        # LOG INCIDENT IF NEEDED
        # ============================================
        
        if any(kw in query_lower for kw in ['violation', 'incident', 'accident', 'hazard']):
            incident_data = {
                'timestamp': datetime.now().isoformat(),
                'query': query,
                'severity': 'high',
                'status': 'reported',
                'user': user
            }
            
            zone_match = re.search(r'zone\s*([a-z0-9]+)', query_lower, re.IGNORECASE)
            if zone_match:
                incident_data['zone'] = zone_match.group(1).upper()
            
            try:
                result = self.incidents_col.insert_one(incident_data)
                incident_data['_id'] = str(result.inserted_id)
                tool_results.append({'type': 'incident_logged', 'incident_id': str(result.inserted_id)})
            except Exception as e:
                tool_results.append({'type': 'incident_error', 'error': str(e)})
        
        return {
            'query': query,
            'response': response,
            'reasoning': f"Generated using {self.provider} ({self.model_name})",
            'action': self._detect_action(query),
            'workflow_status': 'completed',
            'incident_data': incident_data,
            'tool_results': tool_results
        }
    
    def _gather_context(self, query: str) -> Dict[str, Any]:
        """Gather relevant context from database"""
        context = {
            'query': query,
            'general_stats': {},
            'ppe_stats': {},
            'recent_violations': [],
            'documents': [],
            'zone_data': {},
            'recent_audits': []
        }
        
        # Get general stats
        context['general_stats'] = self._get_general_stats()
        
        # Get PPE stats if relevant
        if any(kw in query for kw in ['ppe', 'helmet', 'vest', 'mask', 'compliance']):
            context['ppe_stats'] = self._get_ppe_compliance_stats()
        
        # Get recent violations
        if any(kw in query for kw in ['violation', 'incident', 'alert', 'hazard']):
            context['recent_violations'] = self._get_latest_violations(limit=10)
        
        # Get zone data if mentioned
        zone_match = re.search(r'zone\s*([a-z0-9]+)', query, re.IGNORECASE)
        if zone_match:
            zone = zone_match.group(1).upper()
            context['zone_data'] = {
                'zone': zone,
                'data': self._get_zone_data(zone),
                'violations': self._get_zone_violations(zone)
            }
        
        # Get documents if relevant
        if any(kw in query for kw in ['manual', 'policy', 'document', 'procedure', 'guideline']):
            context['documents'] = self._search_documents(query, limit=5)
        
        # Get recent audits
        context['recent_audits'] = list(self.records_col.find({}).sort('upload_date', -1).limit(5))
        
        return context
    
    def _generate_openai_response(self, query: str, context: Dict) -> str:
        """Generate response using OpenAI"""
        
        # Create system prompt
        system_prompt = """You are VisionDesk AI, a workplace safety assistant for a construction/industrial site.

You have access to real-time safety data:
- Visual inspection records (PPE detection, violations)
- Safety documents (manuals, policies, procedures)
- Incident logs
- Zone-specific safety data

Your responses should be:
1. Professional and clear
2. Data-driven (use the provided context)
3. Actionable (provide recommendations)
4. Well-formatted with emojis and sections

Always provide specific numbers and details from the data."""
        
        # Format context for the prompt
        context_str = self._format_context_for_llm(context)
        
        # Create user prompt
        user_prompt = f"""
User Query: {query}

Available Context Data:
{context_str}

Please provide a comprehensive, helpful response to the user's query about workplace safety.
"""
        
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI Error: {e}")
            return f"I encountered an error while generating a response. Please try again. (Error: {str(e)[:100]})"
    
    def _generate_google_response(self, query: str, context: Dict) -> str:
        """Generate response using Google Gemini"""
        
        system_prompt = """You are VisionDesk AI, a workplace safety assistant.
Use the provided data to give accurate, helpful responses about safety compliance, PPE, and incidents."""
        
        context_str = self._format_context_for_llm(context)
        
        prompt = f"""
{system_prompt}

User Query: {query}

Safety Data:
{context_str}

Please respond to the user's query about workplace safety.
"""
        
        try:
            response = self.llm_client.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Google Gemini Error: {e}")
            return f"Error generating response: {str(e)[:100]}"
    
    def _format_context_for_llm(self, context: Dict) -> str:
        """Format context data for LLM prompt"""
        parts = []
        
        # General stats
        stats = context.get('general_stats', {})
        if stats:
            parts.append(f"📊 Total Audits: {stats.get('total_audits', 0)}")
            parts.append(f"⚠️ Violations: {stats.get('violations', 0)}")
            parts.append(f"✅ Safe: {stats.get('safe', 0)}")
            parts.append(f"📈 Compliance: {stats.get('compliance_rate', 0)}%")
            parts.append(f"📄 Documents: {stats.get('documents', 0)}")
        
        # PPE stats
        ppe = context.get('ppe_stats', {})
        if ppe and ppe.get('total_workers', 0) > 0:
            parts.append(f"\n🛡️ PPE Stats:")
            parts.append(f"👷 Workers: {ppe.get('total_workers', 0)}")
            parts.append(f"⛑️ Helmets: {ppe.get('helmets', 0)} ({ppe.get('helmet_compliance', 0)}%)")
            parts.append(f"🦺 Vests: {ppe.get('vests', 0)} ({ppe.get('vest_compliance', 0)}%)")
            parts.append(f"😷 Masks: {ppe.get('masks', 0)} ({ppe.get('mask_compliance', 0)}%)")
        
        # Violations
        violations = context.get('recent_violations', [])
        if violations:
            parts.append(f"\n🚨 Recent Violations: {len(violations)}")
            for v in violations[:3]:
                parts.append(f"  - {v.get('file_name', 'Unknown')}: {', '.join(v.get('violations', []))}")
        
        # Zone data
        zone_data = context.get('zone_data', {})
        if zone_data and zone_data.get('data'):
            zone = zone_data.get('zone', 'Unknown')
            data = zone_data.get('data', {})
            parts.append(f"\n📍 Zone {zone}:")
            parts.append(f"  Total: {data.get('total', 0)}")
            parts.append(f"  Violations: {data.get('violations', 0)}")
            parts.append(f"  Compliance: {data.get('compliance_rate', 0)}%")
        
        # Documents
        docs = context.get('documents', [])
        if docs:
            parts.append(f"\n📖 Found Documents: {len(docs)}")
            for doc in docs[:3]:
                parts.append(f"  - {doc.get('filename', 'Unknown')}")
        
        return "\n".join(parts)
    
    # ============================================
    # DATABASE QUERY METHODS
    # ============================================
    
    def _get_general_stats(self):
        try:
            total_audits = self.records_col.count_documents({})
            violations = self.records_col.count_documents({'status': 'VIOLATION DETECTED'})
            safe = total_audits - violations
            documents = self.documents_col.count_documents({})
            
            return {
                'total_audits': total_audits,
                'violations': violations,
                'safe': safe,
                'compliance_rate': round((safe / total_audits * 100)) if total_audits > 0 else 100,
                'documents': documents
            }
        except Exception as e:
            print(f"Error getting general stats: {e}")
            return {}
    
    def _get_ppe_compliance_stats(self):
        try:
            records = list(self.records_col.find({}).sort('upload_date', -1).limit(100))
            
            total_workers = 0
            total_helmets = 0
            total_vests = 0
            total_masks = 0
            
            for record in records:
                summary = record.get('summary', {})
                total_workers += summary.get('workers', 0)
                total_helmets += summary.get('helmets', 0)
                total_vests += summary.get('vests', 0)
                total_masks += summary.get('masks', 0)
            
            helmet_comp = round((total_helmets / total_workers * 100)) if total_workers > 0 else 100
            vest_comp = round((total_vests / total_workers * 100)) if total_workers > 0 else 100
            mask_comp = round((total_masks / total_workers * 100)) if total_workers > 0 else 100
            
            return {
                'total_workers': total_workers,
                'helmets': total_helmets,
                'vests': total_vests,
                'masks': total_masks,
                'helmet_compliance': helmet_comp,
                'vest_compliance': vest_comp,
                'mask_compliance': mask_comp
            }
        except Exception as e:
            print(f"Error getting PPE stats: {e}")
            return {}
    
    def _get_latest_violations(self, limit=10):
        try:
            records = list(self.records_col.find({
                'status': 'VIOLATION DETECTED'
            }).sort('upload_date', -1).limit(limit))
            return records
        except Exception as e:
            print(f"Error getting violations: {e}")
            return []
    
    def _get_zone_data(self, zone):
        try:
            records = list(self.records_col.find({
                'file_name': {'$regex': f'zone[_\s]*{zone}', '$options': 'i'}
            }))
            
            total = len(records)
            violations = sum(1 for r in records if r.get('status') == 'VIOLATION DETECTED')
            safe = total - violations
            compliance_rate = round((safe / total * 100)) if total > 0 else 100
            
            return {
                'total': total,
                'violations': violations,
                'safe': safe,
                'compliance_rate': compliance_rate
            }
        except Exception as e:
            print(f"Error getting zone data: {e}")
            return {}
    
    def _get_zone_violations(self, zone):
        try:
            records = list(self.records_col.find({
                'file_name': {'$regex': f'zone[_\s]*{zone}', '$options': 'i'},
                'status': 'VIOLATION DETECTED'
            }).sort('upload_date', -1).limit(10))
            return records
        except Exception as e:
            print(f"Error getting zone violations: {e}")
            return []
    
    def _search_documents(self, query, limit=5):
        try:
            # Remove common words
            search_terms = re.sub(r'(safety|manual|policy|procedure|guideline|document|show|find|search|for|the|and|or|of|to|in|on|at)', '', query)
            search_terms = search_terms.strip()
            
            if not search_terms or len(search_terms) < 3:
                docs = list(self.documents_col.find({}).sort('upload_date', -1).limit(limit))
                return docs
            
            docs = list(self.documents_col.find({
                '$or': [
                    {'filename': {'$regex': search_terms, '$options': 'i'}},
                    {'knowledge_entry.full_text': {'$regex': search_terms, '$options': 'i'}}
                ]
            }).limit(limit))
            
            return docs if docs else list(self.documents_col.find({}).sort('upload_date', -1).limit(3))
        except Exception as e:
            print(f"Error searching documents: {e}")
            return []
    
    def _detect_action(self, query):
        query_lower = query.lower()
        if 'zone' in query_lower:
            return 'zone_investigation'
        elif any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask']):
            return 'ppe_compliance'
        elif any(kw in query_lower for kw in ['manual', 'policy', 'procedure', 'guideline']):
            return 'document_retrieval'
        elif any(kw in query_lower for kw in ['violation', 'incident', 'alert', 'hazard']):
            return 'recent_violations'
        else:
            return 'general_query'

# Create singleton
visiondesk_agent = VisionDeskLLMAgent(provider='openai')  # or 'google'