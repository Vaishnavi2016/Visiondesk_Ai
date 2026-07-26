# agent_workflows.py - Complete Working Version with Real Database Queries

import re
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pymongo import MongoClient
import json

class VisionDeskAgent:
    """Real-time agent with actual database queries"""
    
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
        """Process user query with real-time data"""
        
        query_lower = query.lower().strip()
        response_parts = []
        incident_data = None
        tool_results = []
        
        print(f"📝 Processing query: {query}")
        
        # ============================================
        # DETECT QUERY TYPE
        # ============================================
        
        # 1. ZONE INVESTIGATION
        if 'zone' in query_lower:
            print("📍 Detected: Zone Investigation")
            response_parts = self._handle_zone_query(query_lower)
            tool_results.append({'type': 'zone_investigation', 'status': 'executed'})
        
        # 2. RECENT VIOLATIONS
        elif any(kw in query_lower for kw in ['violation', 'violations', 'recent violations', 'latest violations']):
            print("🚨 Detected: Violation Query")
            response_parts = self._handle_violation_query(query_lower)
            tool_results.append({'type': 'recent_violations', 'status': 'executed'})
        
        # 3. PPE COMPLIANCE
        elif any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask', 'glove', 'compliance']):
            print("🛡️ Detected: PPE Compliance")
            response_parts = self._handle_ppe_query()
            tool_results.append({'type': 'ppe_compliance', 'status': 'executed'})
        
        # 4. SAFETY MANUAL / DOCUMENTS
        elif any(kw in query_lower for kw in ['manual', 'policy', 'procedure', 'guideline', 'document', 'safety manual']):
            print("📖 Detected: Document Query")
            response_parts = self._handle_document_query(query_lower)
            tool_results.append({'type': 'document_retrieval', 'status': 'executed'})
        
        # 5. GENERAL QUERY
        else:
            print("📊 Detected: General Query")
            response_parts = self._handle_general_query()
            tool_results.append({'type': 'general_query', 'status': 'executed'})
        
        # ============================================
        # LOG INCIDENT IF NEEDED
        # ============================================
        
        if any(kw in query_lower for kw in ['violation', 'incident', 'accident', 'hazard']) and 'recent' not in query_lower:
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
        
        # ============================================
        # GENERATE FINAL RESPONSE
        # ============================================
        
        final_response = "\n".join(response_parts) if response_parts else "I couldn't find information for your query. Please try asking about zones, violations, PPE compliance, or safety documents."
        
        return {
            'query': query,
            'response': final_response,
            'action': self._detect_action(query),
            'workflow_status': 'completed',
            'incident_data': incident_data,
            'tool_results': tool_results
        }
    
    # ============================================
    # HANDLER METHODS
    # ============================================
    
    def _handle_zone_query(self, query_lower: str) -> List[str]:
        """Handle zone investigation queries"""
        response_parts = []
        
        zone_match = re.search(r'zone\s*([a-z0-9]+)', query_lower, re.IGNORECASE)
        if zone_match:
            zone = zone_match.group(1).upper()
            print(f"🔍 Investigating Zone: {zone}")
            
            # Get zone data
            zone_data = self._get_zone_data(zone)
            
            if zone_data and zone_data.get('total', 0) > 0:
                response_parts.append(f"📍 **ZONE {zone} INVESTIGATION REPORT**")
                response_parts.append("=" * 50)
                response_parts.append(f"\n📊 **Total Inspections:** {zone_data.get('total', 0)}")
                response_parts.append(f"✅ **Safe Records:** {zone_data.get('safe', 0)}")
                response_parts.append(f"⚠️ **Violations:** {zone_data.get('violations', 0)}")
                response_parts.append(f"📈 **Compliance Rate:** {zone_data.get('compliance_rate', 0)}%")
                
                # Get detailed violations
                zone_violations = self._get_zone_violations(zone)
                if zone_violations:
                    response_parts.append(f"\n🚨 **VIOLATIONS IN ZONE {zone}:**")
                    for i, v in enumerate(zone_violations[:5], 1):
                        file_name = v.get('file_name', 'Unknown')
                        violations_list = v.get('violations', [])
                        summary = v.get('summary', {})
                        date_str = v.get('upload_date', datetime.now()).strftime('%Y-%m-%d %H:%M') if v.get('upload_date') else 'N/A'
                        
                        response_parts.append(f"\n{i}. 📄 **{file_name}**")
                        if violations_list:
                            response_parts.append(f"   ❌ {', '.join(violations_list)}")
                        response_parts.append(f"   👷 Workers: {summary.get('workers', 0)} | ⛑️ Helmets: {summary.get('helmets', 0)} | 🦺 Vests: {summary.get('vests', 0)}")
                        response_parts.append(f"   📅 {date_str}")
                
                # Recommendations
                if zone_data.get('violations', 0) > 0:
                    response_parts.append(f"\n📋 **RECOMMENDATIONS FOR ZONE {zone}:**")
                    response_parts.append("• Conduct immediate safety audit in Zone " + zone)
                    response_parts.append("• Ensure all workers have proper PPE")
                    response_parts.append("• Review safety protocols with team")
                else:
                    response_parts.append(f"\n✅ **Zone {zone} is compliant!**")
                    response_parts.append("• Continue regular monitoring")
                    response_parts.append("• Document all safety checks")
            else:
                response_parts.append(f"📍 **No data available for Zone {zone}.**")
                response_parts.append("Upload media with 'zone' in the filename to track zone-specific data.")
                response_parts.append("\n💡 **Tip:** Name your files like 'zone_a_inspection.jpg' for automatic zone detection.")
        else:
            response_parts.append("🔍 **Please specify which zone you want to investigate.**")
            response_parts.append("Example: 'Investigate Zone A' or 'Check Zone B status'")
        
        return response_parts
    
    def _handle_violation_query(self, query_lower: str) -> List[str]:
        """Handle violation queries"""
        response_parts = []
        
        # Determine time range
        if 'today' in query_lower:
            since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            violations = self._get_violations_since(since)
            time_label = "TODAY"
        elif 'week' in query_lower:
            since = datetime.now() - timedelta(days=7)
            violations = self._get_violations_since(since)
            time_label = "THIS WEEK"
        else:
            violations = self._get_latest_violations(limit=10)
            time_label = "RECENT"
        
        print(f"🔍 Found {len(violations)} violations for {time_label}")
        
        if violations:
            response_parts.append(f"🚨 **VIOLATIONS ({time_label})**")
            response_parts.append("=" * 50)
            response_parts.append(f"\n📊 **Total Violations:** {len(violations)}\n")
            
            for i, v in enumerate(violations[:10], 1):
                file_name = v.get('file_name', 'Unknown')
                violations_list = v.get('violations', [])
                summary = v.get('summary', {})
                date_str = v.get('upload_date', datetime.now()).strftime('%Y-%m-%d %H:%M') if v.get('upload_date') else 'N/A'
                
                response_parts.append(f"{i}. ⚠️ **{file_name}**")
                if violations_list:
                    response_parts.append(f"   ❌ Issues: {', '.join(violations_list)}")
                response_parts.append(f"   👷 Workers: {summary.get('workers', 0)} | ⛑️ Helmets: {summary.get('helmets', 0)} | 🦺 Vests: {summary.get('vests', 0)}")
                response_parts.append(f"   📅 {date_str}")
                response_parts.append("")
            
            # Summary statistics
            total_workers = sum(v.get('summary', {}).get('workers', 0) for v in violations)
            missing_helmets = sum(max(0, v.get('summary', {}).get('workers', 0) - v.get('summary', {}).get('helmets', 0)) for v in violations)
            missing_vests = sum(max(0, v.get('summary', {}).get('workers', 0) - v.get('summary', {}).get('vests', 0)) for v in violations)
            
            response_parts.append("📊 **SUMMARY:**")
            response_parts.append(f"• Total workers affected: {total_workers}")
            if missing_helmets > 0:
                response_parts.append(f"• Missing helmets: {missing_helmets}")
            if missing_vests > 0:
                response_parts.append(f"• Missing vests: {missing_vests}")
            
            response_parts.append("\n📋 **RECOMMENDATIONS:**")
            response_parts.append("• Address violations immediately")
            response_parts.append("• Schedule additional safety training")
            response_parts.append("• Increase random inspections")
        else:
            response_parts.append("✅ **No violations found!**")
            response_parts.append("All inspections are compliant. Keep up the good work!")
        
        return response_parts
    
    def _handle_ppe_query(self) -> List[str]:
        """Handle PPE compliance queries"""
        response_parts = []
        
        stats = self._get_ppe_compliance_stats()
        print(f"🛡️ PPE Stats: {stats}")
        
        if stats and stats.get('total_workers', 0) > 0:
            response_parts.append("🛡️ **PPE COMPLIANCE REPORT**")
            response_parts.append("=" * 50)
            response_parts.append(f"\n👷 **Total Workers Detected:** {stats.get('total_workers', 0)}")
            response_parts.append(f"⛑️ **Helmets:** {stats.get('helmets', 0)} ({stats.get('helmet_compliance', 0)}% compliance)")
            response_parts.append(f"🦺 **Vests:** {stats.get('vests', 0)} ({stats.get('vest_compliance', 0)}% compliance)")
            response_parts.append(f"😷 **Masks:** {stats.get('masks', 0)} ({stats.get('mask_compliance', 0)}% compliance)")
            
            # Overall compliance
            avg_compliance = (stats.get('helmet_compliance', 0) + stats.get('vest_compliance', 0) + stats.get('mask_compliance', 0)) / 3
            response_parts.append(f"\n📊 **Overall Compliance Score:** {round(avg_compliance)}%")
            
            # Risk assessment
            if avg_compliance < 70:
                response_parts.append("\n🚨 **CRITICAL:** PPE compliance is below 70%!")
                response_parts.append("• Immediate action required")
                response_parts.append("• Conduct emergency safety meeting")
                response_parts.append("• Distribute missing PPE immediately")
            elif avg_compliance < 90:
                response_parts.append("\n⚠️ **WARNING:** PPE compliance is below 90%")
                response_parts.append("• Schedule additional safety training")
                response_parts.append("• Increase random inspections")
                response_parts.append("• Review PPE distribution process")
            else:
                response_parts.append("\n✅ **GOOD:** PPE compliance is above 90%")
                response_parts.append("• Maintain current safety protocols")
                response_parts.append("• Continue regular monitoring")
        else:
            response_parts.append("📊 **No PPE data available.**")
            response_parts.append("Upload media with workers to generate compliance reports.")
            response_parts.append("\n💡 **Tip:** Upload images or videos from your site for automatic PPE detection.")
        
        return response_parts
    
    def _handle_document_query(self, query_lower: str) -> List[str]:
        """Handle safety manual/document queries"""
        response_parts = []
        
        # Search for documents
        documents = self._search_documents(query_lower)
        print(f"📖 Found {len(documents)} documents")
        
        if documents:
            response_parts.append("📖 **SAFETY DOCUMENTS & MANUALS**")
            response_parts.append("=" * 50)
            
            for doc in documents[:5]:
                filename = doc.get('filename', 'Unknown Document')
                response_parts.append(f"\n📄 **{filename}**")
                
                # Get knowledge entry
                knowledge = doc.get('knowledge_entry', {})
                metadata = knowledge.get('metadata', {})
                
                if metadata.get('sections'):
                    response_parts.append(f"📑 Sections: {', '.join(metadata.get('sections', [])[:3])}")
                
                if metadata.get('important_phrases'):
                    response_parts.append(f"🏷️ Topics: {', '.join(metadata.get('important_phrases', [])[:5])}")
                
                # Extract relevant passage
                full_text = knowledge.get('full_text', '')
                if full_text:
                    passages = self._find_relevant_passages(full_text, query_lower)
                    if passages:
                        response_parts.append(f"📝 Excerpt: {passages[0][:200]}...")
                
                # Show RAG status
                if doc.get('rag_indexed'):
                    response_parts.append(f"🧠 RAG Indexed: ✅")
        else:
            response_parts.append("📚 **No safety documents found.**")
            response_parts.append("\n📤 **Upload safety documents to build your knowledge base:**")
            response_parts.append("• Supported formats: PDF, DOCX, TXT, HTML")
            response_parts.append("• Go to 'Upload Document' section")
            response_parts.append("• Documents will be automatically indexed for AI search")
        
        return response_parts
    
    def _handle_general_query(self) -> List[str]:
        """Handle general queries"""
        response_parts = []
        
        stats = self._get_general_stats()
        print(f"📊 General Stats: {stats}")
        
        response_parts.append("📊 **VISIONDESK AI OVERVIEW**")
        response_parts.append("=" * 50)
        response_parts.append(f"\n📁 **Total Audits:** {stats.get('total_audits', 0)}")
        response_parts.append(f"⚠️ **Violations:** {stats.get('violations', 0)}")
        response_parts.append(f"✅ **Safe Records:** {stats.get('safe', 0)}")
        response_parts.append(f"📈 **Compliance Rate:** {stats.get('compliance_rate', 0)}%")
        response_parts.append(f"📄 **Documents:** {stats.get('documents', 0)}")
        
        response_parts.append("\n💡 **Try asking:**")
        response_parts.append("• 'Investigate Zone A'")
        response_parts.append("• 'Show recent violations'")
        response_parts.append("• 'PPE compliance report'")
        response_parts.append("• 'Find safety manual'")
        
        return response_parts
    
    # ============================================
    # DATABASE QUERY METHODS
    # ============================================
    
    def _get_latest_violations(self, limit=10):
        """Get latest violations from database"""
        try:
            records = list(self.records_col.find({
                'status': 'VIOLATION DETECTED'
            }).sort('upload_date', -1).limit(limit))
            print(f"📊 Found {len(records)} violations")
            return records
        except Exception as e:
            print(f"❌ Error getting violations: {e}")
            return []
    
    def _get_violations_since(self, since):
        """Get violations since a specific date"""
        try:
            records = list(self.records_col.find({
                'status': 'VIOLATION DETECTED',
                'upload_date': {'$gte': since}
            }).sort('upload_date', -1))
            print(f"📊 Found {len(records)} violations since {since}")
            return records
        except Exception as e:
            print(f"❌ Error getting violations since {since}: {e}")
            return []
    
    def _get_zone_data(self, zone):
        """Get data for a specific zone"""
        try:
            # Search for zone in filenames
            records = list(self.records_col.find({
                '$or': [
                    {'file_name': {'$regex': f'zone[_\s]*{zone}', '$options': 'i'}},
                    {'file_name': {'$regex': f'{zone}[_\s]*zone', '$options': 'i'}}
                ]
            }))
            
            print(f"📊 Found {len(records)} records for Zone {zone}")
            
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
            print(f"❌ Error getting zone data: {e}")
            return None
    
    def _get_zone_violations(self, zone):
        """Get violations for a specific zone"""
        try:
            records = list(self.records_col.find({
                '$or': [
                    {'file_name': {'$regex': f'zone[_\s]*{zone}', '$options': 'i'}},
                    {'file_name': {'$regex': f'{zone}[_\s]*zone', '$options': 'i'}}
                ],
                'status': 'VIOLATION DETECTED'
            }).sort('upload_date', -1).limit(10))
            return records
        except Exception as e:
            print(f"❌ Error getting zone violations: {e}")
            return []
    
    def _get_ppe_compliance_stats(self):
        """Get PPE compliance statistics"""
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
            print(f"❌ Error getting PPE stats: {e}")
            return None
    
    def _search_documents(self, query):
        """Search documents by filename or content"""
        try:
            # Clean query
            search_terms = re.sub(r'(safety|manual|policy|procedure|guideline|document|show|find|search|for|the|and|or|of|to|in|on|at)', '', query)
            search_terms = search_terms.strip()
            
            if not search_terms or len(search_terms) < 3:
                docs = list(self.documents_col.find({}).sort('upload_date', -1).limit(5))
                return docs
            
            # Search by filename
            docs = list(self.documents_col.find({
                'filename': {'$regex': search_terms, '$options': 'i'}
            }).limit(5))
            
            if not docs:
                # Search in knowledge entries
                docs = list(self.documents_col.find({
                    'knowledge_entry.full_text': {'$regex': search_terms, '$options': 'i'}
                }).limit(5))
            
            if not docs:
                # Return recent documents
                docs = list(self.documents_col.find({}).sort('upload_date', -1).limit(3))
            
            return docs
        except Exception as e:
            print(f"❌ Error searching documents: {e}")
            return []
    
    def _find_relevant_passages(self, text, query, max_passages=3):
        """Find relevant passages in text"""
        sentences = text.split('. ')
        relevant = []
        query_words = set(re.sub(r'(safety|manual|policy|procedure|guideline|document|show|find|search|for|the|and|or|of|to|in|on|at)', '', query).split())
        query_words = {w for w in query_words if len(w) > 2}
        
        if not query_words:
            return [text[:200]]
        
        for sentence in sentences:
            sentence_words = set(sentence.lower().split())
            overlap = len(query_words & sentence_words)
            if overlap > 0:
                relevant.append(sentence.strip() + '.')
                if len(relevant) >= max_passages:
                    break
        
        return relevant if relevant else [text[:200]]
    
    def _get_general_stats(self):
        """Get general dashboard stats"""
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
            print(f"❌ Error getting general stats: {e}")
            return {
                'total_audits': 0,
                'violations': 0,
                'safe': 0,
                'compliance_rate': 100,
                'documents': 0
            }
    
    def _detect_action(self, query):
        """Detect action from query"""
        query_lower = query.lower()
        if 'zone' in query_lower:
            return 'zone_investigation'
        elif any(kw in query_lower for kw in ['ppe', 'helmet', 'vest', 'mask']):
            return 'ppe_compliance'
        elif any(kw in query_lower for kw in ['manual', 'policy', 'procedure', 'guideline']):
            return 'document_retrieval'
        elif any(kw in query_lower for kw in ['violation', 'violations', 'incident', 'alert', 'hazard']):
            return 'recent_violations'
        else:
            return 'general_query'

# Create singleton
visiondesk_agent = VisionDeskAgent()
print("✅ VisionDesk Agent initialized")