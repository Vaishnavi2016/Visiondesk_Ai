import re
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session, abort, current_app
import bleach
from markupsafe import Markup, escape

# ============================================
# INPUT SANITIZATION
# ============================================

class Sanitizer:
    """Input sanitization utilities"""
    
    @staticmethod
    def sanitize_html(text):
        """Sanitize HTML content using bleach"""
        if not text:
            return text
        
        allowed_tags = [
            'p', 'br', 'strong', 'em', 'u', 'ul', 'ol', 'li',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div',
            'code', 'pre', 'blockquote', 'a', 'img'
        ]
        allowed_attrs = {
            'a': ['href', 'title', 'target', 'rel'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            '*': ['class', 'id', 'style']
        }
        
        return bleach.clean(text, tags=allowed_tags, attributes=allowed_attrs, strip=True)

    @staticmethod
    def sanitize_filename(filename):
        """Sanitize file name - remove dangerous characters"""
        if not filename:
            return "unnamed_file"
        
        # Remove path traversal
        filename = filename.replace('/', '').replace('\\', '')
        
        # Keep only alphanumeric, dash, dot, underscore, space
        safe = re.sub(r'[^a-zA-Z0-9\s\.\-_]', '', filename)
        
        # Limit length
        if len(safe) > 255:
            name, ext = safe.rsplit('.', 1) if '.' in safe else (safe, '')
            safe = name[:250] + '.' + ext if ext else name[:255]
        
        return safe.strip()

    @staticmethod
    def sanitize_input(data):
        """Recursively sanitize dictionary/list input"""
        if isinstance(data, dict):
            return {k: Sanitizer.sanitize_input(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [Sanitizer.sanitize_input(item) for item in data]
        elif isinstance(data, str):
            # Escape HTML and trim
            return escape(data).strip()
        else:
            return data

    @staticmethod
    def validate_email(email):
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_password(password):
        """Validate password strength"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        if not re.search(r'[0-9]', password):
            return False, "Password must contain at least one number"
        if not re.search(r'[^A-Za-z0-9]', password):
            return False, "Password must contain at least one special character"
        return True, "Password is strong"


# ============================================
# RATE LIMITING
# ============================================

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.limits = {}  # {key: {'count': int, 'reset': timestamp}}
        self.default_limit = 100  # requests per hour
        self.default_window = 3600  # 1 hour in seconds

    def is_allowed(self, key, limit=None, window=None):
        """Check if request is allowed"""
        limit = limit or self.default_limit
        window = window or self.default_window
        
        now = datetime.now().timestamp()
        
        if key not in self.limits:
            self.limits[key] = {'count': 1, 'reset': now + window}
            return True
        
        record = self.limits[key]
        
        # Reset if window expired
        if now > record['reset']:
            record['count'] = 1
            record['reset'] = now + window
            return True
        
        # Check if limit exceeded
        if record['count'] >= limit:
            return False
        
        record['count'] += 1
        return True

    def get_remaining(self, key):
        """Get remaining requests for key"""
        if key not in self.limits:
            return self.default_limit
        
        record = self.limits[key]
        now = datetime.now().timestamp()
        
        if now > record['reset']:
            return self.default_limit
        
        return max(0, self.default_limit - record['count'])

    def get_reset_time(self, key):
        """Get reset time for key"""
        if key not in self.limits:
            return datetime.now() + timedelta(seconds=self.default_window)
        
        return datetime.fromtimestamp(self.limits[key]['reset'])

# Global rate limiter instance
rate_limiter = RateLimiter()


# ============================================
# DECORATORS
# ============================================

def rate_limit(limit=None, window=None):
    """Decorator for rate limiting routes"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Use IP + endpoint as key
            client_ip = request.remote_addr or 'unknown'
            endpoint = request.endpoint or request.path
            key = f"{client_ip}:{endpoint}"
            
            if not rate_limiter.is_allowed(key, limit, window):
                return jsonify({
                    'error': 'Too many requests. Please try again later.',
                    'retry_after': rate_limiter.get_reset_time(key).isoformat()
                }), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_csrf_token(f):
    """Decorator to require CSRF token for POST requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            # Check for CSRF token in headers or form
            token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
            
            if not token:
                abort(403, 'CSRF token missing')
            
            # Verify token
            session_token = session.get('csrf_token')
            if not session_token or not secrets.compare_digest(token, session_token):
                abort(403, 'Invalid CSRF token')
        
        return f(*args, **kwargs)
    return decorated_function


def require_login(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# SESSION MANAGEMENT
# ============================================

def create_session(user_id, username, role):
    """Create a new session with security features"""
    session.clear()
    session['user_id'] = str(user_id)
    session['username'] = username
    session['role'] = role
    session['login_time'] = datetime.now().isoformat()
    session['ip_address'] = request.remote_addr
    session['user_agent'] = request.headers.get('User-Agent', 'Unknown')
    
    # Generate CSRF token
    session['csrf_token'] = secrets.token_hex(32)
    
    return session


def is_session_expired():
    """Check if session has expired"""
    if 'login_time' not in session:
        return True
    
    login_time = datetime.fromisoformat(session['login_time'])
    max_age = current_app.config.get('PERMANENT_SESSION_LIFETIME')
    
    if max_age:
        expiry_time = login_time + max_age
        return datetime.now() > expiry_time
    
    return False


def refresh_session():
    """Refresh session to prevent timeout"""
    if 'login_time' in session:
        session['login_time'] = datetime.now().isoformat()
        session.modified = True


# ============================================
# PASSWORD RESET TOKENS
# ============================================

class PasswordResetToken:
    """Generate and verify password reset tokens"""
    
    @staticmethod
    def generate_token(email):
        """Generate a secure reset token"""
        # Use email + timestamp + secret
        timestamp = int(datetime.now().timestamp())
        raw = f"{email}:{timestamp}:{current_app.config['SECRET_KEY']}"
        token = hashlib.sha256(raw.encode()).hexdigest()
        
        # Store token with expiry (1 hour)
        # In production, store in Redis or database
        # For now, we'll store in a dictionary (not recommended for production)
        if not hasattr(current_app, 'reset_tokens'):
            current_app.reset_tokens = {}
        
        current_app.reset_tokens[token] = {
            'email': email,
            'expires': datetime.now() + timedelta(hours=1)
        }
        
        return token
    
    @staticmethod
    def verify_token(token):
        """Verify a reset token"""
        if not hasattr(current_app, 'reset_tokens'):
            return None
        
        if token not in current_app.reset_tokens:
            return None
        
        record = current_app.reset_tokens[token]
        if datetime.now() > record['expires']:
            del current_app.reset_tokens[token]
            return None
        
        return record['email']
    
    @staticmethod
    def invalidate_token(token):
        """Invalidate a used token"""
        if hasattr(current_app, 'reset_tokens') and token in current_app.reset_tokens:
            del current_app.reset_tokens[token]