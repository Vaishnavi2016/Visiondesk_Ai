# agent_workflows_llm.py - Complete Working Agent with Real Responses

import json
import datetime
import re
from collections import Counter
from pymongo import MongoClient

# Try to import RAG system
try:
    from rag_system import rag_system
except ImportError:
    # Create a simple RAG fallback
    class DummyRAG:
        def get_context(self, q, k=5):
            return "No RAG system available."
        def search(self, q, k=5):
            return []
        def get_document_stats(self):
            return {'total_chunks': 0, 'documents': 0}
    rag_system = DummyRAG()

class VisionDeskAgent:
    def __init__(self):
        """Initialize the VisionDesk Agent with database connection"""
        try:
            self.client = MongoClient('mongodb://localhost:27017/')
            self.db = self.client['visiondesk_db']
            self.records_col = self.db['visual_records']
            self.documents_col = self.db['documents']
            self.incidents_col = self.db['incidents']
            self.knowledge_col = self.db['knowledge_repository']
            print("✅ Agent connected to MongoDB")
        except Exception as e:
            print(f"⚠️ Agent database connection failed: {e}")
            self.records_col = None
            self.documents_col = None
            self.incidents_col = None
            self.knowledge_col = None
    
    def process_query(self, query, username):
        """Main entry point for processing user queries"""
        if not query or not query.strip():
            return {
                'response': "Please enter a valid question.",
                'query': query,
                'action': 'error'
            }
        
        query_lower = query.lower().strip()
        
        # Route to appropriate handler based on query type
        if self._is_greeting(query_lower):
            return self._handle_greeting(username)
        elif self._is_help(query_lower):
            return self._handle_help()
        elif self._is_statistics(query_lower):
            return self._handle_statistics(username)
        elif self._is_incident_query(query_lower):
            return self._handle_incident_query(query_lower, username)
        elif self._is_compliance_query(query_lower):
            return self._handle_compliance_query(username)
        elif self._is_recommendation_query(query_lower):
            return self._handle_recommendations(username)
        elif self._is_knowledge_query(query_lower):
            return self._handle_knowledge_query(query_lower, username)
        elif self._is_document_query(query_lower):
            return self._handle_document_query(query_lower, username)
        else:
            # Default: search knowledge base and use RAG
            return self._handle_general_query(query, username)
    
    # ========== QUERY CLASSIFICATION ==========
    
    def _is_greeting(self, query):
        greetings = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
        return any(g in query for g in greetings)
    
    def _is_help(self, query):
        help_terms = ['help', 'what can you do', 'capabilities', 'features', 'how to use', 'guide']
        return any(h in query for h in help_terms)
    
    def _is_statistics(self, query):
        stat_terms = ['statistics', 'stats', 'summary', 'overview', 'dashboard', 'count', 'total', 'analytics']
        return any(s in query for s in stat_terms)
    
    def _is_incident_query(self, query):
        incident_terms = ['incident', 'accident', 'violation', 'hazard', 'danger', 'unsafe', 'alert', 'emergency']
        return any(i in query for i in incident_terms)
    
    def _is_compliance_query(self, query):
        compliance_terms = ['compliance', 'regulation', 'standard', 'osha', 'safety rule', 'policy', 'procedure']
        return any(c in query for c in compliance_terms)
    
    def _is_recommendation_query(self, query):
        rec_terms = ['recommend', 'suggest', 'advise', 'improve', 'prevent', 'solution', 'action']
        return any(r in query for r in rec_terms)
    
    def _is_knowledge_query(self, query):
        knowledge_terms = ['what is', 'how to', 'why', 'explain', 'define', 'meaning', 'purpose', 'benefits']
        return any(k in query for k in knowledge_terms)
    
    def _is_document_query(self, query):
        doc_terms = ['document', 'pdf', 'file', 'report', 'upload', 'search', 'find']
        return any(d in query for d in doc_terms)
    
    # ========== HANDLERS ==========
    
    def _handle_greeting(self, username):
        """Handle greeting queries"""
        responses = [
            f"Hello {username}! 👋 I'm your VisionDesk AI assistant. I can help you with safety compliance, document analysis, and incident management.",
            f"Hi {username}! How can I assist you with safety management today?",
            f"Greetings {username}! I'm ready to help you analyze safety data and compliance."
        ]
        import random
        return {
            'response': responses[random.randint(0, len(responses)-1)],
            'query': 'greeting',
            'action': 'greeting',
            'tool_results': [{'type': 'greeting', 'status': 'success'}]
        }
    
    def _handle_help(self):
        """Handle help queries"""
        help_text = """
**🤖 VisionDesk AI Assistant - Capabilities**

I can help you with:

📊 **Analytics & Statistics**
- Get compliance rates and safety metrics
- View detection summaries and trends

📄 **Document Management**
- Search through uploaded safety documents
- Extract knowledge from PDFs, DOCX, TXT files

🚨 **Incident Management**
- Review safety incidents and violations
- Get incident details and status

💡 **Recommendations**
- Get safety improvement suggestions
- Preventive action recommendations

📚 **Knowledge Base**
- Search safety regulations and procedures
- Get answers to safety-related questions

**Try asking me:**
- "What's the current compliance rate?"
- "Show me recent safety incidents"
- "How can I improve site safety?"
- "What safety regulations should we follow?"
- "Search for PPE guidelines in documents"
"""
        return {
            'response': help_text,
            'query': 'help',
            'action': 'help',
            'tool_results': [{'type': 'help', 'status': 'success'}]
        }
    
    def _handle_statistics(self, username):
        """Handle statistics queries"""
        try:
            if not self.records_col:
                return self._get_fallback_response("statistics")
            
            # Get user's records
            records = list(self.records_col.find({'uploaded_by': username}))
            total = len(records)
            
            if total == 0:
                return {
                    'response': "📊 No detection records found yet. Upload some media to start collecting safety data.",
                    'query': 'statistics',
                    'action': 'statistics',
                    'tool_results': [{'type': 'statistics', 'status': 'no_data'}]
                }
            
            violations = sum(1 for r in records if r.get('status') != 'SAFE')
            safe = total - violations
            compliance = round((safe / total * 100)) if total > 0 else 100
            
            # Equipment stats
            workers = sum(r.get('summary', {}).get('workers', 0) for r in records)
            helmets = sum(r.get('summary', {}).get('helmets', 0) for r in records)
            vests = sum(r.get('summary', {}).get('vests', 0) for r in records)
            masks = sum(r.get('summary', {}).get('masks', 0) for r in records)
            
            # Violation types
            violation_counts = Counter()
            for record in records:
                for v in record.get('violations', []):
                    violation_counts[v] += 1
            
            response = f"""
📊 **Safety Statistics Summary**

📁 Total Records: **{total}**
✅ Safe Records: **{safe}**
⚠️ Violations: **{violations}**
📈 Compliance Rate: **{compliance}%**

👷 **Equipment Usage:**
- Workers Detected: {workers}
- Helmets: {helmets} ({round((helmets/workers)*100 if workers > 0 else 0)}%)
- Vests: {vests} ({round((vests/workers)*100 if workers > 0 else 0)}%)
- Masks: {masks} ({round((masks/workers)*100 if workers > 0 else 0)}%)
"""
            
            if violation_counts:
                response += "\n🚨 **Top Violations:**\n"
                for violation, count in violation_counts.most_common(3):
                    response += f"- {violation}: {count} times\n"
            
            return {
                'response': response,
                'query': 'statistics',
                'action': 'statistics',
                'tool_results': [{
                    'type': 'statistics',
                    'status': 'success',
                    'data': {
                        'total': total,
                        'violations': violations,
                        'safe': safe,
                        'compliance': compliance,
                        'equipment': {
                            'workers': workers,
                            'helmets': helmets,
                            'vests': vests,
                            'masks': masks
                        }
                    }
                }]
            }
            
        except Exception as e:
            return self._get_error_response(f"Error getting statistics: {str(e)}")
    
    def _handle_incident_query(self, query, username):
        """Handle incident-related queries"""
        try:
            if not self.incidents_col:
                return self._get_fallback_response("incidents")
            
            # Search for incidents
            search_terms = query.split()
            filter_query = {
                '$or': [
                    {'user': username},
                    {'uploaded_by': username}
                ]
            }
            
            # Get incidents
            incidents = list(self.incidents_col.find(filter_query).sort('timestamp', -1).limit(10))
            records = list(self.records_col.find({'uploaded_by': username}).sort('upload_date', -1).limit(10))
            
            # Also check for violations in records
            violations = [r for r in records if r.get('status') != 'SAFE']
            
            if not incidents and not violations:
                return {
                    'response': "🚨 No incidents or violations found. Keep up the good safety practices!",
                    'query': query,
                    'action': 'incident',
                    'tool_results': [{'type': 'incident', 'status': 'no_data'}]
                }
            
            response = "🚨 **Incidents & Violations Report**\n\n"
            
            if incidents:
                response += f"📋 **Incidents** ({len(incidents)}):\n"
                for inc in incidents[:5]:
                    status_icon = "🔴" if inc.get('status') == 'active' else "✅"
                    response += f"{status_icon} {inc.get('type', 'General')} - {inc.get('status', 'Unknown')}\n"
                    response += f"   📝 {inc.get('description', 'No description')[:100]}\n"
                    if inc.get('severity'):
                        response += f"   ⚠️ Severity: {inc.get('severity')}\n"
                    response += "\n"
            
            if violations:
                response += f"⚠️ **Recent Violations** ({len(violations)}):\n"
                for v in violations[:5]:
                    response += f"- {v.get('file_name')}: {', '.join(v.get('violations', ['Violation detected']))}\n"
            
            return {
                'response': response,
                'query': query,
                'action': 'incident',
                'tool_results': [{
                    'type': 'incident',
                    'status': 'success',
                    'data': {
                        'incidents': len(incidents),
                        'violations': len(violations)
                    }
                }]
            }
            
        except Exception as e:
            return self._get_error_response(f"Error getting incidents: {str(e)}")
    
    def _handle_compliance_query(self, username):
        """Handle compliance-related queries"""
        try:
            records = list(self.records_col.find({'uploaded_by': username}))
            
            if not records:
                return {
                    'response': "📋 No compliance data available. Upload media to start compliance monitoring.",
                    'query': 'compliance',
                    'action': 'compliance',
                    'tool_results': [{'type': 'compliance', 'status': 'no_data'}]
                }
            
            total = len(records)
            violations = sum(1 for r in records if r.get('status') != 'SAFE')
            compliance = round(((total - violations) / total * 100)) if total > 0 else 100
            
            # Check specific compliance areas
            workers = sum(r.get('summary', {}).get('workers', 0) for r in records)
            helmets = sum(r.get('summary', {}).get('helmets', 0) for r in records)
            vests = sum(r.get('summary', {}).get('vests', 0) for r in records)
            
            helmet_compliance = round((helmets / workers * 100)) if workers > 0 else 100
            vest_compliance = round((vests / workers * 100)) if workers > 0 else 100
            
            response = f"""
📋 **Compliance Status Report**

Overall Compliance: **{compliance}%**

📊 **Equipment Compliance:**
- Helmet Compliance: {helmet_compliance}% ({helmets}/{workers} workers)
- Vest Compliance: {vest_compliance}% ({vests}/{workers} workers)

📈 **Summary:**
- Total Inspections: {total}
- Safe Records: {total - violations}
- Violations: {violations}

"""
            
            if compliance >= 90:
                response += "✅ **Excellent compliance!** Continue maintaining these high standards."
            elif compliance >= 70:
                response += "⚠️ **Good compliance.** Consider improving in areas with violations."
            else:
                response += "🔴 **Compliance needs improvement.** Review safety procedures immediately."
            
            return {
                'response': response,
                'query': 'compliance',
                'action': 'compliance',
                'tool_results': [{
                    'type': 'compliance',
                    'status': 'success',
                    'data': {
                        'compliance_rate': compliance,
                        'helmet_compliance': helmet_compliance,
                        'vest_compliance': vest_compliance
                    }
                }]
            }
            
        except Exception as e:
            return self._get_error_response(f"Error checking compliance: {str(e)}")
    
    def _handle_recommendations(self, username):
        """Handle recommendation queries"""
        try:
            records = list(self.records_col.find({'uploaded_by': username}).sort('upload_date', -1).limit(10))
            
            if not records:
                return {
                    'response': "💡 I need some data to make recommendations. Upload media or documents to get started.",
                    'query': 'recommendations',
                    'action': 'recommendations',
                    'tool_results': [{'type': 'recommendations', 'status': 'no_data'}]
                }
            
            # Analyze violations pattern
            violations = []
            for record in records:
                if record.get('violations'):
                    violations.extend(record.get('violations', []))
            
            violation_counts = Counter(violations)
            recommendations = []
            
            # Generate recommendations based on patterns
            if violation_counts.get('Missing helmet protective gear.', 0) >= 2:
                recommendations.append(
                    "🪖 **Increase helmet enforcement:** Implement mandatory helmet usage policy and conduct regular checks."
                )
            if violation_counts.get('Missing high-visibility vest safety gear.', 0) >= 2:
                recommendations.append(
                    "🦺 **Improve vest compliance:** Ensure all workers have access to high-visibility vests and enforce usage."
                )
            
            # General recommendations
            recommendations.append("📋 **Regular audits:** Conduct weekly safety inspections and document all findings.")
            recommendations.append("📚 **Training:** Provide regular safety training sessions for all workers.")
            recommendations.append("🔍 **Monitoring:** Install additional cameras in high-risk areas.")
            
            if not recommendations:
                recommendations = [
                    "✅ **Great work!** No significant violations detected. Continue your excellent safety practices.",
                    "📊 **Documentation:** Keep all safety documents up-to-date and accessible.",
                    "🎯 **Continuous improvement:** Set monthly safety goals and track progress."
                ]
            
            response = "💡 **Safety Recommendations**\n\n" + "\n".join(recommendations)
            
            return {
                'response': response,
                'query': 'recommendations',
                'action': 'recommendations',
                'tool_results': [{
                    'type': 'recommendations',
                    'status': 'success',
                    'data': {'recommendations': recommendations}
                }]
            }
            
        except Exception as e:
            return self._get_error_response(f"Error generating recommendations: {str(e)}")
    
    def _handle_knowledge_query(self, query, username):
        """Handle knowledge-based queries using RAG"""
        try:
            # Search RAG system
            rag_results = rag_system.search(query, top_k=5)
            
            if not rag_results:
                # Fallback to knowledge collection
                knowledge_results = []
                if self.knowledge_col:
                    for doc in self.knowledge_col.find({}).limit(5):
                        knowledge_results.append(doc.get('full_text', '')[:300])
                
                if knowledge_results:
                    response = "📚 **Knowledge Base Results:**\n\n"
                    for i, result in enumerate(knowledge_results, 1):
                        response += f"[{i}] {result}...\n\n"
                else:
                    response = "📚 I don't have enough information in the knowledge base to answer that. Try uploading relevant documents."
            else:
                response = "📚 **Found relevant information:**\n\n"
                for i, result in enumerate(rag_results, 1):
                    text = result.get('text', '')[:400]
                    source = result.get('metadata', {}).get('filename', 'Unknown source')
                    response += f"[{i}] {text}...\nSource: {source}\n\n"
            
            return {
                'response': response,
                'query': query,
                'action': 'knowledge',
                'tool_results': [{
                    'type': 'knowledge',
                    'status': 'success',
                    'count': len(rag_results)
                }]
            }
            
        except Exception as e:
            return self._get_error_response(f"Error searching knowledge base: {str(e)}")
    
    def _handle_document_query(self, query, username):
        """Handle document-related queries"""
        try:
            if not self.documents_col:
                return self._get_fallback_response("documents")
            
            # Search for documents
            search_terms = query.lower().split()
            docs = list(self.documents_col.find({'uploaded_by': username}))
            
            if not docs:
                return {
                    'response': "📄 No documents uploaded yet. Go to Documents → Upload Document to add safety documents.",
                    'query': query,
                    'action': 'documents',
                    'tool_results': [{'type': 'documents', 'status': 'no_data'}]
                }
            
            # Filter documents by search terms
            matching_docs = []
            for doc in docs:
                filename = doc.get('filename', '').lower()
                if any(term in filename for term in search_terms):
                    matching_docs.append(doc)
            
            if matching_docs:
                response = f"📄 **Found {len(matching_docs)} documents:**\n\n"
                for doc in matching_docs[:10]:
                    response += f"- {doc.get('filename')} (Uploaded: {doc.get('upload_date', 'Unknown')})\n"
                    if doc.get('sections'):
                        response += f"  Sections: {', '.join(doc.get('sections', [])[:3])}\n"
            else:
                response = f"📄 Found {len(docs)} documents. Try searching with different terms.\n\n"
                response += "Recent documents:\n"
                for doc in docs[:5]:
                    response += f"- {doc.get('filename')} (Uploaded: {doc.get('upload_date', 'Unknown')})\n"
            
            return {
                'response': response,
                'query': query,
                'action': 'documents',
                'tool_results': [{
                    'type': 'documents',
                    'status': 'success',
                    'count': len(matching_docs) if matching_docs else len(docs)
                }]
            }
            
        except Exception as e:
            return self._get_error_response(f"Error searching documents: {str(e)}")
    
    def _handle_general_query(self, query, username):
        """Handle general queries with RAG context"""
        try:
            # Get RAG context
            rag_context = rag_system.get_context(query, k=3)
            
            if rag_context and "No relevant documents" not in rag_context:
                response = f"🔍 **Based on available knowledge:**\n\n{rag_context}"
            else:
                # Try to provide a helpful response
                response = f"I understand you're asking about: '{query}'\n\n"
                response += "I can help you with:\n"
                response += "📊 Statistics & analytics\n"
                response += "🚨 Incident reports\n"
                response += "📄 Document search\n"
                response += "💡 Safety recommendations\n"
                response += "📚 Knowledge base queries\n\n"
                response += "Try being more specific, or ask me something like:\n"
                response += "- 'What's the compliance rate?'\n"
                response += "- 'Show me recent incidents'\n"
                response += "- 'How can I improve safety?'"
            
            return {
                'response': response,
                'query': query,
                'action': 'general',
                'tool_results': [{'type': 'general', 'status': 'success'}]
            }
            
        except Exception as e:
            return self._get_error_response(f"Error processing your query: {str(e)}")
    
    # ========== UTILITY METHODS ==========
    
    def _get_error_response(self, error_message):
        """Generate error response"""
        return {
            'response': f"❌ {error_message}\n\nPlease try again or ask a different question.",
            'query': 'error',
            'action': 'error',
            'tool_results': [{'type': 'error', 'status': 'error', 'error': error_message}]
        }
    
    def _get_fallback_response(self, context):
        """Generate fallback response when database is not available"""
        return {
            'response': f"⚠️ I'm having trouble accessing the database for '{context}'. Please check your MongoDB connection.\n\nYou can still ask about general safety topics or upload documents.",
            'query': 'fallback',
            'action': 'fallback',
            'tool_results': [{'type': 'fallback', 'status': 'error'}]
        }

# Create singleton instance
visiondesk_agent = VisionDeskAgent()