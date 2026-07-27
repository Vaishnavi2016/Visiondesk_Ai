# agent_workflows.py - NO LLM, Rule-Based Only

import re
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pymongo import MongoClient
from rag_system import rag_system

class VisionDeskAgent:
    """Rule-based agent with real-time database access - NO LLM"""
    
    def __init__(self):
        # Connect to MongoDB
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['visiondesk_db']
        self.records_col = self.db['visual_records']
        self.documents_col = self.db['documents']
        self.incidents_col = self.db['incidents']
        self.knowledge_col = self.db['knowledge_repository']
        print("✅ Agent connected to MongoDB")
    
    def process_query(self, query: str, user: str) -> Dict[str, Any]:
        """Process user query with rule-based responses"""
        
        query_lower = query.lower().strip()
        incident_data = None
        tool_results = []
        response = None
        
        print(f"📝 Processing query: {query}")
        
        # ============================================
        # GATHER DATA FROM DATABASE
        # ============================================
        
        data = self._gather_data(query_lower)
        rag_context = rag_system.get_context(query, top_k=3)
        
        # ============================================
        # GENERATE RULE-BASED RESPONSE
        # ============================================
        
        response = self._generate_rule_based_response(query_lower, data, rag_context)
        tool_results.append({'type': 'rule_based', 'status': 'success'})
        
        # ============================================
        # LOG INCIDENT IF NEEDED
        # ============================================
        
        if any(kw in query_lower for kw in ['violation', 'incident', 'accident', 'hazard']):
            incident_data = {
                'timestamp': datetime.now().isoformat(),
                'query': query,
                'severity': 'high' if 'violation' in query_lower else 'medium',
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
                print(f"✅ Incident logged: {incident_data['_id']}")
            except Exception as e:
                print(f"❌ Error logging incident: {e}")
                tool_results.append({'type': 'incident_error', 'error': str(e)})
        
        return {
            'query': query,
            'response': response,
            'action': self._detect_action(query),
            'workflow_status': 'completed',
            'incident_data': incident_data,
            'tool_results': tool_results,
            'llm_used': False
        }
    
    def _gather_data(self, query_lower: str) -> Dict[str, Any]:
        """Gather relevant data from database"""
        data = {}
        
        # General stats
        data['general_stats'] = self._get_general_stats()
        
        # PPE stats if relevant
        if any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask', 'compliance']):
            data['ppe_stats'] = self._get_ppe_compliance_stats()
        
        # Violations if relevant
        if any(kw in query_lower for kw in ['violation', 'violations', 'incident', 'hazard']):
            data['violations'] = self._get_latest_violations(limit=10)
        
        # Zone data if mentioned
        zone_match = re.search(r'zone\s*([a-z0-9]+)', query_lower, re.IGNORECASE)
        if zone_match:
            zone = zone_match.group(1).upper()
            data['zone_data'] = {
                'zone': zone,
                'data': self._get_zone_data(zone),
                'violations': self._get_zone_violations(zone)
            }
        
        # Documents if relevant
        if any(kw in query_lower for kw in ['manual', 'policy', 'procedure', 'document']):
            data['documents'] = self._search_documents(query_lower, limit=5)
        
        return data
    
    def _generate_rule_based_response(self, query_lower: str, data: Dict, context: str) -> str:
        """Generate rule-based response without LLM"""
        parts = []
        
        # Check what data we have and format accordingly
        if data.get('zone_data'):
            zone_data = data['zone_data']
            zone = zone_data.get('zone', 'Unknown')
            data_z = zone_data.get('data', {})
            
            parts.append(f"📍 **ZONE {zone} INVESTIGATION REPORT**")
            parts.append("=" * 50)
            parts.append(f"\n📊 **Total Inspections:** {data_z.get('total', 0)}")
            parts.append(f"✅ **Safe Records:** {data_z.get('safe', 0)}")
            parts.append(f"⚠️ **Violations:** {data_z.get('violations', 0)}")
            parts.append(f"📈 **Compliance Rate:** {data_z.get('compliance_rate', 0)}%")
            
            violations = zone_data.get('violations', [])
            if violations:
                parts.append(f"\n🚨 **VIOLATIONS IN ZONE {zone}:**")
                for i, v in enumerate(violations[:5], 1):
                    parts.append(f"\n{i}. 📄 **{v.get('file_name', 'Unknown')}**")
                    if v.get('violations'):
                        parts.append(f"   ❌ {', '.join(v.get('violations', []))}")
                    summary = v.get('summary', {})
                    parts.append(f"   👷 Workers: {summary.get('workers', 0)} | ⛑️ Helmets: {summary.get('helmets', 0)} | 🦺 Vests: {summary.get('vests', 0)}")
        
        elif data.get('violations'):
            violations = data['violations']
            parts.append(f"🚨 **VIOLATIONS (RECENT)**")
            parts.append("=" * 50)
            parts.append(f"\n📊 **Total Violations:** {len(violations)}\n")
            
            for i, v in enumerate(violations[:10], 1):
                parts.append(f"{i}. ⚠️ **{v.get('file_name', 'Unknown')}**")
                if v.get('violations'):
                    parts.append(f"   ❌ {', '.join(v.get('violations', []))}")
                summary = v.get('summary', {})
                parts.append(f"   👷 Workers: {summary.get('workers', 0)} | ⛑️ Helmets: {summary.get('helmets', 0)} | 🦺 Vests: {summary.get('vests', 0)}")
                parts.append("")
            
            # Summary
            total_workers = sum(v.get('summary', {}).get('workers', 0) for v in violations)
            missing_helmets = sum(max(0, v.get('summary', {}).get('workers', 0) - v.get('summary', {}).get('helmets', 0)) for v in violations)
            missing_vests = sum(max(0, v.get('summary', {}).get('workers', 0) - v.get('summary', {}).get('vests', 0)) for v in violations)
            
            parts.append("📊 **SUMMARY:**")
            parts.append(f"• Total workers affected: {total_workers}")
            if missing_helmets > 0:
                parts.append(f"• Missing helmets: {missing_helmets}")
            if missing_vests > 0:
                parts.append(f"• Missing vests: {missing_vests}")
            
            parts.append("\n📋 **RECOMMENDATIONS:**")
            parts.append("• Address violations immediately")
            parts.append("• Schedule additional safety training")
            parts.append("• Increase random inspections")
        
        elif data.get('ppe_stats'):
            ppe = data['ppe_stats']
            parts.append("🛡️ **PPE COMPLIANCE REPORT**")
            parts.append("=" * 50)
            parts.append(f"\n👷 **Total Workers Detected:** {ppe.get('total_workers', 0)}")
            parts.append(f"⛑️ **Helmets:** {ppe.get('helmets', 0)} ({ppe.get('helmet_compliance', 0)}% compliance)")
            parts.append(f"🦺 **Vests:** {ppe.get('vests', 0)} ({ppe.get('vest_compliance', 0)}% compliance)")
            parts.append(f"😷 **Masks:** {ppe.get('masks', 0)} ({ppe.get('mask_compliance', 0)}% compliance)")
            
            avg_compliance = (ppe.get('helmet_compliance', 0) + ppe.get('vest_compliance', 0) + ppe.get('mask_compliance', 0)) / 3
            parts.append(f"\n📊 **Overall Compliance Score:** {round(avg_compliance)}%")
            
            if avg_compliance < 70:
                parts.append("\n🚨 **CRITICAL:** PPE compliance is below 70%!")
                parts.append("• Immediate action required")
                parts.append("• Conduct emergency safety meeting")
            elif avg_compliance < 90:
                parts.append("\n⚠️ **WARNING:** PPE compliance is below 90%")
                parts.append("• Schedule additional safety training")
                parts.append("• Increase random inspections")
            else:
                parts.append("\n✅ **GOOD:** PPE compliance is above 90%")
                parts.append("• Maintain current safety protocols")
        
        elif data.get('documents'):
            docs = data['documents']
            parts.append("📖 **SAFETY DOCUMENTS & MANUALS**")
            parts.append("=" * 50)
            
            for doc in docs[:5]:
                parts.append(f"\n📄 **{doc.get('filename', 'Unknown Document')}**")
                knowledge = doc.get('knowledge_entry', {})
                metadata = knowledge.get('metadata', {})
                
                if metadata.get('sections'):
                    parts.append(f"📑 Sections: {', '.join(metadata.get('sections', [])[:3])}")
                if metadata.get('important_phrases'):
                    parts.append(f"🏷️ Topics: {', '.join(metadata.get('important_phrases', [])[:5])}")
        
        else:
            stats = data.get('general_stats', {})
            parts.append("📊 **VISIONDESK AI OVERVIEW**")
            parts.append("=" * 50)
            parts.append(f"\n📁 **Total Audits:** {stats.get('total_audits', 0)}")
            parts.append(f"⚠️ **Violations:** {stats.get('violations', 0)}")
            parts.append(f"✅ **Safe Records:** {stats.get('safe', 0)}")
            parts.append(f"📈 **Compliance Rate:** {stats.get('compliance_rate', 0)}%")
            parts.append(f"📄 **Documents:** {stats.get('documents', 0)}")
            
            parts.append("\n💡 **Try asking:**")
            parts.append("• 'Investigate Zone A'")
            parts.append("• 'Show recent violations'")
            parts.append("• 'PPE compliance report'")
            parts.append("• 'Find safety manual'")
        
        # Add context if available
        if context and "No relevant documents" not in context:
            parts.append(f"\n{context}")
        
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
        elif any(kw in query_lower for kw in ['violation', 'violations', 'incident', 'hazard']):
            return 'recent_violations'
        else:
            return 'general_query'

# Create singleton
visiondesk_agent = VisionDeskAgent()
print("✅ VisionDesk Agent initialized (Rule-Based - No LLM)")