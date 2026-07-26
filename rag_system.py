# rag_system.py - Enhanced version
import os
import json
from typing import List, Dict, Any
from datetime import datetime
import hashlib
from pymongo import MongoClient

class RAGSystem:
    """Enhanced RAG system with better context retrieval"""
    
    def __init__(self):
        self.documents = []
        self.vectorizer = None
        self.doc_vectors = None
        
        # MongoDB connection
        self.mongodb_client = MongoClient('mongodb://localhost:27017/')
        self.db = self.mongodb_client['visiondesk_db']
        self.rag_collection = self.db['rag_embeddings']
        self.knowledge_col = self.db['knowledge_repository']
        
        self._load_from_db()
        self._build_vectorizer()
    
    def _load_from_db(self):
        """Load existing documents from database"""
        try:
            # Try to load from rag_embeddings first
            stored = self.rag_collection.find_one({'type': 'simple_rag'})
            if stored and 'documents' in stored:
                self.documents = stored.get('documents', [])
                print(f"Loaded {len(self.documents)} chunks from RAG storage")
            else:
                # Load from knowledge_repository
                knowledge_docs = list(self.knowledge_col.find({}))
                for doc in knowledge_docs:
                    text = doc.get('full_text', '') or doc.get('searchable_text', '')
                    if text:
                        chunks = self._chunk_text(text)
                        for chunk in chunks:
                            self.documents.append({
                                'text': chunk,
                                'metadata': {
                                    'filename': doc.get('filename', 'Unknown'),
                                    'source': 'knowledge_repository',
                                    'upload_date': doc.get('upload_date', datetime.now()).isoformat()
                                },
                                'chunk_id': hashlib.md5(chunk.encode()).hexdigest()[:12]
                            })
                print(f"Loaded {len(self.documents)} chunks from knowledge repository")
        except Exception as e:
            print(f"Could not load documents: {e}")
    
    def _build_vectorizer(self):
        """Build TF-IDF vectorizer from documents"""
        if not self.documents:
            return
        
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
            texts = [d['text'] for d in self.documents]
            self.doc_vectors = self.vectorizer.fit_transform(texts)
        except Exception as e:
            print(f"Could not build vectorizer: {e}")
    
    def add_document(self, text: str, metadata: Dict[str, Any]) -> List[Dict]:
        """Add a document to the RAG system"""
        chunks = self._chunk_text(text)
        added_chunks = []
        
        for chunk in chunks:
            chunk_doc = {
                'text': chunk,
                'metadata': metadata,
                'chunk_id': hashlib.md5(chunk.encode()).hexdigest()[:12],
                'added_date': datetime.now().isoformat()
            }
            self.documents.append(chunk_doc)
            added_chunks.append(chunk_doc)
        
        self._build_vectorizer()
        self._save_to_db()
        
        return added_chunks
    
    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """Split text into chunks with paragraph awareness"""
        if not text:
            return []
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                if current_chunk:
                    current_chunk += " " + para
                else:
                    current_chunk = para
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text[:1000]]
    
    def _save_to_db(self):
        """Save to MongoDB"""
        try:
            self.rag_collection.update_one(
                {'type': 'simple_rag'},
                {
                    '$set': {
                        'documents': self.documents,
                        'last_updated': datetime.now(),
                        'count': len(self.documents)
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"Error saving to RAG DB: {e}")
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant chunks with better scoring"""
        if not self.documents or self.doc_vectors is None or self.vectorizer is None:
            return []
        
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            query_vec = self.vectorizer.transform([query])
            similarities = cosine_similarity(query_vec, self.doc_vectors).flatten()
            
            # Get top indices with positive similarity
            top_indices = similarities.argsort()[-top_k:][::-1]
            
            results = []
            for idx in top_indices:
                if similarities[idx] > 0.01:  # Minimum threshold
                    results.append({
                        'text': self.documents[idx]['text'],
                        'metadata': self.documents[idx]['metadata'],
                        'score': float(similarities[idx]),
                        'chunk_id': self.documents[idx]['chunk_id']
                    })
            
            return results
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def get_context(self, query: str, top_k: int = 5) -> str:
        """Get context with source attribution"""
        results = self.search(query, top_k)
        if not results:
            return "No relevant documents found in the knowledge base."
        
        parts = []
        parts.append("📚 **Relevant Information from Knowledge Base:**\n")
        
        for i, r in enumerate(results, 1):
            filename = r['metadata'].get('filename', 'Unknown Document')
            score_pct = round(r['score'] * 100)
            
            parts.append(f"**[{i}] From: {filename}** (Relevance: {score_pct}%)")
            parts.append(f"{r['text'][:300]}...")
            parts.append("")
        
        return "\n".join(parts)
    
    def get_document_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        unique_docs = len(set(d.get('metadata', {}).get('filename', '') for d in self.documents))
        return {
            'total_chunks': len(self.documents),
            'documents': unique_docs,
            'last_updated': datetime.now().isoformat()
        }

# Create singleton
rag_system = RAGSystem()