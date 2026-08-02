# ============================================
# COMPLETE APP.PY - FULLY WORKING VERSION
# ============================================

import os
import time
import datetime
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
from pymongo import MongoClient
from bson import ObjectId
from bson.errors import InvalidId

# Encryption
import bcrypt

# Computer Vision
import cv2
from ultralytics import YOLO

# Document Processing
import PyPDF2
import docx
from bs4 import BeautifulSoup

# PDF Export
from xhtml2pdf import pisa

# ============================================
# CONFIGURATION
# ============================================

SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
UPLOAD_FOLDER = 'uploads/'
RESULT_FOLDER = 'static/results/'
DOCUMENT_FOLDER = 'documents/'
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/'
MONGO_DB = os.environ.get('MONGO_DB') or 'visiondesk_db'

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

# ============================================
# MONGODB CONNECTION
# ============================================

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]
    client.server_info()
    print(f"✅ Connected to MongoDB: {MONGO_URI}")
except Exception as e:
    print(f"⚠️ MongoDB connection error: {e}")
    db = None

# Collections
if db is not None:
    users_col = db['users']
    records_col = db['visual_records']
    documents_col = db['documents']
    knowledge_col = db['knowledge_repository']
    notifications_col = db['notifications']
    incidents_col = db['incidents']
else:
    users_col = None
    records_col = None
    documents_col = None
    knowledge_col = None
    notifications_col = None
    incidents_col = None

# ============================================
# DATABASE SETUP
# ============================================

def setup_database():
    if db is None:
        return
    
    collections = ['users', 'visual_records', 'documents', 
                   'knowledge_repository', 'notifications', 'incidents']
    
    for col_name in collections:
        try:
            if col_name not in db.list_collection_names():
                db.create_collection(col_name)
                print(f"✅ Created collection: {col_name}")
        except Exception as e:
            print(f"⚠️ Could not create collection {col_name}: {e}")

setup_database()

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
# YOLO MODEL LOADING
# ============================================

project_root = pathlib.Path(__file__).parent.resolve()
model_path = os.path.join(project_root, 'ppe_yolov8.pt')

def download_ppe_model():
    try:
        model_urls = [
            "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n-ppe.pt",
            "https://huggingface.co/ultralytics/yolov8/resolve/main/yolov8n.pt"
        ]
        for url in model_urls:
            try:
                print(f"📥 Attempting to download from: {url}")
                urllib.request.urlretrieve(url, model_path)
                print("✅ Model downloaded successfully")
                return YOLO(model_path)
            except Exception as e:
                print(f"⚠️ Failed to download from {url}: {e}")
                continue
        return None
    except Exception as e:
        print(f"⚠️ Could not download PPE model: {e}")
        return None

model = None
try:
    if os.path.exists(model_path):
        model = YOLO(model_path)
        print("✅ Custom PPE model loaded successfully")
    else:
        print("⚠️ Custom model not found, attempting to download...")
        model = download_ppe_model()
        if model is None:
            print("📥 Using base YOLOv8n model...")
            model = YOLO('yolov8n.pt')
            print("✅ Base YOLOv8n model loaded successfully")
except Exception as e:
    print(f"⚠️ Could not load YOLO model: {e}")
    model = None

# ============================================
# SEED ADMIN USER
# ============================================

if db is not None and users_col is not None:
    try:
        if users_col.count_documents({'username': 'admin'}) == 0:
            passwd_bytes = 'safety2026'.encode('utf-8')
            salt_hash = bcrypt.gensalt()
            hashed_value = bcrypt.hashpw(passwd_bytes, salt_hash)
            users_col.insert_one({
                'username': 'admin',
                'password_hash': hashed_value.decode('utf-8'),
                'role': 'Admin',
                'created_at': datetime.now()
            })
            print("✅ Admin user created")
    except Exception as e:
        print(f"⚠️ Admin user creation: {e}")

# ============================================
# RAG & AGENT SYSTEM (FALLBACK)
# ============================================

try:
    from rag_system import rag_system
    print("✅ RAG System loaded successfully")
except ImportError as e:
    print(f"⚠️ RAG System not found: {e}")
    class DummyRAG:
        def get_document_stats(self): 
            return {'total_chunks': 0, 'documents': 0, 'total_incidents': 0, 'active_incidents': 0}
        def get_context(self, q, k=5): 
            return "No RAG system available."
        def search(self, q, k=5): 
            return []
        def add_document(self, text, metadata): 
            return []
    rag_system = DummyRAG()

try:
    from agent_workflows import visiondesk_agent
    print("✅ Agent System loaded successfully")
except ImportError as e:
    print(f"⚠️ Agent System not found: {e}")
    class DummyAgent:
        def process_query(self, q, u):
            return {
                'response': f"I'm a basic assistant. Your query: '{q}'\n\nPlease install required dependencies.",
                'query': q,
                'action': 'fallback',
                'tool_results': [{'type': 'fallback', 'status': 'error'}]
            }
    visiondesk_agent = DummyAgent()

# ============================================
# DOCUMENT PROCESSING FUNCTIONS
# ============================================

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
    return text

def extract_text_from_docx(file_path):
    text = ""
    try:
        doc = docx.Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    except Exception as e:
        print(f"Error extracting DOCX text: {e}")
    return text

def extract_text_from_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error extracting TXT text: {e}")
        return ""

def extract_text_from_html(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file.read(), 'html.parser')
            return soup.get_text()
    except Exception as e:
        print(f"Error extracting HTML text: {e}")
        return ""

def extract_safety_keywords(text):
    safety_patterns = {
        'hazards': r'\b(hazard|danger|risk|threat|unsafe|caution|warning)\b',
        'ppe': r'\b(helmet|hardhat|vest|mask|glove|goggles|earplug|safety shoes|ppe|protective)\b',
        'incidents': r'\b(incident|accident|injury|near miss|fatality|emergency|violation|non-compliant)\b',
        'compliance': r'\b(compliance|regulation|standard|osha|iso|safety protocol|policy|procedure)\b',
        'inspection': r'\b(inspection|audit|check|verify|monitor|surveillance|assessment)\b',
        'procedures': r'\b(procedure|protocol|guideline|manual|instruction|step|process)\b'
    }
    extracted_info = {}
    for category, pattern in safety_patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        extracted_info[category] = list(set([m.lower() for m in matches]))
    return extracted_info

def extract_metadata(text):
    metadata = {}
    date_patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{2}/\d{2}/\d{4}\b',
        r'\b\d{2}-\d{2}-\d{4}\b',
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b'
    ]
    dates = []
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, text))
    metadata['dates'] = list(set(dates))
    numbers = re.findall(r'\b\d+\b', text)
    metadata['numbers'] = numbers[:20]
    capitalized = re.findall(r'\b[A-Z][A-Z\s]{2,}\b', text)
    metadata['important_phrases'] = list(set(capitalized))[:10]
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
    file_extension = os.path.splitext(filename)[1].lower()
    
    if file_extension == '.pdf':
        text = extract_text_from_pdf(file_path)
    elif file_extension == '.docx':
        text = extract_text_from_docx(file_path)
    elif file_extension == '.txt':
        text = extract_text_from_txt(file_path)
    elif file_extension in ['.html', '.htm']:
        text = extract_text_from_html(file_path)
    else:
        return None, "Unsupported document format"
    
    if not text or len(text.strip()) == 0:
        return None, "No text could be extracted from the document"
    
    safety_keywords = extract_safety_keywords(text)
    metadata = extract_metadata(text)
    
    knowledge_entry = {
        'filename': filename,
        'full_text': text[:5000],
        'searchable_text': text.lower(),
        'safety_keywords': safety_keywords,
        'metadata': metadata,
        'upload_date': datetime.now(),
        'document_hash': hashlib.md5(text.encode()).hexdigest()
    }
    
    try:
        metadata = {
            'filename': filename,
            'uploaded_by': session.get('username', 'unknown'),
            'upload_date': datetime.now().isoformat()
        }
        rag_system.add_document(text, metadata)
        knowledge_entry['rag_indexed'] = True
        print(f"✅ Document indexed for RAG: {filename}")
    except Exception as e:
        print(f"⚠️ RAG indexing failed: {e}")
        knowledge_entry['rag_indexed'] = False
    
    return knowledge_entry, "Document processed successfully"

def search_knowledge_base(query, search_type='full_text'):
    results = []
    query_lower = query.lower()
    
    if db is None or knowledge_col is None:
        return results
    
    if search_type == 'full_text':
        for doc in knowledge_col.find():
            searchable_text = doc.get('searchable_text', '').lower()
            if query_lower in searchable_text:
                text = doc.get('full_text', '')
                snippets = []
                start_pos = 0
                while True:
                    index = text.lower().find(query_lower, start_pos)
                    if index == -1:
                        break
                    start = max(0, index - 150)
                    end = min(len(text), index + 150 + len(query))
                    snippet = '...' + text[start:end] + '...'
                    snippets.append(snippet)
                    start_pos = index + 1
                combined_snippet = ' '.join(snippets[:3]) if snippets else text[:300] + '...'
                metadata = doc.get('metadata', {})
                sections = metadata.get('sections', [])
                results.append({
                    'filename': doc.get('filename'),
                    'snippet': combined_snippet,
                    'safety_keywords': doc.get('safety_keywords', {}),
                    'upload_date': doc.get('upload_date'),
                    'metadata': metadata,
                    'sections': sections
                })
    elif search_type == 'keyword':
        for doc in knowledge_col.find():
            safety_keywords = doc.get('safety_keywords', {})
            found = False
            matched_keywords = []
            for category, keywords in safety_keywords.items():
                for keyword in keywords:
                    if query_lower in keyword.lower():
                        found = True
                        matched_keywords.append(keyword)
            if found:
                results.append({
                    'filename': doc.get('filename'),
                    'safety_keywords': safety_keywords,
                    'upload_date': doc.get('upload_date'),
                    'matched_keywords': list(set(matched_keywords))[:5]
                })
    return results

# ============================================
# FLASK ROUTES
# ============================================

@app.route('/')
@login_required
def index():
    if db is None or records_col is None:
        historical_logs = []
    else:
        historical_logs = list(records_col.find(
            {'uploaded_by': session.get('username')}
        ).sort('_id', -1).limit(50))
    
    return render_template('dashboard.html', 
                         user=session.get('username', 'User'), 
                         role=session.get('role', 'User'),
                         data=historical_logs)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    error_msg = None
    generate_csrf_token()
    
    if request.method == 'POST':
        token = request.form.get('csrf_token')
        if not token or token != session.get('csrf_token'):
            error_msg = 'Invalid CSRF token'
            return render_template('login.html', error=error_msg)
        
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Fallback for testing
        if username == 'admin' and password == 'safety2026':
            session['user_id'] = 'admin'
            session['username'] = 'admin'
            session['role'] = 'Admin'
            session['csrf_token'] = secrets.token_hex(32)
            flash('Welcome back, admin!', 'success')
            return redirect(url_for('index'))
        
        if db is not None and users_col is not None:
            user = users_col.find_one({'username': username})
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                session['user_id'] = str(user['_id'])
                session['username'] = user['username']
                session['role'] = user.get('role', 'Operator')
                session['csrf_token'] = secrets.token_hex(32)
                flash(f'Welcome back, {user["username"]}!', 'success')
                return redirect(url_for('index'))
        
        error_msg = 'Invalid username or password'
    
    return render_template('login.html', error=error_msg)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if db is None or users_col is None:
        return "Database not available", 500
    
    generate_csrf_token()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip()
        
        if not username or len(username) < 3:
            return 'Username must be at least 3 characters', 400
        if not password or len(password) < 8:
            return 'Password must be at least 8 characters', 400
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return 'Username can only contain letters, numbers, and underscores', 400
        
        if users_col.find_one({'username': username}):
            return 'Username already exists', 400
        
        passwd_bytes = password.encode('utf-8')
        salt_hash = bcrypt.gensalt()
        hashed_value = bcrypt.hashpw(passwd_bytes, salt_hash)
        
        users_col.insert_one({
            'username': username,
            'email': email,
            'password_hash': hashed_value.decode('utf-8'),
            'role': 'Operator',
            'created_at': datetime.now()
        })
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
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

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html', user=session.get('username'), role=session.get('role'))

@app.route('/rag-chat')
@login_required
def rag_chat():
    return render_template('rag_chat.html', user=session.get('username'), role=session.get('role'))

@app.route('/search-knowledge', methods=['GET', 'POST'])
@login_required
def search_knowledge():
    if request.method == 'GET':
        return render_template('knowledge_search.html', user=session.get('username'), role=session.get('role'))
    
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
# UPLOAD ROUTES
# ============================================
# app.py - Updated upload_feed section

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

    # 1. UPDATED MAPPING: Normalizes spaces, hyphens, and exact class names
    ppe_mapping = {
        'person': 'person', 'people': 'person', 'worker': 'person', 'machinery': 'person',
        'hardhat': 'helmet', 'helmet': 'helmet', 'head': 'helmet',
        'safety vest': 'vest', 'vest': 'vest', 'jacket': 'vest',
        'mask': 'mask', 'facemask': 'mask'
    }

    is_video = filename.lower().endswith(('.mp4', '.avi', '.mov', '.webm'))
    
    if is_video:
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
                
                # 2. UPDATED FRAME INTERVAL: Lowered from 10 to 3 for better detection continuity
                if frame_count % 3 == 0 and model is not None:
                    try:
                        # Lower confidence threshold to 0.20 for small PPE objects
                        results = model(frame, conf=0.20, imgsz=640)
                        for box in results[0].boxes:
                            tag_class = model.names[int(box.cls[0])]
                            tag_lower = tag_class.lower().strip()
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            box_id = f"{int(x1)},{int(y1)},{int(x2)},{int(y2)}"
                            
                            mapped = None
                            for key, value in ppe_mapping.items():
                                if key in tag_lower:
                                    mapped = value
                                    break
                            
                            if mapped == 'person':
                                detections['workers'].add(box_id)
                            elif mapped == 'helmet':
                                detections['helmets'].add(box_id)
                            elif mapped == 'vest':
                                detections['vests'].add(box_id)
                            elif mapped == 'mask':
                                detections['masks'].add(box_id)
                                
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
            
        except Exception as e:
            print(f"⚠️ Video processing error: {e}")
            shutil.copy2(disk_path, save_destination)
    else:
        print(f"🖼️ Processing image: {filename}")
        if model is not None:
            try:
                # Lower confidence threshold to 0.20 and set image size to 640
                results = model(disk_path, conf=0.20, imgsz=640)
                for item in results:
                    for box in item.boxes:
                        tag_class = model.names[int(box.cls[0])]
                        tag_lower = tag_class.lower().strip()
                        mapped = None
                        for key, value in ppe_mapping.items():
                            if key in tag_lower:
                                mapped = value
                                break
                        
                        if mapped == 'person':
                            count_workers += 1
                        elif mapped == 'helmet':
                            count_helmets += 1
                        elif mapped == 'vest':
                            count_vests += 1
                        elif mapped == 'mask':
                            count_masks += 1
                            
                results[0].save(save_destination)
            except Exception as e:
                print(f"⚠️ Image processing error: {e}")
                shutil.copy2(disk_path, save_destination)
        else:
            shutil.copy2(disk_path, save_destination)

    # 3. COMPLIANCE & VIOLATION LOGIC
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
            violation_incident_reports.append('Missing face mask')

    if db is not None and records_col is not None:
        try:
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
            records_col.insert_one(record)
        except Exception as e:
            print(f"⚠️ Database save error: {e}")
    
    flash('File uploaded and processed successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/upload-document', methods=['GET', 'POST'])
@login_required
def upload_document():
    if request.method == 'GET':
        if db is None or documents_col is None:
            user_docs = []
        else:
            user_docs = list(documents_col.find(
                {'uploaded_by': session.get('username')}
            ).sort('_id', -1))
        return render_template('documents.html', 
                             user=session.get('username'), 
                             role=session.get('role'), 
                             documents=user_docs)
    
    # Handle document upload - ALWAYS RETURN JSON
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
        if not sections and knowledge_entry.get('full_text'):
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
            'processing_status': 'completed',
            'status': 'Processed',
            'progress': 100,
            'sections': sections[:5],
            'rag_indexed': knowledge_entry.get('rag_indexed', False)
        }
        
        doc_id = None
        if db is not None and documents_col is not None:
            try:
                doc_id = documents_col.insert_one(document_record).inserted_id
                knowledge_entry['document_id'] = doc_id
                knowledge_entry['uploaded_by'] = session.get('username')
                if knowledge_col is not None:
                    knowledge_col.insert_one(knowledge_entry)
            except Exception as e:
                print(f"Database error: {e}")
                return jsonify({'error': 'Database error'}), 500
        
        return jsonify({
            'success': True,
            'message': message,
            'document_id': str(doc_id) if doc_id else None,
            'filename': filename,
            'rag_indexed': knowledge_entry.get('rag_indexed', False)
        })
        
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/document/<doc_id>')
@login_required
def view_document(doc_id):
    if db is None or documents_col is None:
        return "Document not found", 404
    
    try:
        doc = documents_col.find_one({
            '_id': ObjectId(doc_id), 
            'uploaded_by': session.get('username')
        })
        if not doc:
            return "Document not found or access denied", 404
        return render_template('document_detail.html', 
                             user=session.get('username'), 
                             role=session.get('role'),
                             document=doc)
    except InvalidId:
        return "Invalid document ID", 400

@app.route('/delete-document/<doc_id>', methods=['POST'])
@login_required
def delete_document(doc_id):
    if db is None or documents_col is None:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        obj_id = ObjectId(doc_id)
        doc = documents_col.find_one({
            '_id': obj_id,
            'uploaded_by': session.get('username')
        })
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
        
        documents_col.delete_one({'_id': obj_id, 'uploaded_by': session.get('username')})
        if knowledge_col is not None:
            knowledge_col.delete_many({'document_id': obj_id, 'uploaded_by': session.get('username')})
        
        return jsonify({'success': True, 'message': 'Document deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API ROUTES
# ============================================

@app.route('/api/compliance-stats', methods=['GET'])
@login_required
def compliance_stats():
    try:
        if db is None or records_col is None:
            return jsonify({'total': 0, 'violations': 0, 'safe': 0, 'compliance': 100})
        records = list(records_col.find({'uploaded_by': session.get('username')}))
        total = len(records)
        violations = sum(1 for r in records if r.get('status') != 'SAFE')
        safe = total - violations
        compliance = round((safe / total * 100) if total > 0 else 100)
        return jsonify({'total': total, 'violations': violations, 'safe': safe, 'compliance': compliance})
    except Exception as e:
        return jsonify({'total': 0, 'violations': 0, 'safe': 0, 'compliance': 100}), 200

@app.route('/api/analytics')
@login_required
def analytics_data():
    if db is None or records_col is None:
        return jsonify({
            'total_audits': 0, 'total_violations': 0, 'safe_audits': 0,
            'compliance_rate': 100, 'total_workers': 0,
            'helmet_compliance': 100, 'vest_compliance': 100, 'mask_compliance': 100,
            'top_violations': [], 'timeline': []
        })
    
    records = list(records_col.find({'uploaded_by': session.get('username')}))
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
        'compliance_rate': round((safe / total * 100) if total > 0 else 100),
        'total_workers': total_workers,
        'helmet_compliance': round((total_helmets / total_workers * 100) if total_workers > 0 else 100),
        'vest_compliance': round((total_vests / total_workers * 100) if total_workers > 0 else 100),
        'mask_compliance': round((total_masks / total_workers * 100) if total_workers > 0 else 100),
        'top_violations': sorted(violation_types.items(), key=lambda x: x[1], reverse=True)[:5],
        'timeline': timeline
    })

@app.route('/api/agent/query', methods=['POST'])
@login_required
def agent_query():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        result = visiondesk_agent.process_query(query, session.get('username'))
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'error': str(e),
            'response': f"I encountered an error: {str(e)}. Please try again.",
            'query': query if 'query' in locals() else ''
        }), 500

@app.route('/api/rag/stats', methods=['GET'])
@login_required
def rag_stats():
    try:
        stats = rag_system.get_document_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'total_chunks': 0, 'documents': 0, 'error': str(e)}), 200

@app.route('/knowledge-stats')
@login_required
def knowledge_stats():
    if db is None or documents_col is None:
        return jsonify({'total_documents': 0})
    total = documents_col.count_documents({'uploaded_by': session.get('username')})
    return jsonify({'total_documents': total})

# ============================================
# EXPORT ROUTES
# ============================================

@app.route('/export/pdf')
@login_required
def export_pdf():
    if db is None or records_col is None:
        historical_logs = []
    else:
        historical_logs = list(records_col.find({'uploaded_by': session.get('username')}).sort('_id', -1))
    
    total_audits = len(historical_logs)
    total_violations = sum(1 for log in historical_logs if log.get('status') != 'SAFE')
    compliance_rate = round(((total_audits - total_violations) / total_audits * 100)) if total_audits > 0 else 100

    report_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { font-family: Helvetica, Arial, sans-serif; color: #2d3748; }
            .header { background: #1a365d; color: white; padding: 20px; text-align: center; }
            .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 8px; border: 1px solid #ddd; text-align: left; }
            th { background: #edf2f7; }
            .text-safe { color: green; font-weight: bold; }
            .text-violation { color: red; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>VisionDesk AI Compliance Report</h1>
            <p>Generated: {{ date_str }}</p>
            <p>User: {{ user }}</p>
        </div>
        <div class="section">
            <h2>Summary Statistics</h2>
            <table>
                <tr><td>Total Audits:</td><td>{{ total_audits }}</td></tr>
                <tr><td>Violations:</td><td>{{ total_violations }}</td></tr>
                <tr><td>Compliance Rate:</td><td>{{ compliance_rate }}%</td></tr>
            </table>
        </div>
    </body>
    </html>
    """
    
    rendered_html = render_template_string(report_template, 
        user=session.get('username'), 
        date_str=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_audits=total_audits,
        total_violations=total_violations,
        compliance_rate=compliance_rate
    )
    
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(rendered_html, dest=pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Compliance_Report_{datetime.now().strftime("%Y%m%d")}.pdf'
    return response

@app.route('/export-knowledge-pdf')
@login_required
def export_knowledge_pdf():
    if db is None or documents_col is None:
        user_docs = []
    else:
        user_docs = list(documents_col.find({'uploaded_by': session.get('username')}).sort('_id', -1))
    
    report_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { font-family: Helvetica, Arial, sans-serif; color: #2d3748; }
            .header { background: #1a365d; color: white; padding: 20px; text-align: center; }
            .doc-card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .keyword-tag { display: inline-block; background: #e2e8f0; padding: 2px 8px; margin: 2px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>VisionDesk Knowledge Report</h1>
            <p>Generated: {{ date_str }}</p>
            <p>User: {{ user }}</p>
        </div>
        <h3>Documents: {{ documents|length }}</h3>
        {% for doc in documents %}
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
        documents=user_docs
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
# DELETE ROUTES
# ============================================

@app.route('/delete-visual-record/<record_id>', methods=['POST'])
@login_required
def delete_visual_record(record_id):
    if db is None or records_col is None:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        obj_id = ObjectId(record_id)
        records_col.delete_one({'_id': obj_id, 'uploaded_by': session.get('username')})
        return jsonify({'success': True, 'message': 'Record deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete-all-visual-records', methods=['POST'])
@login_required
def delete_all_visual_records():
    if db is None or records_col is None:
        return jsonify({'error': 'Database not available'}), 500
    
    result = records_col.delete_many({'uploaded_by': session.get('username')})
    return jsonify({'success': True, 'deleted_count': result.deleted_count})

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    if request.is_json:
        return jsonify({'error': 'Resource not found'}), 404
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(403)
def forbidden(e):
    if request.is_json:
        return jsonify({'error': 'Access forbidden'}), 403
    return render_template('error.html', error='Access forbidden'), 403

@app.errorhandler(500)
def internal_error(e):
    if request.is_json:
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('error.html', error='Internal server error'), 500

# ============================================
# STATIC FILES
# ============================================

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

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
    print(f"🗄️  MongoDB: {MONGO_URI}{MONGO_DB}")
    print("=" * 60)
    print("🌐 Server running at: http://127.0.0.1:5000")
    print("👤 Default admin: admin / safety2026")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)