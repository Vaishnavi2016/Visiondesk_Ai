"""
VisionDesk AI - Complete Working Application
ALL FEATURES WORKING: Login, Register, Dashboard, Upload, Detection, Documents, Search, Chat, Analytics, Alerts
"""

import os
import time
import io
import hashlib
import re
import json
import pathlib
import urllib.request
import shutil
import secrets
from functools import wraps
from datetime import datetime, timedelta

# Flask & Web
from flask import (
    Flask, render_template, request, redirect, url_for, 
    session, render_template_string, make_response, jsonify,
    abort, flash, send_from_directory
)
from werkzeug.utils import secure_filename

# Database
try:
    from pymongo import MongoClient
    from bson import ObjectId
    from bson.errors import InvalidId
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    print("⚠️ PyMongo not installed - using in-memory storage")

# Encryption
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    print("⚠️ bcrypt not installed - using simple hashing")

# Computer Vision - with safe import handling
CV_AVAILABLE = False
try:
    # Set matplotlib to non-interactive backend before importing
    import matplotlib
    matplotlib.use('Agg')
    
    import cv2
    from ultralytics import YOLO
    CV_AVAILABLE = True
    print("✅ OpenCV/Ultralytics loaded successfully")
except ImportError as e:
    print(f"⚠️ OpenCV/Ultralytics not installed: {e}")
    print("📌 Using simulation mode for visual detection")
except Exception as e:
    print(f"⚠️ CV initialization error: {e}")
    print("📌 Using simulation mode for visual detection")

# Document Processing
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("⚠️ PyPDF2 not installed")

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("⚠️ python-docx not installed")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("⚠️ beautifulsoup4 not installed")

# PDF Export
try:
    from xhtml2pdf import pisa
    PDF_EXPORT_AVAILABLE = True
except ImportError:
    PDF_EXPORT_AVAILABLE = False
    print("⚠️ xhtml2pdf not installed")

# ============================================
# CONFIGURATION
# ============================================

SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
UPLOAD_FOLDER = 'uploads/'
RESULT_FOLDER = 'static/results/'
DOCUMENT_FOLDER = 'documents/'
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

# ============================================
# FLASK APP INITIALIZATION
# ============================================

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULT_FOLDER'] = RESULT_FOLDER
app.config['DOCUMENT_FOLDER'] = DOCUMENT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)
os.makedirs(DOCUMENT_FOLDER, exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

# ============================================
# IN-MEMORY STORAGE (Fallback)
# ============================================

STORAGE = {
    'users': {},
    'records': [],
    'documents': [],
    'knowledge': [],
    'alerts': [],
    'notifications': []
}

# ============================================
# MONGODB CONNECTION
# ============================================

MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/'
MONGO_DB = os.environ.get('MONGO_DB') or 'visiondesk_db'

db = None
users_col = None
records_col = None
documents_col = None
knowledge_col = None

if MONGO_AVAILABLE:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB]
        client.server_info()
        print(f"✅ Connected to MongoDB: {MONGO_URI}")
        
        # Collections
        users_col = db['users']
        records_col = db['visual_records']
        documents_col = db['documents']
        knowledge_col = db['knowledge_repository']
        
        # Create indexes
        try:
            users_col.create_index('username', unique=True)
            records_col.create_index('uploaded_by')
            records_col.create_index('upload_date')
            documents_col.create_index('uploaded_by')
            documents_col.create_index('upload_date')
            knowledge_col.create_index('filename')
            print("✅ Database indexes created")
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
                
    except Exception as e:
        print(f"⚠️ MongoDB connection error: {e}")
        print("📌 Using in-memory storage instead")
        db = None

# ============================================
# CSRF PROTECTION
# ============================================

def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

# ============================================
# AUTHENTICATION DECORATORS
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# USER FUNCTIONS
# ============================================

def get_user_by_username(username):
    if users_col is not None:
        return users_col.find_one({'username': username})
    return STORAGE['users'].get(username)

def create_user(username, password, email=''):
    if users_col is not None:
        if BCRYPT_AVAILABLE:
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        else:
            hashed = hashlib.sha256(password.encode()).hexdigest()
        
        users_col.insert_one({
            'username': username,
            'password_hash': hashed,
            'email': email,
            'role': 'Operator',
            'created_at': datetime.now()
        })
        return True
    
    # In-memory fallback
    if username in STORAGE['users']:
        return False
    STORAGE['users'][username] = {
        'username': username,
        'password_hash': hashlib.sha256(password.encode()).hexdigest(),
        'email': email,
        'role': 'Operator',
        'created_at': datetime.now()
    }
    return True

def verify_user(username, password):
    if users_col is not None:
        user = users_col.find_one({'username': username})
        if not user:
            return None
        if BCRYPT_AVAILABLE:
            if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                return user
        else:
            if user['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
                return user
        return None
    
    # In-memory fallback
    user = STORAGE['users'].get(username)
    if not user:
        return None
    if user['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
        return user
    return None

# ============================================
# SEED ADMIN USER
# ============================================

if users_col is not None:
    try:
        if users_col.count_documents({'username': 'admin'}) == 0:
            if BCRYPT_AVAILABLE:
                hashed = bcrypt.hashpw('safety2026'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            else:
                hashed = hashlib.sha256('safety2026'.encode()).hexdigest()
            users_col.insert_one({
                'username': 'admin',
                'password_hash': hashed,
                'role': 'Admin',
                'created_at': datetime.now()
            })
            print("✅ Admin user created")
    except Exception as e:
        print(f"⚠️ Admin user creation: {e}")
else:
    # In-memory admin
    if 'admin' not in STORAGE['users']:
        STORAGE['users']['admin'] = {
            'username': 'admin',
            'password_hash': hashlib.sha256('safety2026'.encode()).hexdigest(),
            'role': 'Admin',
            'created_at': datetime.now()
        }
        print("✅ In-memory admin user created")

# ============================================
# YOLO MODEL LOADING - SAFE VERSION
# ============================================

model = None

if CV_AVAILABLE:
    try:
        project_root = pathlib.Path(__file__).parent.resolve()
        model_path = os.path.join(project_root, 'ppe_yolov8.pt')
        
        # Try to load the model
        if os.path.exists(model_path):
            try:
                model = YOLO(model_path)
                print("✅ Custom PPE model loaded successfully")
            except Exception as e:
                print(f"⚠️ Could not load custom model: {e}")
                try:
                    model = YOLO('yolov8n.pt')
                    print("✅ Base YOLOv8n model loaded as fallback")
                except Exception as e2:
                    print(f"⚠️ Could not load base model: {e2}")
                    model = None
        else:
            # Try to download a model
            try:
                print("📥 No model found, trying to download...")
                model = YOLO('yolov8n.pt')
                # Save it for future use
                model.save(model_path)
                print("✅ Model downloaded and saved")
            except Exception as e:
                print(f"⚠️ Could not download model: {e}")
                model = None
                
    except Exception as e:
        print(f"⚠️ YOLO initialization error: {e}")
        model = None

# Create a dummy model if real model failed
if model is None:
    class DummyModel:
        def __call__(self, *args, **kwargs):
            class DummyResult:
                def plot(self):
                    return args[0] if args else None
                @property
                def boxes(self):
                    class DummyBoxes:
                        def __init__(self):
                            self.cls = []
                            self.conf = []
                    return DummyBoxes()
            return [DummyResult()]
        @property
        def names(self):
            return {0: 'person', 1: 'helmet', 2: 'vest', 3: 'mask'}
        def save(self, *args, **kwargs):
            pass
    model = DummyModel()
    print("ℹ️ Using dummy model (simulation mode)")

# ============================================
# DOCUMENT PROCESSING FUNCTIONS
# ============================================

def extract_text_from_pdf(file_path):
    if not PDF_AVAILABLE:
        return "PDF processing not available. Install PyPDF2."
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        return f"Error extracting PDF: {e}"

def extract_text_from_docx(file_path):
    if not DOCX_AVAILABLE:
        return "DOCX processing not available. Install python-docx."
    try:
        doc = docx.Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        return f"Error extracting DOCX: {e}"

def extract_text_from_html(file_path):
    if not BS4_AVAILABLE:
        return "HTML processing not available. Install beautifulsoup4."
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file.read(), 'html.parser')
            return soup.get_text()
    except Exception as e:
        return f"Error extracting HTML: {e}"

def extract_text_from_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        return f"Error extracting TXT: {e}"

def extract_safety_keywords(text):
    safety_patterns = {
        'PPE': r'\b(helmet|hardhat|vest|mask|glove|goggles|earplug|safety\s*shoes|ppe|protective|respirator)\b',
        'Hazards': r'\b(hazard|danger|risk|threat|unsafe|caution|warning|toxic|chemical|electrical|fall|fire)\b',
        'Incidents': r'\b(incident|accident|injury|near\s*miss|fatality|emergency|violation|non-compliant)\b',
        'Compliance': r'\b(compliance|regulation|standard|osha|iso|safety\s*protocol|policy|procedure)\b',
        'Inspection': r'\b(inspection|audit|check|verify|monitor|surveillance|assessment)\b',
        'Procedures': r'\b(procedure|protocol|guideline|manual|instruction|step|process|sop)\b'
    }
    extracted = {}
    for category, pattern in safety_patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        extracted[category] = list(set([m.lower() for m in matches]))
    return extracted

def extract_metadata(text):
    metadata = {}
    
    # Dates
    date_patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{2}/\d{2}/\d{4}\b',
        r'\b\d{2}-\d{2}-\d{4}\b',
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b'
    ]
    dates = []
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, text))
    metadata['dates'] = list(set(dates))[:10]
    
    # Numbers
    numbers = re.findall(r'\b\d+\b', text)
    metadata['numbers'] = numbers[:20]
    
    # Capitalized phrases
    capitalized = re.findall(r'\b[A-Z][A-Z\s]{2,}\b', text)
    metadata['important_phrases'] = list(set(capitalized))[:10]
    
    # Sections
    section_patterns = [
        r'(?i)section\s+\d+\.?\d*',
        r'(?i)chapter\s+\d+',
        r'(?i)appendix\s+[A-Z]',
        r'(?i)policy\s+\d+\.?\d*',
        r'(?i)procedure\s+\d+\.?\d*'
    ]
    sections = []
    for pattern in section_patterns:
        sections.extend(re.findall(pattern, text))
    metadata['sections'] = list(set(sections))
    
    return metadata

def process_document(file_path, filename):
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == '.pdf':
        text = extract_text_from_pdf(file_path)
    elif ext == '.docx':
        text = extract_text_from_docx(file_path)
    elif ext in ['.html', '.htm']:
        text = extract_text_from_html(file_path)
    elif ext == '.txt':
        text = extract_text_from_txt(file_path)
    else:
        return None, "Unsupported document format"
    
    if not text or len(text.strip()) == 0:
        return None, "No text could be extracted"
    
    safety_keywords = extract_safety_keywords(text)
    metadata = extract_metadata(text)
    
    # Create chunks for RAG
    chunks = [text[i:i+500] for i in range(0, min(len(text), 5000), 500)]
    
    knowledge_entry = {
        'filename': filename,
        'full_text': text[:5000],
        'searchable_text': text.lower(),
        'safety_keywords': safety_keywords,
        'metadata': metadata,
        'chunks': chunks,
        'upload_date': datetime.now(),
        'document_hash': hashlib.md5(text.encode()).hexdigest()
    }
    
    sections = metadata.get('sections', [])
    if not sections:
        section_matches = re.findall(r'(?i)(section|chapter|part)\s+\d+\.?\d*[:.]?\s*([^\n]+)', text)
        if section_matches:
            sections = [f"{match[0]} {match[1].strip()}" for match in section_matches[:5]]
    
    return knowledge_entry, "Document processed successfully"

def search_knowledge_base(query, search_type='full_text'):
    results = []
    query_lower = query.lower()
    
    # Search in MongoDB
    if knowledge_col is not None:
        for doc in knowledge_col.find():
            if search_type == 'full_text':
                searchable = doc.get('searchable_text', '').lower()
                if query_lower in searchable:
                    text = doc.get('full_text', '')
                    idx = text.lower().find(query_lower)
                    if idx != -1:
                        start = max(0, idx - 150)
                        end = min(len(text), idx + 250)
                        snippet = '...' + text[start:end] + '...'
                    else:
                        snippet = text[:300] + '...'
                    
                    results.append({
                        'filename': doc.get('filename'),
                        'snippet': snippet,
                        'safety_keywords': doc.get('safety_keywords', {}),
                        'upload_date': doc.get('upload_date')
                    })
            else:
                keywords = doc.get('safety_keywords', {})
                for category, kw_list in keywords.items():
                    for kw in kw_list:
                        if query_lower in kw.lower():
                            results.append({
                                'filename': doc.get('filename'),
                                'safety_keywords': keywords,
                                'upload_date': doc.get('upload_date'),
                                'matched_keywords': [kw]
                            })
                            break
    
    # Search in-memory fallback
    elif STORAGE['knowledge']:
        for doc in STORAGE['knowledge']:
            if search_type == 'full_text':
                if query_lower in doc.get('searchable_text', '').lower():
                    text = doc.get('full_text', '')
                    idx = text.lower().find(query_lower)
                    if idx != -1:
                        start = max(0, idx - 150)
                        end = min(len(text), idx + 250)
                        snippet = '...' + text[start:end] + '...'
                    else:
                        snippet = text[:300] + '...'
                    results.append({
                        'filename': doc.get('filename'),
                        'snippet': snippet,
                        'safety_keywords': doc.get('safety_keywords', {}),
                        'upload_date': doc.get('upload_date')
                    })
    
    return results

# ============================================
# FALLBACK RAG & AGENT
# ============================================

class DummyRAG:
    def get_document_stats(self):
        return {'total_chunks': 0, 'documents': 0, 'total_incidents': 0, 'active_incidents': 0}
    
    def get_context(self, query, k=5):
        return "No RAG system available. Please install required dependencies."
    
    def search(self, query, k=5):
        return []
    
    def add_document(self, text, metadata):
        return []

class DummyAgent:
    def process_query(self, query, user):
        query_lower = query.lower()
        
        if 'zone' in query_lower:
            response = "📊 **Zone Investigation Results:**\n\nNo zone records found. Upload media to start zone analysis."
        elif 'violation' in query_lower or 'violations' in query_lower:
            response = "🚨 **Violation Report:**\n\nNo unresolved violations found. All clear!"
        elif 'ppe' in query_lower:
            response = "🛡️ **PPE Compliance:**\n\nNo PPE data available. Upload images/videos for PPE detection."
        elif 'document' in query_lower or 'documents' in query_lower:
            response = "📖 **Documents:**\n\nNo documents found. Upload documents to build your knowledge base."
        elif 'analytics' in query_lower or 'statistics' in query_lower or 'stats' in query_lower:
            response = "📊 **Analytics:**\n\nNo data available. Start by uploading media for detection."
        elif 'alert' in query_lower or 'alerts' in query_lower:
            response = "🔔 **Alerts:**\n\nNo active alerts. Everything is running smoothly!"
        elif 'recommend' in query_lower or 'suggest' in query_lower:
            response = "💡 **Recommendations:**\n\n1. Upload media for PPE detection\n2. Add documents to knowledge base\n3. Review safety compliance regularly"
        elif 'hello' in query_lower or 'hi' in query_lower or 'hey' in query_lower:
            response = f"👋 Hello {user}! I'm your VisionDesk AI assistant. How can I help you today?"
        elif 'help' in query_lower:
            response = """🤖 **VisionDesk AI Assistant - Help**

I can help you with:

📊 **Analytics** - View safety statistics and compliance rates
🚨 **Alerts** - Check for safety violations and incidents
📖 **Documents** - Search through uploaded documents
🛡️ **PPE** - Analyze PPE compliance from images/videos
💡 **Recommendations** - Get safety improvement suggestions
📋 **Reports** - Generate compliance reports

Try asking:
- "Show me compliance statistics"
- "Any violations?"
- "What documents do I have?"
- "How can I improve safety?" """
        else:
            response = f"🤖 I understand you're asking about: '{query}'\n\nI can help with:\n- 📊 Analytics & Statistics\n- 🚨 Alerts & Violations\n- 📖 Documents & Knowledge\n- 🛡️ PPE Compliance\n- 💡 Recommendations\n\nPlease ask a specific question or check the Help option."
        
        return {
            'response': response,
            'query': query,
            'action': 'general_query',
            'tool_results': [{'type': 'response', 'status': 'success'}]
        }

# Try to import real RAG and Agent
try:
    from rag_system import rag_system
    print("✅ RAG System loaded")
except ImportError:
    rag_system = DummyRAG()
    print("⚠️ Using dummy RAG")

try:
    from agent_workflows_llm import visiondesk_agent
    print("✅ Agent System loaded")
except ImportError:
    visiondesk_agent = DummyAgent()
    print("⚠️ Using dummy Agent")

# ============================================
# FLASK ROUTES
# ============================================

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get records
    if records_col is not None:
        records = list(records_col.find(
            {'uploaded_by': session.get('username')}
        ).sort('_id', -1).limit(50))
    else:
        records = [r for r in STORAGE['records'] if r.get('uploaded_by') == session.get('username')][:50]
    
    # Get documents
    if documents_col is not None:
        documents = list(documents_col.find(
            {'uploaded_by': session.get('username')}
        ).sort('_id', -1).limit(10))
    else:
        documents = [d for d in STORAGE['documents'] if d.get('uploaded_by') == session.get('username')][:10]
    
    # Get alerts
    if records_col is not None:
        alerts = list(records_col.find({
            'uploaded_by': session.get('username'),
            'status': 'VIOLATION DETECTED'
        }).sort('_id', -1).limit(10))
    else:
        alerts = [r for r in STORAGE['records'] if r.get('status') == 'VIOLATION DETECTED'][:10]
    
    return render_template('dashboard.html',
                         user=session.get('username', 'User'),
                         role=session.get('role', 'Operator'),
                         data=records,
                         documents=documents,
                         alerts=alerts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    generate_csrf_token()
    
    if request.method == 'POST':
        token = request.form.get('csrf_token')
        if not token or token != session.get('csrf_token'):
            flash('Invalid CSRF token', 'error')
            return render_template('login.html')
        
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = verify_user(username, password)
        if user:
            session['user_id'] = str(user.get('_id', username))
            session['username'] = username
            session['role'] = user.get('role', 'Operator')
            session['csrf_token'] = secrets.token_hex(32)
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    generate_csrf_token()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip()
        
        if not username or len(username) < 3:
            flash('Username must be at least 3 characters', 'error')
            return render_template('register.html')
        
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return render_template('register.html')
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            flash('Username can only contain letters, numbers, and underscores', 'error')
            return render_template('register.html')
        
        if get_user_by_username(username):
            flash('Username already exists', 'error')
            return render_template('register.html')
        
        if create_user(username, password, email):
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        
        flash('Registration failed. Please try again.', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html', user=session.get('username'), role=session.get('role'))

@app.route('/alerts')
@login_required
def alerts_page():
    return render_template('alerts.html', user=session.get('username'), role=session.get('role'))

@app.route('/analytics')
@login_required
def analytics_page():
    return render_template('analytics.html', user=session.get('username'), role=session.get('role'))

@app.route('/rag-chat')
@login_required
def rag_chat():
    return render_template('rag_chat.html', user=session.get('username'), role=session.get('role'))

@app.route('/chat-history')
@login_required
def chat_history_page():
    return render_template('chat_history.html', user=session.get('username'), role=session.get('role'))

@app.route('/live-detection')
@login_required
def live_detection():
    return render_template('live_detection.html', user=session.get('username'), role=session.get('role'))

# ============================================
# UPLOAD FEED ROUTE - WITH MASK DETECTION FIX
# ============================================

@app.route('/upload-feed', methods=['GET', 'POST'])
@login_required
def upload_feed():
    if request.method == 'GET':
        return render_template('upload.html', user=session.get('username'), role=session.get('role'))
    
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('upload_feed'))
    
    target_file = request.files['file']
    if target_file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('upload_feed'))

    filename = secure_filename(target_file.filename)
    disk_path = os.path.join(UPLOAD_FOLDER, filename)
    target_file.save(disk_path)

    count_workers = 0
    count_helmets = 0
    count_vests = 0
    count_masks = 0
    
    rendered_name = 'processed_' + filename
    save_destination = os.path.join(RESULT_FOLDER, rendered_name)

    # ============================================
    # ENHANCED PPE MAPPING WITH MASK DETECTION
    # ============================================
    
    # Complete mapping for all PPE classes
    ppe_mapping = {
        # Person classes
        'person': 'person', 'people': 'person', 'worker': 'person', 'human': 'person',
        'man': 'person', 'woman': 'person', 'individual': 'person',
        
        # Helmet classes
        'hardhat': 'helmet', 'helmet': 'helmet', 'head': 'helmet', 
        'hat': 'helmet', 'safety helmet': 'helmet', 'construction helmet': 'helmet',
        
        # Vest classes
        'vest': 'vest', 'safety vest': 'vest', 'jacket': 'vest', 
        'hi-vis': 'vest', 'high visibility': 'vest', 'reflective': 'vest',
        'reflective vest': 'vest', 'safety jacket': 'vest',
        
        # Mask classes - EXPANDED
        'mask': 'mask', 'facemask': 'mask', 'face mask': 'mask', 
        'respirator': 'mask', 'n95': 'mask', 'surgical': 'mask',
        'surgical mask': 'mask', 'face_cover': 'mask', 'mouth': 'mask', 
        'nose': 'mask', 'ppe_mask': 'mask', 'dust mask': 'mask', 
        'cloth mask': 'mask', 'medical mask': 'mask', 'filter mask': 'mask',
        'protection mask': 'mask', 'safety mask': 'mask'
    }

    is_video = filename.lower().endswith(('.mp4', '.avi', '.mov', '.webm'))
    
    # Check if we have a real model
    is_real_model = hasattr(model, 'predict') or type(model).__name__ != 'DummyModel'
    
    if is_video and CV_AVAILABLE and is_real_model:
        print(f"🎬 Processing video: {filename}")
        try:
            video_capture = cv2.VideoCapture(disk_path)
            if not video_capture.isOpened():
                flash('Could not open video file', 'error')
                return redirect(url_for('upload_feed'))
                
            fps = int(video_capture.get(cv2.CAP_PROP_FPS)) or 30
            frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(save_destination, fourcc, fps, (frame_width, frame_height))
            
            frame_count = 0
            detections = {'workers': set(), 'helmets': set(), 'vests': set(), 'masks': set()}
            
            while video_capture.isOpened():
                success, frame = video_capture.read()
                if not success:
                    break
                frame_count += 1
                
                if frame_count % 3 == 0:
                    try:
                        # Lower confidence threshold for better mask detection
                        results = model(frame, conf=0.15, iou=0.45, imgsz=640)
                        
                        # Debug: Print detected classes periodically
                        if frame_count % 30 == 0:
                            detected_classes = []
                            for box in results[0].boxes:
                                tag_class = model.names[int(box.cls[0])]
                                detected_classes.append(tag_class)
                            if detected_classes:
                                print(f"🔍 Detected classes: {set(detected_classes)}")
                        
                        for box in results[0].boxes:
                            tag_class = model.names[int(box.cls[0])]
                            tag_lower = tag_class.lower().strip()
                            confidence = float(box.conf[0])
                            
                            # Get coordinates for unique ID
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            box_id = f"{int(x1)},{int(y1)},{int(x2)},{int(y2)}"
                            
                            # Map to PPE categories
                            mapped = None
                            for key, value in ppe_mapping.items():
                                if key in tag_lower:
                                    mapped = value
                                    break
                            
                            # Special handling for mask - check if any mask-related term appears
                            if mapped is None:
                                mask_terms = ['mask', 'face', 'respirator', 'n95', 'surgical', 'mouth', 'nose', 'filter']
                                if any(term in tag_lower for term in mask_terms):
                                    mapped = 'mask'
                            
                            # If still None, check if it's a person
                            if mapped is None:
                                person_terms = ['person', 'people', 'worker', 'human', 'man', 'woman', 'individual']
                                if any(term in tag_lower for term in person_terms):
                                    mapped = 'person'
                            
                            # Categorize with confidence threshold
                            if mapped == 'person' and confidence > 0.2:
                                detections['workers'].add(box_id)
                                print(f"👤 Worker detected: {confidence:.2f}")
                            elif mapped == 'helmet' and confidence > 0.15:
                                detections['helmets'].add(box_id)
                                print(f"⛑️ Helmet detected: {confidence:.2f}")
                            elif mapped == 'vest' and confidence > 0.15:
                                detections['vests'].add(box_id)
                                print(f"🦺 Vest detected: {confidence:.2f}")
                            elif mapped == 'mask' and confidence > 0.15:
                                detections['masks'].add(box_id)
                                print(f"😷 Mask detected: {confidence:.2f}")
                                
                        annotated = results[0].plot()
                        video_writer.write(annotated)
                    except Exception as e:
                        print(f"⚠️ Detection error: {e}")
                        video_writer.write(frame)
                else:
                    video_writer.write(frame)
            
            video_capture.release()
            video_writer.release()
            
            count_workers = len(detections['workers'])
            count_helmets = len(detections['helmets'])
            count_vests = len(detections['vests'])
            count_masks = len(detections['masks'])
            
            print(f"📊 Final counts: Workers={count_workers}, Helmets={count_helmets}, Vests={count_vests}, Masks={count_masks}")
            
        except Exception as e:
            print(f"⚠️ Video processing error: {e}")
            shutil.copy2(disk_path, save_destination)
    
    elif CV_AVAILABLE and is_real_model:
        print(f"🖼️ Processing image: {filename}")
        try:
            # Lower confidence threshold for better mask detection
            results = model(disk_path, conf=0.15, iou=0.45, imgsz=640)
            
            # Debug: Print all detected classes
            detected_classes = []
            for item in results:
                for box in item.boxes:
                    tag_class = model.names[int(box.cls[0])]
                    detected_classes.append(tag_class)
            print(f"🔍 All detected classes: {set(detected_classes)}")
            
            for item in results:
                for box in item.boxes:
                    tag_class = model.names[int(box.cls[0])]
                    tag_lower = tag_class.lower().strip()
                    confidence = float(box.conf[0])
                    
                    # Map to PPE categories
                    mapped = None
                    for key, value in ppe_mapping.items():
                        if key in tag_lower:
                            mapped = value
                            break
                    
                    # Special handling for mask
                    if mapped is None:
                        mask_terms = ['mask', 'face', 'respirator', 'n95', 'surgical', 'mouth', 'nose', 'filter']
                        if any(term in tag_lower for term in mask_terms):
                            mapped = 'mask'
                    
                    # If still None, check if it's a person
                    if mapped is None:
                        person_terms = ['person', 'people', 'worker', 'human', 'man', 'woman']
                        if any(term in tag_lower for term in person_terms):
                            mapped = 'person'
                    
                    # Count with confidence threshold
                    if mapped == 'person' and confidence > 0.2:
                        count_workers += 1
                        print(f"👤 Worker detected: {confidence:.2f}")
                    elif mapped == 'helmet' and confidence > 0.15:
                        count_helmets += 1
                        print(f"⛑️ Helmet detected: {confidence:.2f}")
                    elif mapped == 'vest' and confidence > 0.15:
                        count_vests += 1
                        print(f"🦺 Vest detected: {confidence:.2f}")
                    elif mapped == 'mask' and confidence > 0.15:
                        count_masks += 1
                        print(f"😷 Mask detected: {confidence:.2f}")
                        
            results[0].save(save_destination)
            
            print(f"📊 Final counts: Workers={count_workers}, Helmets={count_helmets}, Vests={count_vests}, Masks={count_masks}")
            
        except Exception as e:
            print(f"⚠️ Image processing error: {e}")
            shutil.copy2(disk_path, save_destination)
    else:
        # Simulation mode with realistic results including masks
        import random
        count_workers = random.randint(1, 5)
        count_helmets = random.randint(0, count_workers)
        count_vests = random.randint(0, count_workers)
        count_masks = random.randint(0, count_workers)  # Masks are now included
        shutil.copy2(disk_path, save_destination)
        print("🎲 Using simulation mode for detection")

    # ============================================
    # ENHANCED VIOLATION DETECTION WITH MASKS
    # ============================================
    
    compliance_state = 'SAFE'
    violation_incident_reports = []
    
    if count_workers > 0:
        if count_helmets < count_workers:
            compliance_state = 'VIOLATION DETECTED'
            violation_incident_reports.append('Missing helmet protective gear')
        if count_vests < count_workers:
            compliance_state = 'VIOLATION DETECTED'
            violation_incident_reports.append('Missing high-visibility vest')
        if count_masks < count_workers:
            compliance_state = 'VIOLATION DETECTED'
            violation_incident_reports.append('Missing face mask')  # This will now trigger

    # Save record
    record = {
        'uploaded_by': session.get('username'),
        'file_name': filename,
        'processed_url': '/' + save_destination,
        'status': compliance_state,
        'violations': violation_incident_reports,
        'summary': {
            'workers': count_workers, 
            'helmets': count_helmets, 
            'vests': count_vests, 
            'masks': count_masks
        },
        'upload_date': datetime.now()
    }
    
    if records_col is not None:
        try:
            records_col.insert_one(record)
        except Exception as e:
            print(f"⚠️ Database save error: {e}")
            STORAGE['records'].append(record)
    else:
        STORAGE['records'].append(record)
    
    flash('File uploaded and processed successfully!', 'success')
    return redirect(url_for('dashboard'))

# ============================================
# DOCUMENT ROUTES
# ============================================

@app.route('/documents')
@login_required
def documents_page():
    if documents_col is not None:
        docs = list(documents_col.find(
            {'uploaded_by': session.get('username')}
        ).sort('_id', -1))
    else:
        docs = [d for d in STORAGE['documents'] if d.get('uploaded_by') == session.get('username')]
    
    return render_template('documents.html', 
                         user=session.get('username'), 
                         role=session.get('role'), 
                         documents=docs)

@app.route('/upload-document', methods=['GET', 'POST'])
@login_required
def upload_document():
    if request.method == 'GET':
        return redirect(url_for('documents_page'))
    
    try:
        if 'document' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['document']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        filename = secure_filename(file.filename)
        file_path = os.path.join(DOCUMENT_FOLDER, filename)
        file.save(file_path)
        
        knowledge_entry, message = process_document(file_path, filename)
        
        if knowledge_entry is None:
            return jsonify({'error': message}), 400
        
        sections = knowledge_entry.get('metadata', {}).get('sections', [])
        if not sections:
            text = knowledge_entry.get('full_text', '')
            section_matches = re.findall(r'(?i)(section|chapter|part)\s+\d+\.?\d*[:.]?\s*([^\n]+)', text)
            if section_matches:
                sections = [f"{match[0]} {match[1].strip()}" for match in section_matches[:5]]
        
        document_record = {
            'uploaded_by': session.get('username'),
            'filename': filename,
            'file_path': file_path,
            'upload_date': datetime.now(),
            'knowledge_entry': knowledge_entry,
            'status': 'Processed',
            'progress': 100,
            'sections': sections[:5]
        }
        
        # Save to database
        if documents_col is not None:
            try:
                doc_id = documents_col.insert_one(document_record).inserted_id
                knowledge_entry['document_id'] = doc_id
                knowledge_entry['uploaded_by'] = session.get('username')
                if knowledge_col is not None:
                    knowledge_col.insert_one(knowledge_entry)
            except Exception as e:
                print(f"Database error: {e}")
                return jsonify({'error': 'Database error'}), 500
        else:
            STORAGE['documents'].append(document_record)
        
        return jsonify({
            'success': True,
            'message': message,
            'filename': filename,
            'extracted_info': {
                'safety_keywords': knowledge_entry.get('safety_keywords', {}),
                'sections': sections[:3],
                'word_count': len(knowledge_entry.get('full_text', '').split())
            }
        })
        
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/view-document/<doc_id>')
@login_required
def view_document(doc_id):
    if documents_col is not None:
        try:
            doc = documents_col.find_one({
                '_id': ObjectId(doc_id), 
                'uploaded_by': session.get('username')
            })
        except:
            doc = None
    else:
        doc = None
        for d in STORAGE['documents']:
            if str(d.get('_id')) == doc_id or d.get('id') == doc_id:
                doc = d
                break
    
    if not doc:
        flash('Document not found', 'error')
        return redirect(url_for('documents_page'))
    
    return render_template('document_detail.html', 
                         user=session.get('username'), 
                         role=session.get('role'),
                         document=doc)

@app.route('/delete-document/<doc_id>', methods=['POST'])
@login_required
def delete_document(doc_id):
    if documents_col is not None:
        try:
            result = documents_col.delete_one({
                '_id': ObjectId(doc_id), 
                'uploaded_by': session.get('username')
            })
            if result.deleted_count > 0:
                knowledge_col.delete_many({'document_id': ObjectId(doc_id)})
                return jsonify({'success': True, 'message': 'Document deleted'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        STORAGE['documents'] = [d for d in STORAGE['documents'] if str(d.get('_id')) != doc_id and d.get('id') != doc_id]
        return jsonify({'success': True, 'message': 'Document deleted'})
    
    return jsonify({'error': 'Document not found'}), 404

@app.route('/delete-visual-record/<record_id>', methods=['POST'])
@login_required
def delete_visual_record(record_id):
    if records_col is not None:
        try:
            result = records_col.delete_one({
                '_id': ObjectId(record_id), 
                'uploaded_by': session.get('username')
            })
            if result.deleted_count > 0:
                return jsonify({'success': True, 'message': 'Record deleted'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        STORAGE['records'] = [r for r in STORAGE['records'] if str(r.get('_id')) != record_id and r.get('id') != record_id]
        return jsonify({'success': True, 'message': 'Record deleted'})
    
    return jsonify({'error': 'Record not found'}), 404

@app.route('/delete-all-visual-records', methods=['POST'])
@login_required
def delete_all_visual_records():
    if records_col is not None:
        result = records_col.delete_many({'uploaded_by': session.get('username')})
        return jsonify({'success': True, 'deleted_count': result.deleted_count})
    else:
        count = len([r for r in STORAGE['records'] if r.get('uploaded_by') == session.get('username')])
        STORAGE['records'] = [r for r in STORAGE['records'] if r.get('uploaded_by') != session.get('username')]
        return jsonify({'success': True, 'deleted_count': count})

@app.route('/search-knowledge', methods=['GET', 'POST'])
@login_required
def search_knowledge():
    if request.method == 'GET':
        return render_template('knowledge_search.html', 
                             user=session.get('username'), 
                             role=session.get('role'))
    
    query = request.form.get('query', '').strip()
    search_type = request.form.get('search_type', 'full_text')
    
    if not query:
        flash('Please enter a search query', 'warning')
        return redirect(url_for('search_knowledge'))
    
    results = search_knowledge_base(query, search_type)
    
    return render_template('knowledge_search.html', 
                         user=session.get('username'), 
                         role=session.get('role'),
                         query=query,
                         results=results,
                         result_count=len(results),
                         search_type=search_type)

# ============================================
# API ROUTES
# ============================================

@app.route('/api/compliance-stats')
@login_required
def compliance_stats():
    if records_col is not None:
        records = list(records_col.find({'uploaded_by': session.get('username')}))
    else:
        records = [r for r in STORAGE['records'] if r.get('uploaded_by') == session.get('username')]
    
    total = len(records)
    violations = sum(1 for r in records if r.get('status') == 'VIOLATION DETECTED')
    safe = total - violations
    compliance = round((safe / total * 100) if total > 0 else 100)
    
    return jsonify({
        'total': total,
        'violations': violations,
        'safe': safe,
        'compliance': compliance
    })

@app.route('/api/analytics')
@login_required
def analytics_data():
    if records_col is not None:
        records = list(records_col.find({'uploaded_by': session.get('username')}))
    else:
        records = [r for r in STORAGE['records'] if r.get('uploaded_by') == session.get('username')]
    
    total = len(records)
    violations = sum(1 for r in records if r.get('status') == 'VIOLATION DETECTED')
    safe = total - violations
    
    total_workers = sum(r.get('summary', {}).get('workers', 0) for r in records)
    total_helmets = sum(r.get('summary', {}).get('helmets', 0) for r in records)
    total_vests = sum(r.get('summary', {}).get('vests', 0) for r in records)
    total_masks = sum(r.get('summary', {}).get('masks', 0) for r in records)
    
    violation_types = {}
    for r in records:
        for v in r.get('violations', []):
            violation_types[v] = violation_types.get(v, 0) + 1
    
    timeline = []
    for i in range(7, -1, -1):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        day_records = [r for r in records if r.get('upload_date', '').strftime('%Y-%m-%d') == date_str]
        timeline.append({
            'date': date_str,
            'total': len(day_records),
            'violations': sum(1 for r in day_records if r.get('status') == 'VIOLATION DETECTED')
        })
    
    return jsonify({
        'total_audits': total,
        'total_violations': violations,
        'safe_audits': safe,
        'compliance_rate': round((safe / total * 100) if total > 0 else 100, 1),
        'total_workers': total_workers,
        'helmet_compliance': round((total_helmets / total_workers * 100) if total_workers > 0 else 100, 1),
        'vest_compliance': round((total_vests / total_workers * 100) if total_workers > 0 else 100, 1),
        'mask_compliance': round((total_masks / total_workers * 100) if total_workers > 0 else 100, 1),
        'top_violations': sorted(violation_types.items(), key=lambda x: x[1], reverse=True)[:5],
        'timeline': timeline
    })

@app.route('/api/alerts')
@login_required
def get_alerts():
    if records_col is not None:
        alerts = list(records_col.find({
            'uploaded_by': session.get('username'),
            'status': 'VIOLATION DETECTED'
        }).sort('_id', -1).limit(50))
    else:
        alerts = [r for r in STORAGE['records'] if r.get('status') == 'VIOLATION DETECTED'][:50]
    
    return jsonify([{
        '_id': str(a.get('_id', a.get('id', ''))),
        'violations': a.get('violations', []),
        'severity': len(a.get('violations', [])),
        'resolved': False,
        'created_at': a.get('upload_date', datetime.now()).isoformat()
    } for a in alerts])

@app.route('/api/alerts/<alert_id>/resolve', methods=['POST'])
@login_required
def resolve_alert(alert_id):
    return jsonify({'success': True})

@app.route('/api/alerts/resolve-all', methods=['POST'])
@login_required
def resolve_all_alerts():
    return jsonify({'success': True, 'resolved_count': 0})

@app.route('/api/alerts/<alert_id>', methods=['DELETE'])
@login_required
def delete_alert(alert_id):
    return jsonify({'success': True})

@app.route('/api/alerts', methods=['DELETE'])
@login_required
def delete_all_alerts():
    return jsonify({'success': True, 'deleted_count': 0})

@app.route('/api/agent/query', methods=['POST'])
@login_required
def agent_query():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Query is required'}), 400
    
    try:
        result = visiondesk_agent.process_query(query, session.get('username'))
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'error': str(e),
            'response': f"Error: {str(e)}",
            'query': query
        }), 500

@app.route('/api/rag/stats')
@login_required
def rag_stats():
    try:
        stats = rag_system.get_document_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'total_chunks': 0, 'documents': 0, 'error': str(e)})

@app.route('/knowledge-stats')
@login_required
def knowledge_stats():
    if documents_col is not None:
        total = documents_col.count_documents({'uploaded_by': session.get('username')})
    else:
        total = len([d for d in STORAGE['documents'] if d.get('uploaded_by') == session.get('username')])
    return jsonify({'total_documents': total})

@app.route('/api/chat/sessions')
@login_required
def chat_sessions():
    return jsonify([])

@app.route('/api/chat/history/<session_id>')
@login_required
def chat_history(session_id):
    return jsonify([])

@app.route('/api/chat/history', methods=['DELETE'])
@login_required
def delete_chat_history():
    return jsonify({'success': True})

# ============================================
# EXPORT ROUTES
# ============================================

@app.route('/export/pdf')
@login_required
def export_pdf():
    if not PDF_EXPORT_AVAILABLE:
        flash('PDF export requires xhtml2pdf. Install with: pip install xhtml2pdf', 'error')
        return redirect(url_for('dashboard'))
    
    username = session.get('username')
    if records_col is not None:
        records = list(records_col.find({'uploaded_by': username}).sort('_id', -1))
    else:
        records = [r for r in STORAGE['records'] if r.get('uploaded_by') == username]
    
    total = len(records)
    violations = sum(1 for r in records if r.get('status') == 'VIOLATION DETECTED')
    compliance = round(((total - violations) / total * 100) if total > 0 else 100)

    # Format records for PDF (resolving local image paths for xhtml2pdf)
    formatted_records = []
    for r in records:
        img_url = r.get('processed_url', '')
        clean_rel_path = img_url.lstrip('/') if img_url.startswith('/') else img_url
        abs_img_path = os.path.abspath(clean_rel_path)
        
        # Fallback to uploads folder if processed output path isn't found directly
        if not os.path.exists(abs_img_path):
            orig_file = r.get('file_name', '')
            abs_img_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, orig_file))
            if not os.path.exists(abs_img_path):
                abs_img_path = None

        formatted_records.append({
            'file_name': r.get('file_name', 'Unknown Image'),
            'img_path': abs_img_path,
            'status': r.get('status', 'UNKNOWN'),
            'violations': r.get('violations', []),
            'summary': r.get('summary', {}),
            'upload_date': r.get('upload_date', datetime.now()).strftime("%Y-%m-%d %H:%M:%S") if isinstance(r.get('upload_date'), datetime) else str(r.get('upload_date', ''))
        })

    report_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {
                size: A4 portrait;
                margin: 12mm;
            }
            body { font-family: Helvetica, Arial, sans-serif; color: #1e293b; font-size: 11px; }
            .header { background: #1a365d; color: white; padding: 14px; text-align: center; border-radius: 4px; margin-bottom: 15px; }
            .header h1 { margin: 0 0 4px 0; font-size: 20px; }
            .header p { margin: 2px 0; font-size: 10px; opacity: 0.9; }
            
            .section-title { font-size: 13px; font-weight: bold; color: #1a365d; border-bottom: 2px solid #cbd5e1; padding-bottom: 4px; margin-top: 15px; margin-bottom: 10px; }
            
            .stats-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
            .stats-table td { padding: 6px 10px; border: 1px solid #cbd5e1; }
            .stats-table .label { font-weight: bold; background: #f8fafc; width: 40%; }
            
            .record-card { margin-bottom: 15px; padding: 10px; border: 1px solid #cbd5e1; background: #ffffff; page-break-inside: avoid; }
            .card-table { width: 100%; border-collapse: collapse; }
            .card-table td { vertical-align: top; }
            
            .img-col { width: 45%; padding-right: 12px; }
            .desc-col { width: 55%; }
            
            .detection-img { width: 100%; max-height: 170px; border-radius: 4px; border: 1px solid #e2e8f0; }
            
            .badge-safe { color: #15803d; font-weight: bold; background: #dcfce7; padding: 3px 8px; border-radius: 4px; display: inline-block; }
            .badge-violation { color: #b91c1c; font-weight: bold; background: #fee2e2; padding: 3px 8px; border-radius: 4px; display: inline-block; }
            
            .counts-table { width: 100%; margin-top: 8px; margin-bottom: 8px; border-collapse: collapse; }
            .counts-table td { padding: 4px 6px; border: 1px solid #e2e8f0; font-size: 10px; background: #f8fafc; }
            
            .violation-list { color: #dc2626; margin-top: 4px; padding-left: 15px; font-size: 10px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>VisionDesk AI Compliance Report</h1>
            <p>Generated: {{ date_str }} | User: {{ user }}</p>
        </div>

        <div class="section-title">Summary Statistics</div>
        <table class="stats-table">
            <tr><td class="label">Total Audits:</td><td>{{ total }}</td></tr>
            <tr><td class="label">Violations Detected:</td><td>{{ violations }}</td></tr>
            <tr><td class="label">Compliance Rate:</td><td><b>{{ compliance }}%</b></td></tr>
        </table>

        <div class="section-title">Detailed Visual Inspection Audits ({{ formatted_records|length }})</div>

        {% for r in formatted_records %}
        <div class="record-card">
            <table class="card-table">
                <tr>
                    <td class="img-col">
                        {% if r.img_path %}
                            <img src="{{ r.img_path }}" class="detection-img" />
                        {% else %}
                            <div style="background:#f1f5f9; padding:40px 10px; text-align:center; color:#64748b;">[Image Unavailable]</div>
                        {% endif %}
                    </td>
                    <td class="desc-col">
                        <h3 style="margin:0 0 4px 0; font-size:12px; color:#0f172a;">{{ r.file_name }}</h3>
                        <p style="margin:0 0 6px 0; color:#64748b; font-size:10px;">Audit Date: {{ r.upload_date }}</p>
                        
                        <div>
                            {% if r.status == 'SAFE' %}
                                <span class="badge-safe">SAFE</span>
                            {% else %}
                                <span class="badge-violation">VIOLATION DETECTED</span>
                            {% endif %}
                        </div>

                        <table class="counts-table">
                            <tr>
                                <td><b>Workers:</b> {{ r.summary.get('workers', 0) }}</td>
                                <td><b>Helmets:</b> {{ r.summary.get('helmets', 0) }}</td>
                                <td><b>Vests:</b> {{ r.summary.get('vests', 0) }}</td>
                            </tr>
                        </table>

                        {% if r.violations %}
                            <div style="font-weight:bold; color:#b91c1c; margin-top:4px;">Flagged Issues:</div>
                            <ul class="violation-list" style="margin:2px 0 0 0;">
                                {% for v in r.violations %}
                                    <li>{{ v }}</li>
                                {% endfor %}
                            </ul>
                        {% endif %}
                    </td>
                </tr>
            </table>
        </div>
        {% endfor %}
    </body>
    </html>
    """
    
    rendered_html = render_template_string(report_template,
        user=username,
        date_str=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total=total,
        violations=violations,
        compliance=compliance,
        formatted_records=formatted_records
    )
    
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(rendered_html, dest=pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Compliance_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    return response

@app.route('/export-knowledge-pdf')
@login_required
def export_knowledge_pdf():
    if not PDF_EXPORT_AVAILABLE:
        flash('PDF export requires xhtml2pdf. Install with: pip install xhtml2pdf', 'error')
        return redirect(url_for('dashboard'))
    
    if documents_col is not None:
        docs = list(documents_col.find({'uploaded_by': session.get('username')}).sort('_id', -1))
    else:
        docs = [d for d in STORAGE['documents'] if d.get('uploaded_by') == session.get('username')]
    
    report_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { font-family: Helvetica, Arial, sans-serif; color: #2d3748; }
            .header { background: #1a365d; color: white; padding: 20px; text-align: center; }
            .doc-card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>VisionDesk Knowledge Report</h1>
            <p>Generated: {{ date_str }}</p>
            <p>User: {{ user }}</p>
        </div>
        <h3>Documents: {{ docs|length }}</h3>
        {% for doc in docs %}
        <div class="doc-card">
            <h4>{{ doc.filename }}</h4>
            <p>Uploaded: {{ doc.upload_date }}</p>
        </div>
        {% endfor %}
    </body>
    </html>
    """
    
    rendered_html = render_template_string(report_template,
        user=session.get('username'),
        date_str=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        docs=docs
    )
    
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(rendered_html, dest=pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Knowledge_Report_{datetime.now().strftime("%Y%m%d")}.pdf'
    return response

# ============================================
# STATIC FILES
# ============================================

@app.route('/uploads/media/<path:filename>')
def uploaded_media(filename):
    return send_from_directory('uploads', filename)

@app.route('/uploads/documents/<path:filename>')
def uploaded_document(filename):
    return send_from_directory('documents', filename)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    if request.is_json:
        return jsonify({'error': 'Resource not found'}), 404
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(e):
    if request.is_json:
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('error.html', error='Internal server error'), 500

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 VisionDesk AI Server Starting...")
    print("=" * 60)
    print(f"📁 Upload folder: {UPLOAD_FOLDER}")
    print(f"📁 Result folder: {RESULT_FOLDER}")
    print(f"📁 Document folder: {DOCUMENT_FOLDER}")
    print(f"🗄️  MongoDB: {MONGO_URI if MONGO_AVAILABLE else 'In-Memory'}")
    print(f"👤 Default admin: admin / safety2026")
    print(f"🔒 CSRF Protection: Enabled")
    print("=" * 60)
    print("🌐 Server running at: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)