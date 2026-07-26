# setup_mongodb.py
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid

def setup_mongodb_collections():
    """Setup all MongoDB collections needed for VisionDesk RAG system"""
    
    # Connect to MongoDB
    client = MongoClient('mongodb://localhost:27017/')
    db = client['visiondesk_db']
    
    print("🔍 Setting up MongoDB collections for VisionDesk RAG...")
    
    # ============================================
    # EXISTING COLLECTIONS (already in your app.py)
    # ============================================
    
    # 1. users - for authentication
    if 'users' not in db.list_collection_names():
        db.create_collection('users')
        print("✅ Created 'users' collection")
    else:
        print("ℹ️ 'users' collection already exists")
    
    # 2. visual_records - for uploaded media analysis
    if 'visual_records' not in db.list_collection_names():
        db.create_collection('visual_records')
        print("✅ Created 'visual_records' collection")
    else:
        print("ℹ️ 'visual_records' collection already exists")
    
    # 3. documents - for uploaded documents
    if 'documents' not in db.list_collection_names():
        db.create_collection('documents')
        print("✅ Created 'documents' collection")
    else:
        print("ℹ️ 'documents' collection already exists")
    
    # 4. knowledge_repository - for document knowledge extraction
    if 'knowledge_repository' not in db.list_collection_names():
        db.create_collection('knowledge_repository')
        print("✅ Created 'knowledge_repository' collection")
    else:
        print("ℹ️ 'knowledge_repository' collection already exists")
    
    # ============================================
    # NEW RAG COLLECTIONS
    # ============================================
    
    # 5. rag_embeddings - for vector embeddings storage
    if 'rag_embeddings' not in db.list_collection_names():
        db.create_collection('rag_embeddings')
        print("✅ Created 'rag_embeddings' collection for RAG vectors")
    else:
        print("ℹ️ 'rag_embeddings' collection already exists")
    
    # 6. incidents - for logging safety incidents
    if 'incidents' not in db.list_collection_names():
        db.create_collection('incidents')
        print("✅ Created 'incidents' collection for incident logging")
    else:
        print("ℹ️ 'incidents' collection already exists")
    
    # ============================================
    # CREATE INDEXES FOR PERFORMANCE
    # ============================================
    
    print("\n📊 Creating indexes for performance...")
    
    # Indexes for users
    db.users.create_index('username', unique=True)
    print("✅ Created unique index on 'users.username'")
    
    # Indexes for visual_records
    db.visual_records.create_index('uploaded_by')
    db.visual_records.create_index('upload_date')
    db.visual_records.create_index('status')
    print("✅ Created indexes on 'visual_records'")
    
    # Indexes for documents
    db.documents.create_index('uploaded_by')
    db.documents.create_index('upload_date')
    db.documents.create_index('filename')
    print("✅ Created indexes on 'documents'")
    
    # Indexes for knowledge_repository
    db.knowledge_repository.create_index('filename')
    db.knowledge_repository.create_index('upload_date')
    print("✅ Created indexes on 'knowledge_repository'")
    
    # Indexes for rag_embeddings
    db.rag_embeddings.create_index('chunk_id')
    db.rag_embeddings.create_index('metadata.filename')
    print("✅ Created indexes on 'rag_embeddings'")
    
    # Indexes for incidents
    db.incidents.create_index('timestamp')
    db.incidents.create_index('status')
    db.incidents.create_index('zone')
    db.incidents.create_index('user')
    print("✅ Created indexes on 'incidents'")
    
    print("\n✅ MongoDB setup complete!")
    print(f"📁 Database: {db.name}")
    print(f"📚 Collections: {db.list_collection_names()}")
    
    return db

# Run the setup
if __name__ == '__main__':
    setup_mongodb_collections()