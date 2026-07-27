# rag_system.py - NO LLM, Pure RAG with TF-IDF

import os
import json
import re
from typing import List, Dict, Any
from datetime import datetime
import hashlib
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class RAGSystem:
    """Pure RAG System with TF-IDF - No LLM Required"""
    
    def __init__(self):
        self.documents = []
        self.vectorizer = None
        self.doc_vectors = None
        
        # No LLM - pure retrieval
        self.use_llm = False
        
        # MongoDB connection
        self._init_mongodb()
        self._load_from_db()
        self._build_vectorizer()
    
    def _init_mongodb(self):
        """Initialize MongoDB connection"""
        try:
            self.mongodb_client = MongoClient('mongodb://localhost:27017/')
            self.db = self.mongodb_client['visiondesk_db']
            self.rag_collection = self.db['rag_embeddings']
            self.knowledge_col = self.db['knowledge_repository']
            print("✅ MongoDB connected")
        except Exception as e:
            print(f"⚠️ MongoDB connection failed: {e}")
            self.rag_collection = None
            self.knowledge_col = None
    
    def _load_from_db(self):
        """Load existing documents from database"""
        if self.rag_collection is None:
            print("⚠️ RAG collection not available")
            return
            
        try:
            stored = self.rag_collection.find_one({'type': 'simple_rag'})
            if stored and 'documents' in stored:
                self.documents = stored.get('documents', [])
                print(f"📚 Loaded {len(self.documents)} chunks from RAG storage")
            else:
                if self.knowledge_col is not None:
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
                    print(f"📚 Loaded {len(self.documents)} chunks from knowledge repository")
        except Exception as e:
            print(f"⚠️ Could not load documents: {e}")
    
    def _build_vectorizer(self):
        """Build TF-IDF vectorizer from documents"""
        if not self.documents:
            return
        
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
            texts = [d['text'] for d in self.documents]
            self.doc_vectors = self.vectorizer.fit_transform(texts)
            print(f"✅ Vectorizer built with {len(self.documents)} documents")
        except ImportError:
            print("⚠️ scikit-learn not installed. Run: pip install scikit-learn")
        except Exception as e:
            print(f"⚠️ Could not build vectorizer: {e}")
    
    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """Split text into chunks"""
        if not text:
            return []
        
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
        if self.rag_collection is None:
            return
            
        try:
            self.rag_collection.update_one(
                {'type': 'simple_rag'},
                {
                    '$set': {
                        'documents': self.documents,
                        'last_updated': datetime.now(),
                        'count': len(self.documents),
                        'llm_enabled': False
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"⚠️ Error saving to RAG DB: {e}")
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant chunks"""
        if not self.documents or self.doc_vectors is None or self.vectorizer is None:
            return []
        
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            query_vec = self.vectorizer.transform([query])
            similarities = cosine_similarity(query_vec, self.doc_vectors).flatten()
            
            top_indices = similarities.argsort()[-top_k:][::-1]
            
            results = []
            for idx in top_indices:
                if similarities[idx] > 0.01:
                    results.append({
                        'text': self.documents[idx]['text'],
                        'metadata': self.documents[idx]['metadata'],
                        'score': float(similarities[idx]),
                        'chunk_id': self.documents[idx]['chunk_id']
                    })
            
            return results
        except Exception as e:
            print(f"⚠️ Search error: {e}")
            return []
    
    def get_context(self, query: str, top_k: int = 5) -> str:
        """Get context for RAG"""
        results = self.search(query, top_k)
        if not results:
            return "No relevant documents found."
        
        parts = ["📚 **Relevant Information from Knowledge Base:**\n"]
        for i, r in enumerate(results, 1):
            filename = r['metadata'].get('filename', 'Unknown Document')
            score_pct = round(r['score'] * 100)
            parts.append(f"**[{i}] From: {filename}** (Relevance: {score_pct}%)")
            parts.append(f"{r['text'][:400]}...")
            parts.append("")
        
        return "\n".join(parts)
    
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
    
    def get_document_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        unique_docs = len(set(d.get('metadata', {}).get('filename', '') for d in self.documents))
        return {
            'total_chunks': len(self.documents),
            'documents': unique_docs,
            'llm_enabled': False,
            'last_updated': datetime.now().isoformat()
        }

# Create singleton
rag_system = RAGSystem()
print(f"🤖 RAG System ready (LLM: Disabled - Pure Retrieval)")