import os
from flask import Flask, render_template, request, redirect, url_for, session, render_template_string, make_response, jsonify
from pymongo import MongoClient
import bcrypt
import cv2
from ultralytics import YOLO
import datetime
import io
from xhtml2pdf import pisa
import PyPDF2
import docx
import hashlib
import re
from bs4 import BeautifulSoup
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'system_deployment_operational_matrix_secret_key_2026'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULT_FOLDER'] = 'static/results/'
app.config['DOCUMENT_FOLDER'] = 'documents/'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOCUMENT_FOLDER'], exist_ok=True)

# Establish connection to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['visiondesk_db']
users_col = db['users']
records_col = db['visual_records']
documents_col = db['documents']
knowledge_col = db['knowledge_repository']

# Ingest custom YOLOv8 model brain using explicit absolute path
import pathlib
project_root = pathlib.Path(__file__).parent.resolve()
model_path = os.path.join(project_root, 'ppe_yolov8.pt')
model = YOLO(model_path)

# Seed Database with default root admin if empty
if users_col.count_documents({'username': 'admin'}) == 0:
    passwd_bytes = 'safety2026'.encode('utf-8')
    salt_hash = bcrypt.gensalt()
    hashed_value = bcrypt.hashpw(passwd_bytes, salt_hash)
    users_col.insert_one({
        'username': 'admin',
        'password_hash': hashed_value.decode('utf-8'),
        'role': 'Admin'
    })

# ------------------- DOCUMENT PROCESSING FUNCTIONS -------------------

def extract_text_from_pdf(file_path):
    """Extract text from PDF files"""
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
    """Extract text from DOCX files"""
    text = ""
    try:
        doc = docx.Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    except Exception as e:
        print(f"Error extracting DOCX text: {e}")
    return text

def extract_text_from_txt(file_path):
    """Extract text from TXT files"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error extracting TXT text: {e}")
        return ""

def extract_text_from_html(file_path):
    """Extract text from HTML files"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file.read(), 'html.parser')
            return soup.get_text()
    except Exception as e:
        print(f"Error extracting HTML text: {e}")
        return ""

def extract_safety_keywords(text):
    """Extract safety-related keywords and phrases"""
    safety_patterns = {
        'hazards': r'\b(hazard|danger|risk|threat|unsafe|caution|warning)\b',
        'ppe': r'\b(helmet|hardhat|vest|mask|glove|goggles|earplug|safety shoes)\b',
        'incidents': r'\b(incident|accident|injury|near miss|fatality|emergency)\b',
        'compliance': r'\b(compliance|regulation|standard|osha|iso|safety protocol)\b',
        'inspection': r'\b(inspection|audit|check|verify|monitor|surveillance)\b'
    }
    
    extracted_info = {}
    for category, pattern in safety_patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        extracted_info[category] = list(set([m.lower() for m in matches]))
    
    return extracted_info

def extract_metadata(text):
    """Extract document metadata like dates, numbers, etc."""
    metadata = {}
    
    # Extract dates
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
    
    # Extract numbers (potential quantities, counts)
    numbers = re.findall(r'\b\d+\b', text)
    metadata['numbers'] = numbers[:20]  # Limit to first 20 numbers
    
    # Extract capitalized phrases (potential document titles or important sections)
    capitalized = re.findall(r'\b[A-Z][A-Z\s]{2,}\b', text)
    metadata['important_phrases'] = list(set(capitalized))[:10]
    
    return metadata

def generate_searchable_content(text, filename):
    """Generate searchable content with metadata for knowledge repository"""
    # Extract key information
    safety_keywords = extract_safety_keywords(text)
    metadata = extract_metadata(text)
    
    # Generate searchable text (lowercase for case-insensitive search)
    searchable_text = text.lower()
    
    # Create knowledge entry
    knowledge_entry = {
        'filename': filename,
        'full_text': text,
        'searchable_text': searchable_text,
        'safety_keywords': safety_keywords,
        'metadata': metadata,
        'upload_date': datetime.datetime.now(),
        'document_hash': hashlib.md5(text.encode()).hexdigest()
    }
    
    return knowledge_entry

def process_document(file_path, filename):
    """Process different document types and extract information"""
    file_extension = os.path.splitext(filename)[1].lower()
    
    # Extract text based on file type
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
    
    # Generate searchable knowledge content
    knowledge_entry = generate_searchable_content(text, filename)
    
    return knowledge_entry, "Document processed successfully"

def search_knowledge_base(query, search_type='full_text'):
    """Search the knowledge repository for relevant documents"""
    results = []
    
    if search_type == 'full_text':
        # Full text search using regex (simple search)
        query_lower = query.lower()
        for doc in knowledge_col.find():
            if query_lower in doc.get('searchable_text', '').lower():
                # Create a snippet around the search term
                text = doc.get('full_text', '')
                index = text.lower().find(query_lower)
                if index != -1:
                    start = max(0, index - 100)
                    end = min(len(text), index + 100 + len(query))
                    snippet = '...' + text[start:end] + '...'
                else:
                    snippet = text[:200] + '...'
                
                results.append({
                    'filename': doc.get('filename'),
                    'snippet': snippet,
                    'safety_keywords': doc.get('safety_keywords', {}),
                    'upload_date': doc.get('upload_date'),
                    'metadata': doc.get('metadata', {})
                })
    
    elif search_type == 'keyword':
        # Search by safety keywords
        for doc in knowledge_col.find():
            safety_keywords = doc.get('safety_keywords', {})
            found = False
            for category, keywords in safety_keywords.items():
                if any(query.lower() in keyword.lower() for keyword in keywords):
                    found = True
                    break
            if found:
                results.append({
                    'filename': doc.get('filename'),
                    'safety_keywords': safety_keywords,
                    'upload_date': doc.get('upload_date')
                })
    
    return results

# ------------------- ROUTES -------------------

@app.route('/')
def index():
    if 'username' not in session: 
        return redirect(url_for('login'))
        
    # ONLY find logs where 'uploaded_by' matches the current session user
    historical_logs = list(records_col.find({'uploaded_by': session['username']}).sort('_id', -1))
    
    return render_template('dashboard.html', user=session['username'], role=session['role'], data=historical_logs)

# NEW ROUTE: To display and handle the dedicated upload page layout
@app.route('/upload-feed', methods=['GET', 'POST'])
def upload_feed():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'GET':
        return render_template('upload.html', user=session['username'], role=session['role'])
        
    if 'file' not in request.files: 
        return 'Payload Error: Missing File Element'
    target_file = request.files['file']
    if target_file.filename == '': 
        return 'Payload Error: Null Reference Standard'

    disk_path = os.path.join(app.config['UPLOAD_FOLDER'], target_file.filename)
    target_file.save(disk_path)

    extracted_tags = []
    count_workers = 0
    count_helmets = 0
    count_vests = 0
    count_masks = 0
    
    rendered_name = 'processed_' + target_file.filename
    save_destination = os.path.join(app.config['RESULT_FOLDER'], rendered_name)

    if target_file.filename.lower().endswith(('.mp4', '.avi', '.mov')):
        video_capture = cv2.VideoCapture(disk_path)
        frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(video_capture.get(cv2.CAP_PROP_FPS)) if int(video_capture.get(cv2.CAP_PROP_FPS)) > 0 else 30
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(save_destination, fourcc, fps, (frame_width, frame_height))

        while video_capture.isOpened():
            success, frame = video_capture.read()
            if not success:
                break
            frame_results = model(frame, conf=0.35)
            annotated_frame = frame_results[0].plot()
            video_writer.write(annotated_frame)
            
            for bounding_box in frame_results[0].boxes:
                tag_class = model.names[int(bounding_box.cls[0])]
                tag_lower = tag_class.lower().strip()
                
                if "no-" in tag_lower or "no " in tag_lower or "missing" in tag_lower:
                    continue
                    
                if 'person' in tag_lower or 'worker' in tag_lower: 
                    count_workers += 1
                elif 'helmet' in tag_lower or 'hardhat' in tag_lower or 'head' in tag_lower: 
                    count_helmets += 1
                elif 'vest' in tag_lower or 'jacket' in tag_lower: 
                    count_vests += 1
                elif 'mask' in tag_lower: 
                    count_masks += 1
                    
        video_capture.release()
        video_writer.release()
    else:
        inference_results = model(disk_path, conf=0.35)
        for item in inference_results:
            for bounding_box in item.boxes:
                tag_class = model.names[int(bounding_box.cls[0])]
                extracted_tags.append({'tag': tag_class, 'confidence': float(bounding_box.conf[0])})
                tag_lower = tag_class.lower().strip()
                
                if "no-" in tag_lower or "no " in tag_lower or "missing" in tag_lower:
                    continue
                    
                if 'person' in tag_lower or 'worker' in tag_lower: 
                    count_workers += 1
                elif 'helmet' in tag_lower or 'hardhat' in tag_lower or 'head' in tag_lower: 
                    count_helmets += 1
                elif 'vest' in tag_lower or 'jacket' in tag_lower: 
                    count_vests += 1
                elif 'mask' in tag_lower: 
                    count_masks += 1
        inference_results[0].save(save_destination)

    compliance_state = 'SAFE'
    violation_incident_reports = []
    if count_helmets < count_workers:
        compliance_state = 'VIOLATION DETECTED'
        violation_incident_reports.append('Hazard Alert: Missing helmet protective gear.')
    if count_vests < count_workers:
        compliance_state = 'VIOLATION DETECTED'
        violation_incident_reports.append('Hazard Alert: Missing high-visibility vest safety gear.')

    records_col.insert_one({
        'uploaded_by': session['username'],
        'file_name': target_file.filename,
        'processed_url': '/' + save_destination,
        'status': compliance_state,
        'violations': violation_incident_reports,
        'summary': {'workers': count_workers, 'helmets': count_helmets, 'vests': count_vests, 'masks': count_masks},
        'raw_payload': extracted_tags,
        'upload_date': datetime.datetime.now()
    })
    return redirect(url_for('index'))

# NEW ROUTE: Document Upload and Processing
@app.route('/upload-document', methods=['GET', 'POST'])
def upload_document():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'GET':
        # Get all processed documents for the current user
        user_docs = list(documents_col.find({'uploaded_by': session['username']}).sort('_id', -1))
        return render_template('documents.html', user=session['username'], role=session['role'], documents=user_docs)
    
    if 'document' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['document']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Secure filename
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['DOCUMENT_FOLDER'], filename)
    file.save(file_path)
    
    # Process the document
    knowledge_entry, message = process_document(file_path, filename)
    
    if knowledge_entry is None:
        return jsonify({'error': message}), 400
    
    # Store in MongoDB
    document_record = {
        'uploaded_by': session['username'],
        'filename': filename,
        'file_path': file_path,
        'upload_date': datetime.datetime.now(),
        'knowledge_entry': knowledge_entry,
        'processing_status': 'completed'
    }
    
    # Insert into documents collection
    doc_id = documents_col.insert_one(document_record).inserted_id
    
    # Also store in knowledge repository for searching
    knowledge_entry['document_id'] = doc_id
    knowledge_entry['uploaded_by'] = session['username']
    knowledge_col.insert_one(knowledge_entry)
    
    return jsonify({
        'success': True,
        'message': message,
        'document_id': str(doc_id),
        'filename': filename,
        'extracted_info': {
            'safety_keywords': knowledge_entry.get('safety_keywords', {}),
            'metadata': knowledge_entry.get('metadata', {})
        }
    })

# NEW ROUTE: Search Knowledge Repository
@app.route('/search-knowledge', methods=['GET', 'POST'])
def search_knowledge():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'GET':
        return render_template('knowledge_search.html', user=session['username'], role=session['role'])
    
    query = request.form.get('query', '')
    search_type = request.form.get('search_type', 'full_text')
    
    if not query:
        return jsonify({'error': 'Search query is required'}), 400
    
    # Search the knowledge base
    results = search_knowledge_base(query, search_type)
    
    return render_template('knowledge_search.html', 
                         user=session['username'], 
                         role=session['role'],
                         query=query,
                         results=results,
                         result_count=len(results))

# NEW ROUTE: Get Document Details
@app.route('/document/<doc_id>')
def view_document(doc_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    from bson.objectid import ObjectId
    try:
        doc = documents_col.find_one({'_id': ObjectId(doc_id), 'uploaded_by': session['username']})
        if not doc:
            return "Document not found or access denied", 404
        
        return render_template('document_detail.html', 
                             user=session['username'], 
                             role=session['role'],
                             document=doc)
    except:
        return "Invalid document ID", 400

# NEW ROUTE: Get Knowledge Statistics
@app.route('/knowledge-stats')
def knowledge_stats():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    total_docs = documents_col.count_documents({'uploaded_by': session['username']})
    
    # Count documents by type
    doc_types = {}
    for doc in documents_col.find({'uploaded_by': session['username']}):
        ext = os.path.splitext(doc.get('filename', ''))[1].lower()
        doc_types[ext] = doc_types.get(ext, 0) + 1
    
    # Count documents with safety keywords
    keyword_counts = {}
    for doc in documents_col.find({'uploaded_by': session['username']}):
        knowledge = doc.get('knowledge_entry', {})
        keywords = knowledge.get('safety_keywords', {})
        for category, kw_list in keywords.items():
            for kw in kw_list:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
    
    return jsonify({
        'total_documents': total_docs,
        'document_types': doc_types,
        'top_keywords': sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    })

# NEW ROUTE: Export Knowledge Report
@app.route('/export-knowledge-pdf')
def export_knowledge_pdf():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user_docs = list(documents_col.find({'uploaded_by': session['username']}).sort('_id', -1))
    
    report_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { font-family: Helvetica, Arial, sans-serif; color: #2d3748; }
            .header { border-bottom: 2px solid #2b6cb0; padding-bottom: 10px; margin-bottom: 20px; }
            .title { font-size: 22pt; font-weight: bold; color: #1a365d; }
            .subtitle { font-size: 10pt; color: #4a5568; }
            .doc-card { border: 1px solid #e2e8f0; padding: 15px; margin-bottom: 15px; }
            .doc-filename { font-size: 12pt; font-weight: bold; color: #2b6cb0; }
            .keywords { background: #f7fafc; padding: 8px; margin: 5px 0; }
            .keyword-tag { display: inline-block; background: #e2e8f0; padding: 2px 8px; margin: 2px; border-radius: 3px; font-size: 8pt; }
            .section { margin-top: 20px; border-left: 4px solid #2b6cb0; padding-left: 10px; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">VisionDesk Knowledge Repository Report</div>
            <div class="subtitle">Document Intelligence & Knowledge Extraction Summary</div>
            <div class="subtitle">Generated by: {{ user }} ({{ role }}) - {{ date_str }}</div>
        </div>
        
        <h3>Processed Documents: {{ documents|length }}</h3>
        
        {% for doc in documents %}
        <div class="doc-card">
            <div class="doc-filename">{{ doc.filename }}</div>
            <div><strong>Uploaded:</strong> {{ doc.upload_date }}</div>
            
            {% set knowledge = doc.get('knowledge_entry', {}) %}
            
            <div class="section">Safety Keywords</div>
            <div class="keywords">
                {% for category, keywords in knowledge.get('safety_keywords', {}).items() %}
                <div><strong>{{ category|title }}:</strong>
                    {% for kw in keywords %}
                    <span class="keyword-tag">{{ kw }}</span>
                    {% endfor %}
                </div>
                {% endfor %}
            </div>
            
            <div class="section">Extracted Metadata</div>
            <div>
                {% set metadata = knowledge.get('metadata', {}) %}
                <div><strong>Dates:</strong> {{ metadata.get('dates', [])|join(', ') }}</div>
                <div><strong>Numbers:</strong> {{ metadata.get('numbers', [])|join(', ') }}</div>
                <div><strong>Key Phrases:</strong> {{ metadata.get('important_phrases', [])|join(', ') }}</div>
            </div>
        </div>
        {% endfor %}
    </body>
    </html>
    """
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rendered_html = render_template_string(
        report_template, 
        user=session['username'], 
        role=session['role'], 
        documents=user_docs,
        date_str=now
    )
    
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(rendered_html, dest=pdf_buffer)
    
    if pisa_status.err:
        return "Error compiling PDF report", 500
    
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Knowledge_Report_{datetime.date.today()}.pdf'
    return response

@app.route('/login', methods=['GET', 'POST'])
def login():
    error_msg = None
    if request.method == 'POST':
        input_user = request.form['username']
        input_pass = request.form['password']
        record = users_col.find_one({'username': input_user})
        
        if record and bcrypt.checkpw(input_pass.encode('utf-8'), record['password_hash'].encode('utf-8')):
            session['username'] = record['username']
            session['role'] = record['role']
            return redirect(url_for('index'))
        
        error_msg = 'Access Denied: Invalid Security Signature Matching'
        
    return render_template('login.html', error=error_msg)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_user = request.form['username']
        new_pass = request.form['password']
        
        existing_user = users_col.find_one({'username': new_user})
        if existing_user:
            return 'Registration Error: Username already exists!'
            
        passwd_bytes = new_pass.encode('utf-8')
        salt_hash = bcrypt.gensalt()
        hashed_value = bcrypt.hashpw(passwd_bytes, salt_hash)
        
        users_col.insert_one({
            'username': new_user,
            'password_hash': hashed_value.decode('utf-8'),
            'role': 'Operator'
        })
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files: 
        return 'Payload Error: Missing File Element'
    target_file = request.files['file']
    if target_file.filename == '': 
        return 'Payload Error: Null Reference Standard'

    disk_path = os.path.join(app.config['UPLOAD_FOLDER'], target_file.filename)
    target_file.save(disk_path)

    extracted_tags = []
    count_workers = 0
    count_helmets = 0
    count_vests = 0
    count_masks = 0
    
    rendered_name = 'processed_' + target_file.filename
    save_destination = os.path.join(app.config['RESULT_FOLDER'], rendered_name)

    if target_file.filename.lower().endswith(('.mp4', '.avi', '.mov')):
        video_capture = cv2.VideoCapture(disk_path)
        frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(video_capture.get(cv2.CAP_PROP_FPS)) if int(video_capture.get(cv2.CAP_PROP_FPS)) > 0 else 30
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(save_destination, fourcc, fps, (frame_width, frame_height))

        while video_capture.isOpened():
            success, frame = video_capture.read()
            if not success:
                break
            frame_results = model(frame, conf=0.35)
            annotated_frame = frame_results[0].plot()
            video_writer.write(annotated_frame)
            
            for bounding_box in frame_results[0].boxes:
                tag_class = model.names[int(bounding_box.cls[0])]
                tag_lower = tag_class.lower().strip()
                
                if "no-" in tag_lower or "no " in tag_lower or "missing" in tag_lower:
                    continue
                    
                if 'person' in tag_lower or 'worker' in tag_lower: 
                    count_workers += 1
                elif 'helmet' in tag_lower or 'hardhat' in tag_lower or 'head' in tag_lower: 
                    count_helmets += 1
                elif 'vest' in tag_lower or 'jacket' in tag_lower: 
                    count_vests += 1
                elif 'mask' in tag_lower: 
                    count_masks += 1
                    
        video_capture.release()
        video_writer.release()
    else:
        inference_results = model(disk_path, conf=0.35)
        for item in inference_results:
            for bounding_box in item.boxes:
                tag_class = model.names[int(bounding_box.cls[0])]
                extracted_tags.append({'tag': tag_class, 'confidence': float(bounding_box.conf[0])})
                tag_lower = tag_class.lower().strip()
                
                if "no-" in tag_lower or "no " in tag_lower or "missing" in tag_lower:
                    continue
                    
                if 'person' in tag_lower or 'worker' in tag_lower: 
                    count_workers += 1
                elif 'helmet' in tag_lower or 'hardhat' in tag_lower or 'head' in tag_lower: 
                    count_helmets += 1
                elif 'vest' in tag_lower or 'jacket' in tag_lower: 
                    count_vests += 1
                elif 'mask' in tag_lower: 
                    count_masks += 1
        inference_results[0].save(save_destination)

    compliance_state = 'SAFE'
    violation_incident_reports = []
    if count_helmets < count_workers:
        compliance_state = 'VIOLATION DETECTED'
        violation_incident_reports.append('Hazard Alert: Missing helmet protective gear.')
    if count_vests < count_workers:
        compliance_state = 'VIOLATION DETECTED'
        violation_incident_reports.append('Hazard Alert: Missing high-visibility vest safety gear.')

    records_col.insert_one({
        'uploaded_by': session['username'],
        'file_name': target_file.filename,
        'processed_url': '/' + save_destination,
        'status': compliance_state,
        'violations': violation_incident_reports,
        'summary': {'workers': count_workers, 'helmets': count_helmets, 'vests': count_vests, 'masks': count_masks},
        'raw_payload': extracted_tags,
        'upload_date': datetime.datetime.now()
    })
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/export/pdf')
def export_pdf():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    historical_logs = list(records_col.find({'uploaded_by': session['username']}).sort('_id', -1))
    
    total_audits = len(historical_logs)
    total_violations = sum(1 for log in historical_logs if log.get('status') != 'SAFE')
    compliance_rate = round(((total_audits - total_violations) / total_audits * 100)) if total_audits > 0 else 100

    report_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {
                font-family: Helvetica, Arial, sans-serif;
                color: #2d3748;
                line-height: 1.4;
            }
            .header-container {
                border-bottom: 2px solid #2b6cb0;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }
            .title {
                font-size: 22pt;
                font-weight: bold;
                color: #1a365d;
                margin: 0;
            }
            .subtitle {
                font-size: 10pt;
                color: #4a5568;
                text-transform: uppercase;
            }
            .meta-table {
                width: 100%;
                margin-bottom: 20px;
                font-size: 10pt;
                color: #4a5568;
            }
            .summary-table {
                width: 100%;
                margin-bottom: 25px;
            }
            .summary-card {
                background-color: #f7fafc;
                border: 1px solid #e2e8f0;
                padding: 12px;
                text-align: center;
            }
            .summary-val {
                font-size: 18pt;
                font-weight: bold;
                color: #2b6cb0;
            }
            .summary-lbl {
                font-size: 8pt;
                text-transform: uppercase;
                color: #718096;
            }
            .section-heading {
                font-size: 13pt;
                color: #1a365d;
                border-left: 4px solid #2b6cb0;
                padding-left: 8px;
                margin-bottom: 15px;
                margin-top: 20px;
            }
            .audit-table {
                width: 100%;
                font-size: 9pt;
            }
            .audit-table th {
                background-color: #2b6cb0;
                color: white;
                text-align: left;
                padding: 8px;
                font-weight: bold;
            }
            .audit-table td {
                padding: 10px 8px;
                border-bottom: 1px solid #e2e8f0;
            }
            .badge {
                padding: 2px 6px;
                font-size: 8pt;
                font-weight: bold;
            }
            .text-safe { color: #38a169; font-weight: bold; }
            .text-violation { color: #e53e3e; font-weight: bold; }
            .violation-list {
                margin: 0;
                padding-left: 12px;
                color: #e53e3e;
            }
        </style>
    </head>
    <body>
        <div class="header-container">
            <div class="title">VisionDesk AI Compliance Report</div>
            <div class="subtitle">Automated Site Auditing Analytics Ledger</div>
        </div>

        <table class="meta-table">
            <tr>
                <td><strong>Generated By:</strong> {{ user }} ({{ role }})</td>
                <td style="text-align: right;"><strong>Timestamp:</strong> {{ date_str }}</td>
            </tr>
        </table>

        <table class="summary-table">
            <tr>
                <td class="summary-card" style="width: 33.33%;">
                    <div class="summary-val">{{ total_audits }}</div>
                    <div class="summary-lbl">Total Feeds Audited</div>
                </td>
                <td class="summary-card" style="width: 33.33%;">
                    <div class="summary-val" style="color: #e53e3e;">{{ total_violations }}</div>
                    <div class="summary-lbl">Safety Exceptions</div>
                </td>
                <td class="summary-card" style="width: 33.33%;">
                    <div class="summary-val" style="color: #38a169;">{{ compliance_rate }}%</div>
                    <div class="summary-lbl">Site Compliance Index</div>
                </td>
            </tr>
        </table>

        <div class="section-heading">Historical Verification Ledger</div>
        <table class="audit-table">
            <thead>
                <tr>
                    <th style="width: 45%; padding-right: 15px;">Asset File Identifier</th>
                    <th style="width: 15%;">Status</th>
                    <th style="width: 20%;">Surveillance Breakdown</th>
                    <th style="width: 20%;">Compliance Infractions</th>
                </tr>
            </thead>
            <tbody>
                {% for item in data %}
                <tr>
                    <td style="font-family: monospace; font-size: 8pt;">{{ item.file_name }}</td>
                    <td>
                        {% if item.status == 'SAFE' %}
                        <span class="text-safe">COMPLIANT</span>
                        {% else %}
                        <span class="text-violation">VIOLATION</span>
                        {% endif %}
                    </td>
                    <td>
                        Workers: {{ item.summary.workers }}<br>
                        Helmets: {{ item.summary.helmets }}<br>
                        Vests: {{ item.summary.vests }}<br>
                        Masks: {{ item.summary.get('masks', 0) }}
                    </td>
                    <td>
                        {% if item.violations %}
                        <ul class="violation-list">
                            {% for v in item.violations %}
                            <li>{{ v }}</li>
                            {% endfor %}
                        </ul>
                        {% else %}
                        <span style="color: #718096;">None</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </body>
    </html>
    """
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rendered_html = render_template_string(
        report_template, 
        user=session['username'], 
        role=session['role'], 
        data=historical_logs,
        date_str=now,
        total_audits=total_audits,
        total_violations=total_violations,
        compliance_rate=compliance_rate
    )
    
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(rendered_html, dest=pdf_buffer)
    
    if pisa_status.err:
        return "Error compiling PDF pipeline report asset", 500
        
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=VisionDesk_Compliance_Report_{datetime.date.today()}.pdf'
    return response

if __name__ == '__main__':
    # debug=True stays on for error checking, but use_reloader=False blocks socket crashes
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)