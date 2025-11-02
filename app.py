from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from functools import wraps
from flask_socketio import SocketIO, emit, join_room
import requests
from bs4 import BeautifulSoup
import threading
import time
from sqlalchemy import func, nullslast
from sqlalchemy import text
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
from dotenv import load_dotenv
from imagekitio import ImageKit

# Load environment variables
load_dotenv()

# ImageKit SDK initialization
# Use environment variables if available, otherwise fallback to hardcoded credentials
IMAGEKIT_PRIVATE_KEY = os.environ.get('IMAGEKIT_PRIVATE_KEY', 'private_XE8zZEDma0ILZDvb4gwdWD2CEWo=')
IMAGEKIT_PUBLIC_KEY = os.environ.get('IMAGEKIT_PUBLIC_KEY', 'public_FwDoUWOImuHVjq5Jcac/OARqTyY=')
IMAGEKIT_URL_ENDPOINT = os.environ.get('IMAGEKIT_URL_ENDPOINT', 'https://ik.imagekit.io/SMI')

try:
    imagekit = ImageKit(
        private_key=IMAGEKIT_PRIVATE_KEY,
        public_key=IMAGEKIT_PUBLIC_KEY,
        url_endpoint=IMAGEKIT_URL_ENDPOINT
    )
    print("✓ ImageKit initialized successfully")
except Exception as e:
    print(f"⚠ ImageKit initialization error: {e}")
    imagekit = None

# Configure Flask with explicit static folder for Vercel deployment
# Get the directory where app.py is located
app_dir = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(app_dir, 'static')

app = Flask(__name__, static_folder=static_folder)
# Generate a random secret key if not set in environment (development only)
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print("⚠ WARNING: SECRET_KEY not set in environment. Using a random key (not recommended for production)")
app.config['SECRET_KEY'] = SECRET_KEY

# PostgreSQL Configuration (Render)
# Use external database URL from environment or default to provided credentials
DATABASE_URL = os.environ.get('DATABASE_URL', 
    'postgresql://smied_db_user:TAuBhdkbInY3nz0ejuQslgPFCgiruxpz@dpg-d3ru3eripnbc738jkja0-a.oregon-postgres.render.com/smied_db')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Test database connection
db_connected = False
try:
    with app.app_context():
        db.engine.connect()
        db_connected = True
        print(f"✓ Connected to PostgreSQL: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'database'}")
except Exception as e:
    print(f"⚠ PostgreSQL connection error: {e}")
    print("⚠ Application will start but database operations may fail.")
    db_connected = False

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'
login_manager.session_protection = 'strong'  # Prevent session hijacking
# Use threading instead of eventlet to avoid SSL compatibility issues with Python 3.12+
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Jinja2 filter for date formatting
@app.template_filter('datetime')
def datetime_filter(value, format='%Y-%m-%d'):
    """Format datetime for templates"""
    if isinstance(value, datetime):
        return value.strftime(format)
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime(format)
        except:
            return value[:10] if len(value) >= 10 else value
    return value

# Helper function to upload image to ImageKit with local fallback
def upload_image_to_imagekit(image_file, folder_name='uploads', fallback_to_local=True):
    """
    Upload an image file to ImageKit and return the URL.
    If ImageKit fails and fallback_to_local is True, saves to local filesystem.
    
    Args:
        image_file: Flask FileStorage object from request.files
        folder_name: Folder name in ImageKit or local storage (default: 'uploads')
        fallback_to_local: If True, save locally when ImageKit fails
    
    Returns:
        str: Image URL if successful, None if failed
    """
    try:
        # Reset file pointer to beginning
        image_file.seek(0)
        file_content = image_file.read()
        image_file.seek(0)  # Reset again for potential local save
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        original_filename = secure_filename(image_file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
        unique_filename = f"{timestamp}_{secrets.token_hex(8)}.{file_extension}"
        
        # Try ImageKit first (if initialized)
        if imagekit:
            try:
                upload_response = imagekit.upload_file(
                    file=file_content,
                    file_name=unique_filename,
                    options={
                        "folder": folder_name
                    }
                )
                
                # Return the URL - response format may vary
                if upload_response:
                    # If response is a dict, try to get URL
                    if isinstance(upload_response, dict):
                        if 'url' in upload_response:
                            print(f"ImageKit upload successful: {upload_response['url']}")
                            return upload_response['url']
                        # Check if response is nested
                        elif 'response_metadata' in upload_response and isinstance(upload_response['response_metadata'], dict) and 'url' in upload_response['response_metadata']:
                            print(f"ImageKit upload successful: {upload_response['response_metadata']['url']}")
                            return upload_response['response_metadata']['url']
                        elif 'response' in upload_response and isinstance(upload_response['response'], dict) and 'url' in upload_response['response']:
                            print(f"ImageKit upload successful: {upload_response['response']['url']}")
                            return upload_response['response']['url']
                        # Additional check for nested structures
                        elif 'data' in upload_response and isinstance(upload_response['data'], dict) and 'url' in upload_response['data']:
                            print(f"ImageKit upload successful: {upload_response['data']['url']}")
                            return upload_response['data']['url']
                    # If response has url attribute
                    elif hasattr(upload_response, 'url'):
                        print(f"ImageKit upload successful: {upload_response.url}")
                        return upload_response.url
                    else:
                        print(f"ImageKit upload returned unexpected format: {type(upload_response)}")
                        print(f"Response: {upload_response}")
            
            except Exception as e:
                print(f"ImageKit upload failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("ImageKit not initialized, skipping upload")
        
        # ImageKit failed or returned None, fallback to local storage if enabled
        if fallback_to_local:
            try:
                # Map folder names to local directories
                folder_map = {
                    'posts': 'posts',
                    'adverts': 'adverts',
                    'profiles': 'profiles',
                    'uploads': 'uploads'
                }
                local_folder = folder_map.get(folder_name, 'uploads')
                
                # Create upload directory if it doesn't exist
                upload_folder = os.path.join(app.root_path, 'static', 'images', local_folder)
                os.makedirs(upload_folder, exist_ok=True)
                
                # Save file locally
                filepath = os.path.join(upload_folder, unique_filename)
                image_file.save(filepath)
                
                # Return local URL
                local_url = url_for('static', filename=f'images/{local_folder}/{unique_filename}')
                print(f"Image saved locally: {local_url}")
                return local_url
                
            except Exception as e:
                print(f"Local file save also failed: {e}")
        
        return None
        
    except Exception as e:
        print(f"Error in upload_image_to_imagekit: {e}")
        import traceback
        traceback.print_exc()
        return None

# SQLAlchemy Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200), nullable=True)
    profile_picture = db.Column(db.String(1000), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # Active by default, admin can deactivate
    email_verified = db.Column(db.Boolean, default=True, nullable=False)  # No email verification required
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        """Return the user ID as a string for Flask-Login"""
        return f"user_{self.id}"
    
    def __repr__(self):
        return f'<User {self.username}>'

class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        """Return the admin ID as a string for Flask-Login"""
        return f"admin_{self.id}"
    
    def __repr__(self):
        return f'<Admin {self.username}>'

class NewsArticle(db.Model):
    __tablename__ = 'news_articles'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, nullable=True)
    source_url = db.Column(db.String(1000), unique=True, nullable=False, index=True)
    image_url = db.Column(db.String(1000), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_education_related = db.Column(db.Boolean, default=True, nullable=False)

class Advert(db.Model):
    __tablename__ = 'adverts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(1000), nullable=True)
    link_url = db.Column(db.String(1000), nullable=True)
    button_text = db.Column(db.String(100), default='Learn More')
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=True)
    weeks = db.Column(db.Integer, default=1, nullable=False)  # Number of weeks to run
    start_date = db.Column(db.DateTime, nullable=True)  # When advert starts running
    end_date = db.Column(db.DateTime, nullable=True)  # When advert expires
    status = db.Column(db.String(50), default='pending', nullable=False)  # pending, approved, active, expired, rejected
    payment_status = db.Column(db.String(50), default='pending', nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    user = db.relationship('User', backref='adverts')

class BlogPost(db.Model):
    __tablename__ = 'blog_posts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(1000), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    author = db.relationship('User', backref='posts')
    comments = db.relationship('PostComment', backref='post', lazy='dynamic', cascade='all, delete-orphan', order_by='PostComment.created_at.asc()')

class PostComment(db.Model):
    __tablename__ = 'post_comments'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('blog_posts.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User', backref='comments')

class UserActivity(db.Model):
    __tablename__ = 'user_activities'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User', backref='activities')

class EmailToken(db.Model):
    __tablename__ = 'email_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    token_type = db.Column(db.String(50), nullable=False)  # 'activation' or 'password_reset'
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User', backref='email_tokens')

class AdvertPricing(db.Model):
    __tablename__ = 'advert_pricing'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=500.00)  # Price per week (default 500 naira)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    """Load user from PostgreSQL - supports both User and Admin"""
    if not db_connected:
        return None
    if not user_id:
        return None
    try:
        # Handle prefixed IDs (user_1, admin_1)
        if isinstance(user_id, str) and '_' in user_id:
            prefix, id_str = user_id.split('_', 1)
            user_id_int = int(id_str)
            
            if prefix == 'admin':
                admin = Admin.query.get(user_id_int)
                if admin:
                    return admin
            elif prefix == 'user':
                user = User.query.get(user_id_int)
                if user and user.is_active:
                    return user
        else:
            # Fallback for legacy integer IDs (try both User and Admin)
            user_id_int = int(user_id)
            
            # Try to load as admin first (to avoid conflicts)
            admin = Admin.query.get(user_id_int)
            if admin:
                return admin
            
            # Try regular user
            user = User.query.get(user_id_int)
            if user and user.is_active:
                return user
        
        return None
    except (ValueError, TypeError, Exception) as e:
        print(f"Error loading user {user_id}: {e}")
        return None

# Email Configuration
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '').replace(' ', '')  # Remove spaces from Gmail App Password
APP_URL = os.environ.get('APP_URL', 'http://127.0.0.1:5000')

# Paystack Configuration
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '')
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
if not PAYSTACK_SECRET_KEY:
    print("⚠ WARNING: PAYSTACK_SECRET_KEY not set in environment. Payment features will not work.")

def send_email(to_email, subject, html_body, text_body=None):
    """Send email using SMTP with improved error handling"""
    try:
        # Check configuration
        if not MAIL_USERNAME:
            print("⚠ Email not configured. MAIL_USERNAME is missing in .env")
            return False
        
        if not MAIL_PASSWORD:
            print("⚠ Email not configured. MAIL_PASSWORD is missing in .env")
            return False
        
        print(f"📧 Attempting to send email to {to_email} using {MAIL_USERNAME}")
        
        # Validate email address
        if not to_email or '@' not in to_email:
            print(f"⚠ Invalid email address: {to_email}")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = MAIL_USERNAME
        msg['To'] = to_email
        
        # Create both plain text and HTML versions
        if text_body:
            text_part = MIMEText(text_body, 'plain', 'utf-8')
            msg.attach(text_part)
        
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Send email with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                server = smtplib.SMTP(SMTP_SERVER, MAIL_PORT, timeout=30)
                server.starttls()
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(msg)
                server.quit()
                
                print(f"✓ Email sent to {to_email}")
                return True
            except smtplib.SMTPAuthenticationError as e:
                print(f"⚠ SMTP Authentication Error: {e}")
                print("⚠ Please check your MAIL_USERNAME and MAIL_PASSWORD in .env")
                print("⚠ For Gmail, make sure you're using an App Password, not your regular password")
                return False
            except smtplib.SMTPException as e:
                if attempt < max_retries - 1:
                    print(f"⚠ SMTP error (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                    time.sleep(2)  # Wait 2 seconds before retry
                else:
                    print(f"⚠ SMTP error after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠ Connection error (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                    time.sleep(2)
                else:
                    print(f"⚠ Connection error after {max_retries} attempts: {e}")
                    raise
        
        return False
    except Exception as e:
        print(f"⚠ Error sending email to {to_email}: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_activation_email(user):
    """Send account activation email"""
    # Generate activation token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    # Save token to database
    email_token = EmailToken(
        user_id=user.id,
        token=token,
        token_type='activation',
        expires_at=expires_at
    )
    db.session.add(email_token)
    db.session.commit()
    
    # Create activation URL
    activation_url = f"{APP_URL}/activate/{token}"
    
    # Email content
    subject = "Activate Your Educators' Tribe Account"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #006B3C; color: white; padding: 20px; text-align: center;">
                <h1>Welcome to Educators' Tribe!</h1>
            </div>
            <div style="padding: 30px; background-color: #f9fafb;">
                <h2>Hello {user.full_name or user.username},</h2>
                <p>Thank you for registering with Educators' Tribe. Please click the button below to activate your account:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{activation_url}" style="background-color: #006B3C; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Activate Account
                    </a>
                </div>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #006B3C;">{activation_url}</p>
                <p><strong>Note:</strong> This link will expire in 24 hours.</p>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #6b7280; font-size: 12px;">If you didn't create this account, please ignore this email.</p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Welcome to Educators' Tribe!
    
    Hello {user.full_name or user.username},
    
    Thank you for registering with Educators' Tribe. Please visit the following link to activate your account:
    
    {activation_url}
    
    This link will expire in 24 hours.
    
    If you didn't create this account, please ignore this email.
    """
    
    return send_email(user.email, subject, html_body, text_body)

def send_password_reset_email(user):
    """Send password reset email"""
    # Generate reset token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Invalidate old tokens
    EmailToken.query.filter_by(user_id=user.id, token_type='password_reset', used=False).update({'used': True})
    
    # Save token to database
    email_token = EmailToken(
        user_id=user.id,
        token=token,
        token_type='password_reset',
        expires_at=expires_at
    )
    db.session.add(email_token)
    db.session.commit()
    
    # Create reset URL
    reset_url = f"{APP_URL}/reset-password/{token}"
    
    # Email content
    subject = "Reset Your Educators' Tribe Password"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #dc2626; color: white; padding: 20px; text-align: center;">
                <h1>Password Reset Request</h1>
            </div>
            <div style="padding: 30px; background-color: #f9fafb;">
                <h2>Hello {user.full_name or user.username},</h2>
                <p>We received a request to reset your password. Click the button below to reset it:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" style="background-color: #dc2626; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Reset Password
                    </a>
                </div>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #dc2626;">{reset_url}</p>
                <p><strong>Note:</strong> This link will expire in 1 hour.</p>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #6b7280; font-size: 12px;">If you didn't request a password reset, please ignore this email.</p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Password Reset Request
    
    Hello {user.full_name or user.username},
    
    We received a request to reset your password. Please visit the following link:
    
    {reset_url}
    
    This link will expire in 1 hour.
    
    If you didn't request a password reset, please ignore this email.
    """
    
    return send_email(user.email, subject, html_body, text_body)

def send_welcome_email(user):
    """Send welcome email after successful account activation"""
    subject = "Welcome to Educators' Tribe - Your Account is Active!"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f9fafb;">
            <div style="background-color: #006B3C; color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0;">🎉 Welcome to Educators' Tribe!</h1>
            </div>
            <div style="padding: 40px; background-color: white;">
                <h2 style="color: #1f2937; margin-top: 0;">Hello {user.full_name or user.username},</h2>
                <p style="color: #4b5563; line-height: 1.6;">
                    Congratulations! Your account has been successfully activated. You're now part of a vibrant community of educators.
                </p>
                <p style="color: #4b5563; line-height: 1.6;">
                    Here's what you can do on Educators' Tribe:
                </p>
                <ul style="color: #4b5563; line-height: 1.8;">
                    <li>Read and share education-related news</li>
                    <li>Create and publish blog posts</li>
                    <li>Connect with other educators</li>
                    <li>Submit advertisements</li>
                    <li>Stay updated with the latest in education</li>
                </ul>
                <div style="text-align: center; margin: 40px 0;">
                    <a href="{APP_URL}" style="background-color: #006B3C; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                        Get Started
                    </a>
                </div>
                <div style="background-color: #f0f9ff; padding: 20px; border-radius: 6px; margin-top: 30px;">
                    <p style="margin: 0; color: #008753; font-size: 14px;">
                        <strong>Need help?</strong> If you have any questions, feel free to reach out to our support team.
                    </p>
                </div>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 40px 0;">
                <p style="color: #6b7280; font-size: 12px; text-align: center; margin: 0;">
                    Thank you for joining Educators' Tribe. We're excited to have you!
                </p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Welcome to Educators' Tribe - Your Account is Active!
    
    Hello {user.full_name or user.username},
    
    Congratulations! Your account has been successfully activated. You're now part of a vibrant community of educators.
    
    Here's what you can do on Educators' Tribe:
    - Read and share education-related news
    - Create and publish blog posts
    - Connect with other educators
    - Submit advertisements
    - Stay updated with the latest in education
    
    Get started by visiting: {APP_URL}
    
    Need help? If you have any questions, feel free to reach out to our support team.
    
    Thank you for joining Educators' Tribe. We're excited to have you!
    """
    
    return send_email(user.email, subject, html_body, text_body)

def send_password_change_confirmation_email(user):
    """Send password change confirmation email"""
    subject = "Your Password Has Been Changed"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f9fafb;">
            <div style="background-color: #059669; color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0;">🔒 Password Changed Successfully</h1>
            </div>
            <div style="padding: 40px; background-color: white;">
                <h2 style="color: #1f2937; margin-top: 0;">Hello {user.full_name or user.username},</h2>
                <p style="color: #4b5563; line-height: 1.6;">
                    This is to confirm that your password has been successfully changed.
                </p>
                <p style="color: #4b5563; line-height: 1.6;">
                    <strong>Date:</strong> {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}
                </p>
                <div style="background-color: #fef3c7; padding: 20px; border-radius: 6px; margin: 30px 0; border-left: 4px solid #f59e0b;">
                    <p style="margin: 0; color: #92400e; font-size: 14px;">
                        <strong>⚠️ Security Alert:</strong> If you did not make this change, please reset your password immediately and contact our support team.
                    </p>
                </div>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{APP_URL}/forgot-password" style="background-color: #dc2626; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; font-size: 14px;">
                        Reset Password
                    </a>
                </div>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #6b7280; font-size: 12px; text-align: center; margin: 0;">
                    This is an automated security notification. Please keep your account credentials secure.
                </p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Password Changed Successfully
    
    Hello {user.full_name or user.username},
    
    This is to confirm that your password has been successfully changed.
    
    Date: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}
    
    SECURITY ALERT: If you did not make this change, please reset your password immediately and contact our support team.
    
    Reset your password: {APP_URL}/forgot-password
    
    This is an automated security notification. Please keep your account credentials secure.
    """
    
    return send_email(user.email, subject, html_body, text_body)

def send_advert_approval_email(user, advert):
    """Send email notification when advert is approved"""
    subject = f"Your Advert '{advert.title}' Has Been Approved!"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f9fafb;">
            <div style="background-color: #059669; color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0;">✅ Advert Approved!</h1>
            </div>
            <div style="padding: 40px; background-color: white;">
                <h2 style="color: #1f2937; margin-top: 0;">Hello {user.full_name or user.username},</h2>
                <p style="color: #4b5563; line-height: 1.6;">
                    Great news! Your advert <strong>"{advert.title}"</strong> has been approved and is now live on Educators' Tribe.
                </p>
                <div style="background-color: #f0fdf4; padding: 20px; border-radius: 6px; margin: 30px 0; border-left: 4px solid #059669;">
                    <p style="margin: 0; color: #166534; font-weight: bold;">Advert Details:</p>
                    <p style="margin: 10px 0 0 0; color: #166534;">
                        <strong>Title:</strong> {advert.title}<br>
                        <strong>Status:</strong> {advert.status.title()}<br>
                        <strong>Payment Status:</strong> {advert.payment_status.title()}<br>
                        <strong>Amount:</strong> ₦{float(advert.amount):,.2f if advert.amount else '0.00'}
                    </p>
                </div>
                {f'<p style="color: #4b5563; line-height: 1.6;"><strong>Admin Notes:</strong> {advert.admin_notes}</p>' if advert.admin_notes else ''}
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{APP_URL}/adverts/my" style="background-color: #006B3C; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                        View My Adverts
                    </a>
                </div>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #6b7280; font-size: 12px; text-align: center; margin: 0;">
                    Thank you for using Educators' Tribe!
                </p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Advert Approved!
    
    Hello {user.full_name or user.username},
    
    Great news! Your advert "{advert.title}" has been approved and is now live on Educators' Tribe.
    
    Advert Details:
    Title: {advert.title}
    Status: {advert.status.title()}
    Payment Status: {advert.payment_status.title()}
    Amount: ₦{float(advert.amount):,.2f if advert.amount else '0.00'}
    
    {f'Admin Notes: {advert.admin_notes}' if advert.admin_notes else ''}
    
    View your adverts: {APP_URL}/adverts/my
    
    Thank you for using Educators' Tribe!
    """
    
    return send_email(user.email, subject, html_body, text_body)

def send_advert_rejection_email(user, advert):
    """Send email notification when advert is rejected"""
    subject = f"Update on Your Advert '{advert.title}'"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f9fafb;">
            <div style="background-color: #dc2626; color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0;">Advert Status Update</h1>
            </div>
            <div style="padding: 40px; background-color: white;">
                <h2 style="color: #1f2937; margin-top: 0;">Hello {user.full_name or user.username},</h2>
                <p style="color: #4b5563; line-height: 1.6;">
                    We regret to inform you that your advert <strong>"{advert.title}"</strong> has been rejected.
                </p>
                <div style="background-color: #fef2f2; padding: 20px; border-radius: 6px; margin: 30px 0; border-left: 4px solid #dc2626;">
                    <p style="margin: 0; color: #991b1b; font-weight: bold;">Advert Details:</p>
                    <p style="margin: 10px 0 0 0; color: #991b1b;">
                        <strong>Title:</strong> {advert.title}<br>
                        <strong>Status:</strong> {advert.status.title()}
                    </p>
                </div>
                {f'<p style="color: #4b5563; line-height: 1.6;"><strong>Admin Notes:</strong> {advert.admin_notes}</p>' if advert.admin_notes else '<p style="color: #4b5563; line-height: 1.6;">If you have questions about this decision, please contact our support team.</p>'}
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{APP_URL}/advert/submit" style="background-color: #006B3C; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                        Submit New Advert
                    </a>
                </div>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #6b7280; font-size: 12px; text-align: center; margin: 0;">
                    Thank you for using Educators' Tribe!
                </p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Advert Status Update
    
    Hello {user.full_name or user.username},
    
    We regret to inform you that your advert "{advert.title}" has been rejected.
    
    Advert Details:
    Title: {advert.title}
    Status: {advert.status.title()}
    
    {f'Admin Notes: {advert.admin_notes}' if advert.admin_notes else 'If you have questions about this decision, please contact our support team.'}
    
    Submit a new advert: {APP_URL}/advert/submit
    
    Thank you for using Educators' Tribe!
    """
    
    return send_email(user.email, subject, html_body, text_body)

def send_account_status_change_email(user, status, reason=None):
    """Send email notification when account status is changed by admin"""
    status_text = "activated" if status else "deactivated"
    status_color = "#059669" if status else "#dc2626"
    subject = f"Account {status_text.title()}"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f9fafb;">
            <div style="background-color: {status_color}; color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0;">Account {status_text.title()}</h1>
            </div>
            <div style="padding: 40px; background-color: white;">
                <h2 style="color: #1f2937; margin-top: 0;">Hello {user.full_name or user.username},</h2>
                <p style="color: #4b5563; line-height: 1.6;">
                    Your account has been <strong>{status_text}</strong> by an administrator.
                </p>
                {f'<p style="color: #4b5563; line-height: 1.6;"><strong>Reason:</strong> {reason}</p>' if reason else ''}
                <div style="background-color: {'#f0fdf4' if status else '#fef2f2'}; padding: 20px; border-radius: 6px; margin: 30px 0; border-left: 4px solid {status_color};">
                    <p style="margin: 0; color: {'#166534' if status else '#991b1b'}; font-size: 14px;">
                        {'Your account is now active and you can log in to access all features.' if status else 'Your account access has been restricted. If you believe this is an error, please contact support.'}
                    </p>
                </div>
                {'<div style="text-align: center; margin: 30px 0;"><a href="' + APP_URL + '/login" style="background-color: #006B3C; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">Login to Your Account</a></div>' if status else ''}
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #6b7280; font-size: 12px; text-align: center; margin: 0;">
                    {('If you have questions, please contact our support team.' if not status else "Thank you for being part of Educators' Tribe!")}
                </p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Account {status_text.title()}
    
    Hello {user.full_name or user.username},
    
    Your account has been {status_text} by an administrator.
    
    {f'Reason: {reason}' if reason else ''}
    
    {'Your account is now active and you can log in to access all features.' if status else 'Your account access has been restricted. If you believe this is an error, please contact support.'}
    
    {'Login to your account: ' + APP_URL + '/login' if status else ''}
    
    {('If you have questions, please contact our support team.' if not status else "Thank you for being part of Educators' Tribe!")}
    """
    
    return send_email(user.email, subject, html_body, text_body)

def send_payment_confirmation_email(user, advert):
    """Send email notification when advert payment is confirmed"""
    subject = f"Payment Confirmed - Your Advert '{advert.title}'"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f9fafb;">
            <div style="background-color: #059669; color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0;">💳 Payment Confirmed!</h1>
            </div>
            <div style="padding: 40px; background-color: white;">
                <h2 style="color: #1f2937; margin-top: 0;">Hello {user.full_name or user.username},</h2>
                <p style="color: #4b5563; line-height: 1.6;">
                    Great news! Your payment for the advert <strong>"{advert.title}"</strong> has been successfully confirmed.
                </p>
                <div style="background-color: #f0fdf4; padding: 20px; border-radius: 6px; margin: 30px 0; border-left: 4px solid #059669;">
                    <p style="margin: 0; color: #166534; font-weight: bold;">Payment Details:</p>
                    <p style="margin: 10px 0 0 0; color: #166534;">
                        <strong>Advert Title:</strong> {advert.title}<br>
                        <strong>Amount Paid:</strong> ₦{float(advert.amount):,.2f if advert.amount else '0.00'}<br>
                        <strong>Payment Status:</strong> Paid<br>
                        <strong>Date:</strong> {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}
                    </p>
                </div>
                <p style="color: #4b5563; line-height: 1.6;">
                    Your advert is now active and will be displayed on Educators' Tribe. Thank you for your payment!
                </p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{APP_URL}/adverts/my" style="background-color: #006B3C; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                        View My Adverts
                    </a>
                </div>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #6b7280; font-size: 12px; text-align: center; margin: 0;">
                    This is your payment confirmation. Please keep this email for your records.
                </p>
            </div>
        </body>
    </html>
    """
    
    text_body = f"""
    Payment Confirmed!
    
    Hello {user.full_name or user.username},
    
    Great news! Your payment for the advert "{advert.title}" has been successfully confirmed.
    
    Payment Details:
    Advert Title: {advert.title}
    Amount Paid: ₦{float(advert.amount):,.2f if advert.amount else '0.00'}
    Payment Status: Paid
    Date: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}
    
    Your advert is now active and will be displayed on Educators' Tribe. Thank you for your payment!
    
    View your adverts: {APP_URL}/adverts/my
    
    This is your payment confirmation. Please keep this email for your records.
    """
    
    return send_email(user.email, subject, html_body, text_body)

# Decorator for admin-only routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not db_connected:
            flash('Database not available. Please try again later.', 'danger')
            return redirect(url_for('index'))
        
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('admin_login'))
        
        # Check if user is an admin by checking the class name or type
        is_admin = (isinstance(current_user, Admin) or 
                   current_user.__class__.__name__ == 'Admin' or
                   hasattr(current_user, '__tablename__') and current_user.__tablename__ == 'admins')
        
        if not is_admin:
            flash('Access denied. Admin privileges required.', 'danger')
            logout_user()
            return redirect(url_for('admin_login'))
        
        return f(*args, **kwargs)
    return decorated_function

# News fetching function
def fetch_education_news():
    """Fetch education-related news from multiple Nigeria education sources"""
    if not db_connected:
        print("⚠ Cannot fetch news: PostgreSQL not connected")
        return 0
    
    # List of news sources
    news_sources = [
        'https://education.gov.ng/category/latest-news/',
        'https://guardian.ng/category/education/',
        'https://punchng.com/topics/education/',
        'https://tribuneonlineng.com/category/education/',
        'https://www.legit.ng/education/',
        'https://dailytrust.com/topics/education/',
        'https://www.nerdc.gov.ng/',
        'https://thenigeriaeducationnews.com'
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    education_keywords = ['education', 'teacher', 'school', 'university', 'student', 'teaching', 'learn', 
                         'nigeria', 'nigerian', 'academic', 'curriculum', 'examination', 'exam', 'graduate',
                         'scholarship', 'education ministry', 'WAEC', 'JAMB', 'UNILAG', 'ABU', 'LASU', 'polytechnic',
                         'college', 'tuition', 'scholarship', 'bursary', 'education board']
    
    total_articles = 0
    
    with app.app_context():
        for source_url in news_sources:
            try:
                print(f"Fetching from: {source_url}")
                response = requests.get(source_url, headers=headers, timeout=15)
                if response.status_code != 200:
                    print(f"  ⚠ Failed to fetch from {source_url}: HTTP {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                articles = []
                
                # Extract base URL for relative link resolution
                from urllib.parse import urljoin, urlparse
                base_url = f"{urlparse(source_url).scheme}://{urlparse(source_url).netloc}"
                
                # Find article links - try multiple selectors
                article_links = []
                
                # Try common article link patterns
                selectors = [
                    'a[href*="article"]', 'a[href*="news"]', 'a[href*="story"]',
                    'article a', '.article a', '.news-item a', '.post-title a',
                    'h2 a', 'h3 a', 'h4 a', '.entry-title a', '.title a'
                ]
                
                for selector in selectors:
                    links = soup.select(selector)
                    if links:
                        article_links.extend(links)
                        break
                
                # Fallback: get all links
                if not article_links:
                    article_links = soup.find_all('a', href=True)
                
                # Limit per source but increase it to get more articles
                max_links_per_source = 300
                for link in article_links[:max_links_per_source]:  # Check up to 300 links per source
                    try:
                        href = link.get('href', '')
                        if not href:
                            continue
                        
                        # Resolve relative URLs
                        full_url = urljoin(source_url, href)
                        
                        # Skip non-article links (but be less strict - allow some category pages)
                        if any(skip in full_url.lower() for skip in ['javascript:', 'mailto:', '#']):
                            continue
                        
                        # Skip obvious non-article pages but allow category pages from education sources
                        if any(skip in full_url.lower() for skip in ['tag/', 'author/', '?page=']):
                            # Allow page numbers in some cases
                            if '?page=' in full_url.lower() and 'page=' not in full_url.lower().split('/')[-1]:
                                continue
                        
                        title = link.get_text(strip=True)
                        
                        # Also try to get title from parent or nearby elements
                        if not title or len(title) < 10:
                            parent = link.parent
                            if parent:
                                # Try h1-h6 tags
                                heading = parent.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                                if heading:
                                    title = heading.get_text(strip=True)
                                else:
                                    title = parent.get_text(strip=True)[:200]  # Limit length
                        
                        if not title or len(title) < 15:
                            continue
                        
                        # Since we're on education category pages, assume articles are education-related
                        # But still check for relevance
                        title_lower = title.lower()
                        is_education = any(keyword in title_lower for keyword in education_keywords)
                        
                        # For education category pages, be more lenient
                        # If the source URL contains 'education', accept most articles
                        is_education_category = 'education' in source_url.lower()
                        
                        if not is_education and is_education_category:
                            # On education category pages, check surrounding context more leniently
                            parent = link.parent
                            check_depth = 0
                            while parent and not is_education and check_depth < 5:
                                parent_text = parent.get_text(strip=True).lower()
                                if len(parent_text) > 30:  # More lenient - check smaller text blocks
                                    is_education = any(keyword in parent_text for keyword in education_keywords)
                                parent = parent.parent
                                check_depth += 1
                                if parent and parent.name == 'body':  # Stop at body
                                    break
                        
                        # On education category pages, accept most articles unless clearly not education
                        if is_education_category and not is_education:
                            # Check if title contains clearly non-education words
                            exclude_words = ['sports', 'entertainment', 'politics', 'technology', 'business']
                            if not any(exclude in title_lower for exclude in exclude_words):
                                # Accept it if we're on an education category page
                                is_education = True
                        
                        if is_education:
                            # Try to find image
                            image_url = None
                            
                            # Check link for img
                            img_tag = link.find('img')
                            if img_tag:
                                image_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src') or img_tag.get('data-original')
                            
                            # Check parent for img
                            if not image_url:
                                parent = link.parent
                                for _ in range(3):  # Check up to 3 levels up
                                    if parent:
                                        parent_img = parent.find('img')
                                        if parent_img:
                                            image_url = parent_img.get('src') or parent_img.get('data-src') or parent_img.get('data-lazy-src') or parent_img.get('data-original')
                                            if image_url:
                                                break
                                        parent = parent.parent
                            
                            # Resolve relative image URLs
                            if image_url and not image_url.startswith('http'):
                                image_url = urljoin(source_url, image_url)
                            
                            # Skip if title is too short or empty (filter empty articles)
                            if not title or len(title.strip()) < 15:
                                continue
                            
                            # Check if article already exists
                            existing = NewsArticle.query.filter_by(source_url=full_url).first()
                            if not existing:
                                # Create new article
                                article = NewsArticle(
                                    title=title[:500],  # Limit title length
                                    source_url=full_url,
                                    image_url=image_url[:1000] if image_url else None,  # Limit URL length
                                    category='Education',
                                    published_at=datetime.utcnow(),
                                    fetched_at=datetime.utcnow(),
                                    is_education_related=True
                                )
                                articles.append(article)
                            else:
                                # Article exists, but keep it in potential list for fallback
                                potential_article = {
                                    'title': title[:500],
                                    'source_url': full_url,
                                    'image_url': image_url[:1000] if image_url else None
                                }
                                articles.append(potential_article)
                    except Exception as e:
                        continue  # Skip problematic links
                
                # Save articles to database
                new_articles = []
                existing_urls = set()
                
                for article in articles:
                    # Check if it's a dict (potential/existing article) or NewsArticle object (new)
                    if isinstance(article, dict):
                        # Check if we already have this in our new_articles list
                        if article['source_url'] not in existing_urls:
                            # Check if it exists in database
                            existing = NewsArticle.query.filter_by(source_url=article['source_url']).first()
                            if not existing:
                                # Skip if title is too short or empty
                                if article['title'] and len(article['title'].strip()) >= 15:
                                    new_article = NewsArticle(
                                        title=article['title'],
                                        source_url=article['source_url'],
                                        image_url=article['image_url'],
                                        category='Education',
                                        published_at=datetime.utcnow(),
                                        fetched_at=datetime.utcnow(),
                                        is_education_related=True
                                    )
                                    new_articles.append(new_article)
                                    existing_urls.add(article['source_url'])
                    else:
                        # It's a NewsArticle object (new article)
                        if article.source_url not in existing_urls:
                            new_articles.append(article)
                            existing_urls.add(article.source_url)
                
                if new_articles:
                    for article in new_articles:
                        db.session.add(article)
                    db.session.commit()
                    total_articles += len(new_articles)
                    print(f"  ✓ Added {len(new_articles)} new articles from {source_url}")
                    
                    # Limit to max 50 articles per source per fetch to avoid overwhelming
                    if len(new_articles) > 50:
                        print(f"  ℹ Limited to 50 articles per source (found {len(new_articles)})")
                else:
                    # If no new articles, fetch the last articles from this source (update existing ones)
                    # Get the last 30 articles we have from this source domain (only education-related, non-empty)
                    source_domain = urlparse(source_url).netloc
                    existing_articles = NewsArticle.query.filter(
                        NewsArticle.source_url.like(f'%{source_domain}%'),
                        NewsArticle.is_education_related == True,
                        NewsArticle.title.isnot(None),
                        NewsArticle.title != '',
                        func.length(NewsArticle.title) >= 15
                    ).order_by(NewsArticle.fetched_at.desc()).limit(30).all()
                    
                    # Update their fetched_at timestamp to show they're still relevant
                    if existing_articles:
                        for article in existing_articles:
                            article.fetched_at = datetime.utcnow()
                        db.session.commit()
                        print(f"  ℹ No new articles from {source_url}, updated {len(existing_articles)} existing articles")
                    else:
                        print(f"  ℹ No articles found from {source_url}")
                    
            except Exception as e:
                print(f"  ⚠ Error fetching from {source_url}: {e}")
                continue
    
    if total_articles > 0:
        print(f"✓ Total articles added: {total_articles}")
    
    return total_articles

# Background thread for fetching news
def news_fetcher_thread():
    """Background thread to periodically fetch news"""
    if not db_connected:
        print("⚠ News fetcher thread not started - PostgreSQL not connected")
        return
    
    while True:
        try:
            if db_connected:
                with app.app_context():
                    fetch_education_news()
            time.sleep(3600)  # Fetch every hour
        except Exception as e:
            print(f"⚠ Error in news fetcher thread: {e}")
            time.sleep(3600)

# Routes
@app.route('/')
def index():
    """Homepage"""
    # Get latest news articles (filter out non-education related and empty articles)
    if db_connected:
        news_articles = NewsArticle.query.filter(
            NewsArticle.is_education_related == True,
            NewsArticle.title.isnot(None),
            NewsArticle.title != '',
            func.length(NewsArticle.title) >= 15  # Minimum title length
        ).order_by(NewsArticle.fetched_at.desc()).limit(10).all()
    else:
        news_articles = []
    
    # Get latest blog posts
    if db_connected:
        latest_posts = BlogPost.query.order_by(BlogPost.created_at.desc()).limit(6).all()
    else:
        latest_posts = []
    
    # Get active adverts for carousel (not expired) - cleanup before querying
    if db_connected:
        cleanup_expired_adverts()
        now = datetime.utcnow()
        # Include both 'active' and 'approved' status for backwards compatibility
        # Also handle NULL start_date in ordering
        approved_adverts = Advert.query.filter(
            (Advert.status == 'active') | (Advert.status == 'approved'),
            Advert.payment_status == 'paid',
            (Advert.end_date.is_(None) | (Advert.end_date > now))
        ).order_by(
            nullslast(Advert.start_date.desc())  # Handle NULL start_date
        ).all()
    else:
        approved_adverts = []
    
    return render_template('index.html', 
                         news_articles=news_articles, 
                         latest_posts=latest_posts,
                         approved_adverts=approved_adverts,
                         user=current_user if current_user.is_authenticated else None)

@app.route('/contact')
def contact():
    """Contact support page"""
    return render_template('contact.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        
        # Validation
        if not username or not email or not password:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose another.', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'danger')
            return redirect(url_for('login'))
        
        # Create new user (active immediately, no email verification required)
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            is_active=True,  # Active immediately
            email_verified=True  # No email verification required
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Send welcome email (optional, non-blocking)
        try:
            send_welcome_email(user)
        except Exception as e:
            print(f"Error sending welcome email: {e}")
        
        # Log activity
        activity = UserActivity(
            user_id=user.id,
            action='registration',
            description=f'User {username} registered'
        )
        db.session.add(activity)
        db.session.commit()
        
        flash('Registration successful! You can now log in to your account.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    # If already logged in, redirect to home
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return redirect(url_for('login'))
        
        try:
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password):
                if not user.is_active:
                    flash('Your account has been deactivated. Please contact admin for assistance.', 'danger')
                    return redirect(url_for('login'))
                
                login_user(user, remember=True)
                
                # Update last login
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                # Log activity
                try:
                    activity = UserActivity(
                        user_id=user.id,
                        action='login',
                        description=f'User {username} logged in'
                    )
                    db.session.add(activity)
                    db.session.commit()
                except Exception as e:
                    print(f"Error logging activity: {e}")
                
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                else:
                    flash(f'Welcome back, {user.full_name or user.username}!', 'success')
                    return redirect(url_for('index'))
            
            flash('Invalid username or password.', 'danger')
        except Exception as e:
            print(f"Login error: {e}")
            flash('An error occurred during login. Please try again.', 'danger')
    
    return render_template('login.html')

@app.route('/activate/<token>')
def activate_account(token):
    """Activate user account via email token"""
    try:
        email_token = EmailToken.query.filter_by(token=token, token_type='activation', used=False).first()
        
        if not email_token:
            flash('Invalid or expired activation link.', 'danger')
            return redirect(url_for('login'))
        
        if email_token.expires_at < datetime.utcnow():
            flash('Activation link has expired. Please register again.', 'danger')
            email_token.used = True
            db.session.commit()
            return redirect(url_for('register'))
        
        user = User.query.get(email_token.user_id)
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('register'))
        
        # Activate user
        user.is_active = True
        user.email_verified = True
        email_token.used = True
        db.session.commit()
        
        # Send welcome email after successful activation
        try:
            send_welcome_email(user)
        except Exception as e:
            print(f"Error sending welcome email: {e}")
        
        flash('Account activated successfully! You can now log in. Check your email for a welcome message!', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        print(f"Activation error: {e}")
        flash('An error occurred during activation. Please try again or contact support.', 'danger')
        return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Send password reset email
            if send_password_reset_email(user):
                flash('Password reset link has been sent to your email.', 'success')
            else:
                flash('Could not send reset email. Please try again later or contact support.', 'danger')
        else:
            # Don't reveal if email exists or not (security)
            flash('If an account exists with that email, a password reset link has been sent.', 'success')
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password via token"""
    email_token = EmailToken.query.filter_by(token=token, token_type='password_reset', used=False).first()
    
    if not email_token:
        flash('Invalid or expired password reset link.', 'danger')
        return redirect(url_for('forgot_password'))
    
    if email_token.expires_at < datetime.utcnow():
        flash('Password reset link has expired. Please request a new one.', 'danger')
        email_token.used = True
        db.session.commit()
        return redirect(url_for('forgot_password'))
    
    user = User.query.get(email_token.user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Please fill in all fields.', 'danger')
            return render_template('reset_password.html', token=token)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('reset_password.html', token=token)
        
        # Reset password
        user.set_password(password)
        email_token.used = True
        db.session.commit()
        
        # Send password change confirmation email
        try:
            send_password_change_confirmation_email(user)
        except Exception as e:
            print(f"Error sending password change confirmation email: {e}")
        
        flash('Password reset successfully! You can now log in with your new password. A confirmation email has been sent.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Profile page - view and edit profile information for users and admins"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    # Check if current user is admin or regular user
    is_admin = current_user.__class__.__name__ == 'Admin'
    
    if request.method == 'POST':
        try:
            # Determine which form was submitted
            form_type = request.form.get('form_type', 'picture')
            
            if form_type == 'picture' and not is_admin:
                # Handle profile picture upload (only for regular users)
                profile_picture_url = current_user.profile_picture  # Keep existing by default
                
                # Check if profile picture file was uploaded
                if 'profile_picture' in request.files:
                    profile_file = request.files['profile_picture']
                    if profile_file and profile_file.filename:
                        # Validate file type
                        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                        filename = secure_filename(profile_file.filename)
                        if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                            # Upload to ImageKit
                            uploaded_url = upload_image_to_imagekit(profile_file, folder_name='profiles')
                            if uploaded_url:
                                profile_picture_url = uploaded_url
                            else:
                                flash('Failed to upload profile picture. Please try again or use an image URL.', 'warning')
                
                # Handle profile picture URL input
                profile_url_input = request.form.get('profile_picture_url', '').strip()
                if 'profile_picture' not in request.files or not request.files['profile_picture'].filename:
                    if profile_url_input:
                        profile_picture_url = profile_url_input
                    elif not profile_url_input and 'remove_picture' in request.form:
                        profile_picture_url = None
                
                # Update profile picture
                current_user.profile_picture = profile_picture_url
                db.session.commit()
                
                flash('Profile picture updated successfully!', 'success')
                
            elif form_type == 'info':
                # Handle profile information update (username for both, full_name only for users)
                new_username = request.form.get('username', '').strip()
                
                # Validate username
                if not new_username:
                    flash('Username cannot be empty.', 'danger')
                    return redirect(url_for('profile'))
                
                # Check if username is being changed and if it already exists
                if new_username != current_user.username:
                    # Check in appropriate table based on user type
                    if is_admin:
                        existing = Admin.query.filter_by(username=new_username).first()
                    else:
                        existing = User.query.filter_by(username=new_username).first()
                    
                    if existing:
                        flash('This username is already taken. Please choose another.', 'danger')
                        return redirect(url_for('profile'))
                
                # Update username for both users and admins
                current_user.username = new_username
                
                # Update full_name only for regular users (admins don't have this field)
                if not is_admin:
                    new_full_name = request.form.get('full_name', '').strip()
                    current_user.full_name = new_full_name if new_full_name else None
                
                db.session.commit()
                
                # Log activity only for regular users
                if not is_admin:
                    activity = UserActivity(
                        user_id=current_user.id,
                        action='update_profile',
                        description=f'User updated profile information'
                    )
                    db.session.add(activity)
                    db.session.commit()
                
                flash('Profile information updated successfully!', 'success')
                
            elif form_type == 'password':
                # Handle password change (works for both users and admins)
                current_password = request.form.get('current_password', '')
                new_password = request.form.get('new_password', '')
                confirm_password = request.form.get('confirm_password', '')
                
                # Validate fields
                if not current_password or not new_password or not confirm_password:
                    flash('Please fill in all password fields.', 'danger')
                    return redirect(url_for('profile'))
                
                # Verify current password
                if not current_user.check_password(current_password):
                    flash('Current password is incorrect.', 'danger')
                    return redirect(url_for('profile'))
                
                # Check if new passwords match
                if new_password != confirm_password:
                    flash('New passwords do not match.', 'danger')
                    return redirect(url_for('profile'))
                
                # Validate password length
                if len(new_password) < 6:
                    flash('Password must be at least 6 characters long.', 'danger')
                    return redirect(url_for('profile'))
                
                # Update password
                current_user.set_password(new_password)
                db.session.commit()
                
                # Log activity only for regular users
                if not is_admin:
                    activity = UserActivity(
                        user_id=current_user.id,
                        action='change_password',
                        description=f'User changed password'
                    )
                    db.session.add(activity)
                    db.session.commit()
                
                flash('Password changed successfully!', 'success')
            
            return redirect(url_for('profile'))
            
        except Exception as e:
            print(f"Error updating profile: {e}")
            db.session.rollback()
            flash('An error occurred while updating your profile. Please try again.', 'danger')
            return redirect(url_for('profile'))
    
    return render_template('profile.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    # Check if user is admin before logging activity
    is_admin = current_user.__class__.__name__ == 'Admin'
    
    if current_user.is_authenticated and db_connected and not is_admin:
        # Log activity only for regular users
        try:
            activity = UserActivity(
                user_id=current_user.id,
                action='logout',
                description=f'User {current_user.username} logged out'
            )
            db.session.add(activity)
            db.session.commit()
        except Exception as e:
            print(f"Error logging logout activity: {e}")
            db.session.rollback()
    
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    # If already logged in as admin, redirect to dashboard
    if current_user.is_authenticated:
        # Check if current user is an admin
        is_admin = (isinstance(current_user, Admin) or 
                   current_user.__class__.__name__ == 'Admin' or
                   hasattr(current_user, '__tablename__') and current_user.__tablename__ == 'admins')
        if is_admin:
            return redirect(url_for('admin_dashboard'))
        # If logged in as regular user, logout first
        else:
            logout_user()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('admin_login.html')
        
        try:
            # Logout any existing user session first
            if current_user.is_authenticated:
                logout_user()
            
            admin = Admin.query.filter_by(username=username).first()
            
            if not admin:
                flash('Invalid admin credentials.', 'danger')
                return render_template('admin_login.html')
            
            # Verify password
            if not admin.check_password(password):
                flash('Invalid admin credentials.', 'danger')
                return render_template('admin_login.html')
            
            # Login the admin
            login_user(admin, remember=True)
            flash('Welcome, Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            print(f"Admin login error: {e}")
            import traceback
            traceback.print_exc()
            flash('An error occurred during login. Please try again.', 'danger')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    total_posts = BlogPost.query.count()
    total_news = NewsArticle.query.count()
    total_adverts = Advert.query.count()
    pending_adverts = Advert.query.filter_by(status='pending').count()
    
    recent_activities = UserActivity.query.order_by(UserActivity.timestamp.desc()).limit(4).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         active_users=active_users,
                         total_posts=total_posts,
                         total_news=total_news,
                         total_adverts=total_adverts,
                         pending_adverts=pending_adverts,
                         recent_activities=recent_activities,
                         recent_users=recent_users)

@app.route('/admin/users')
@admin_required
def admin_users():
    """Admin - View all users"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    """Admin - Toggle user active status"""
    try:
        user = User.query.get(user_id)
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('admin_users'))
        
        old_status = user.is_active
        user.is_active = not user.is_active
        db.session.commit()
        
        # Send account status change email notification
        try:
            send_account_status_change_email(user, user.is_active)
        except Exception as e:
            print(f"Error sending account status change email: {e}")
        
        action = 'activated' if user.is_active else 'deactivated'
        flash(f'User {user.username} has been {action}. User has been notified via email.', 'success')
    except Exception as e:
        flash('Error updating user status.', 'danger')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Admin - Delete user and all related data"""
    try:
        user = User.query.get(user_id)
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('admin_users'))
        
        # Prevent regular users from deleting themselves (if they somehow access this)
        # Admins can delete any regular user
        if isinstance(current_user, User) and current_user.id == user_id:
            flash('You cannot delete your own account. Please contact an admin.', 'danger')
            return redirect(url_for('admin_users'))
        
        # Store username for flash message
        username = user.username
        
        # Delete related records
        # Delete user's blog posts
        BlogPost.query.filter_by(author_id=user_id).delete()
        
        # Delete user's comments
        PostComment.query.filter_by(user_id=user_id).delete()
        
        # Delete user's adverts
        Advert.query.filter_by(submitted_by=user_id).delete()
        
        # Delete user's activities
        UserActivity.query.filter_by(user_id=user_id).delete()
        
        # Delete user's email tokens
        EmailToken.query.filter_by(user_id=user_id).delete()
        
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        
        flash(f'User {username} and all related data have been deleted successfully.', 'success')
    except Exception as e:
        print(f"Error deleting user: {e}")
        db.session.rollback()
        flash('Error deleting user. Please try again.', 'danger')
    
    return redirect(url_for('admin_users'))

@app.route('/news')
def news():
    """News page"""
    if not db_connected:
        return render_template('news.html', news_articles=[], page=1, total_pages=0)
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filter out non-education related and empty articles
    base_query = NewsArticle.query.filter(
        NewsArticle.is_education_related == True,
        NewsArticle.title.isnot(None),
        NewsArticle.title != '',
        func.length(NewsArticle.title) >= 15  # Minimum title length
    )
    
    # Get total count and paginate
    pagination = base_query.order_by(NewsArticle.fetched_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    news_articles = pagination
    
    return render_template('news.html', news_articles=news_articles)

@app.route('/api/fetch-news', methods=['POST'])
@admin_required
def api_fetch_news():
    """API endpoint to manually fetch news"""
    with app.app_context():
        count = fetch_education_news()
    return jsonify({'success': True, 'articles_added': count})

@app.route('/blog', methods=['GET'])
def blog():
    """View all blog posts"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    try:
        pagination = BlogPost.query.order_by(BlogPost.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        posts = pagination.items
    except Exception as e:
        print(f"Error fetching blog posts: {e}")
        posts = []
        pagination = None
    
    # Get active adverts for sidebar (not expired) - cleanup before querying
    if db_connected:
        cleanup_expired_adverts()
        now = datetime.utcnow()
        # Include both 'active' and 'approved' status for backwards compatibility
        # Also handle NULL start_date in ordering
        approved_adverts = Advert.query.filter(
            (Advert.status == 'active') | (Advert.status == 'approved'),
            Advert.payment_status == 'paid',
            (Advert.end_date.is_(None) | (Advert.end_date > now))
        ).order_by(
            nullslast(Advert.start_date.desc())  # Handle NULL start_date
        ).limit(5).all()
    else:
        approved_adverts = []
    
    return render_template('blog.html', posts=posts, pagination=pagination, approved_adverts=approved_adverts)

@app.route('/blog/create', methods=['GET', 'POST'])
@login_required
def create_post():
    """Create a new blog post - Regular users only (admins use /admin/post/create)"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    # Admins cannot create posts here - they must use the admin_create_post route
    # because BlogPost.author_id references users.id, not admins.id
    if current_user.__class__.__name__ == 'Admin':
        flash('Admins should use the admin dashboard to create posts.', 'warning')
        return redirect(url_for('blog'))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        image_url = request.form.get('image_url', '').strip()
        
        if not title or not content:
            flash('Please provide both title and content.', 'danger')
            return render_template('create_post.html')
        
        if len(title) > 500:
            flash('Title is too long. Maximum 500 characters.', 'danger')
            return render_template('create_post.html')
        
        try:
            # Handle image upload
            final_image_url = None
            
            # Check if image file was uploaded
            if 'image_file' in request.files:
                image_file = request.files['image_file']
                if image_file and image_file.filename:
                    # Validate file type
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = secure_filename(image_file.filename)
                    if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        # Upload to ImageKit
                        final_image_url = upload_image_to_imagekit(image_file, folder_name='posts')
                        if not final_image_url:
                            flash('Failed to upload image. Please try again or use an image URL.', 'warning')
            
            # If no file upload, use URL if provided
            if not final_image_url and image_url:
                final_image_url = image_url
            
            # Create new blog post
            post = BlogPost(
                title=title,
                content=content,
                image_url=final_image_url,
                author_id=current_user.id
            )
            db.session.add(post)
            db.session.commit()
            
            # Log activity
            activity = UserActivity(
                user_id=current_user.id,
                action='create_post',
                description=f'User {current_user.username} created blog post: {title[:50]}'
            )
            db.session.add(activity)
            db.session.commit()
            
            flash('Blog post created successfully!', 'success')
            return redirect(url_for('post_detail', post_id=post.id))
        
        except Exception as e:
            print(f"Error creating blog post: {e}")
            db.session.rollback()
            flash('An error occurred while creating the post. Please try again.', 'danger')
    
    return render_template('create_post.html')

@app.route('/blog/post/<int:post_id>')
def post_detail(post_id):
    """View individual blog post"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    try:
        post = BlogPost.query.get_or_404(post_id)
        
        # Get related posts (by same author)
        related_posts = BlogPost.query.filter(
            BlogPost.author_id == post.author_id,
            BlogPost.id != post.id
        ).order_by(BlogPost.created_at.desc()).limit(3).all()
        
        # Get comments for this post
        comments = PostComment.query.filter_by(post_id=post_id).order_by(PostComment.created_at.asc()).all()
        
        return render_template('post_detail.html', post=post, related_posts=related_posts, comments=comments)
    except Exception as e:
        print(f"Error fetching blog post: {e}")
        flash('Blog post not found.', 'danger')
        return redirect(url_for('blog'))

@app.route('/blog/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    """Add a comment to a blog post"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('post_detail', post_id=post_id))
    
    # Prevent admins from commenting (they can create posts instead)
    if current_user.__class__.__name__ == 'Admin':
        flash('Admins cannot post comments. Please create a blog post instead.', 'warning')
        return redirect(url_for('post_detail', post_id=post_id))
    
    try:
        post = BlogPost.query.get_or_404(post_id)
        
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('Comment cannot be empty.', 'danger')
            return redirect(url_for('post_detail', post_id=post_id))
        
        # Create comment
        comment = PostComment(
            post_id=post_id,
            user_id=current_user.id,
            content=content
        )
        db.session.add(comment)
        db.session.commit()
        
        # Log activity
        try:
            activity = UserActivity(
                user_id=current_user.id,
                action='comment',
                description=f'User {current_user.username} commented on post: {post.title[:50]}'
            )
            db.session.add(activity)
            db.session.commit()
        except Exception as e:
            print(f"Error logging activity: {e}")
        
        flash('Comment added successfully!', 'success')
        return redirect(url_for('post_detail', post_id=post_id))
    
    except Exception as e:
        print(f"Error adding comment: {e}")
        db.session.rollback()
        flash('An error occurred while adding the comment. Please try again.', 'danger')
        return redirect(url_for('post_detail', post_id=post_id))

@app.route('/blog/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    """Edit a blog post - All users and admins can edit any post"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    try:
        post = BlogPost.query.get_or_404(post_id)
        
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            image_url = request.form.get('image_url', '').strip()
            
            if not title or not content:
                flash('Please provide both title and content.', 'danger')
                return render_template('edit_post.html', post=post)
            
            if len(title) > 500:
                flash('Title is too long. Maximum 500 characters.', 'danger')
                return render_template('edit_post.html', post=post)
            
            try:
                # Handle image upload
                final_image_url = post.image_url  # Keep existing image by default
                
                # Check if image file was uploaded
                if 'image_file' in request.files:
                    image_file = request.files['image_file']
                    if image_file and image_file.filename:
                        # Validate file type
                        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                        filename = secure_filename(image_file.filename)
                        if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                            # Upload to ImageKit
                            uploaded_url = upload_image_to_imagekit(image_file, folder_name='posts')
                            if uploaded_url:
                                final_image_url = uploaded_url
                            else:
                                flash('Failed to upload image. Keeping existing image.', 'warning')
                
                # If no file upload, use URL if provided (or keep existing)
                if 'image_file' not in request.files or not request.files['image_file'].filename:
                    if image_url:
                        final_image_url = image_url
                    elif not image_url:
                        # User might have cleared the URL, so set to None
                        final_image_url = None
                
                post.title = title
                post.content = content
                post.image_url = final_image_url
                db.session.commit()
                
                # Log activity only for regular users
                is_admin = current_user.__class__.__name__ == 'Admin'
                if not is_admin:
                    activity = UserActivity(
                        user_id=current_user.id,
                        action='edit_post',
                        description=f'User {current_user.username} edited blog post: {title[:50]}'
                    )
                    db.session.add(activity)
                    db.session.commit()
                
                flash('Blog post updated successfully!', 'success')
                return redirect(url_for('post_detail', post_id=post.id))
            
            except Exception as e:
                print(f"Error updating blog post: {e}")
                db.session.rollback()
                flash('An error occurred while updating the post. Please try again.', 'danger')
        
        return render_template('edit_post.html', post=post)
    
    except Exception as e:
        print(f"Error fetching blog post: {e}")
        flash('Blog post not found.', 'danger')
        return redirect(url_for('blog'))

@app.route('/blog/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    """Delete a blog post"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('index'))
    
    try:
        post = BlogPost.query.get_or_404(post_id)
        
        # Only admins can delete posts (all users can see delete button but only admins can actually delete)
        # This check ensures that only admins can delete, matching the template restriction
        if current_user.__class__.__name__ != 'Admin':
            flash('You do not have permission to delete this post.', 'danger')
            return redirect(url_for('post_detail', post_id=post_id))
        
        post_title = post.title
        
        # Log activity (note: admins can delete posts but shouldn't log to UserActivity)
        # The check above ensures we're here as an admin, so skip logging to avoid FK errors
        # Admin activities are not tracked in user_activities table
        # if not is_admin:
        #     activity = UserActivity(...)
        #     db.session.add(activity)
        
        db.session.delete(post)
        db.session.commit()
        
        flash('Blog post deleted successfully!', 'success')
        return redirect(url_for('blog'))
    
    except Exception as e:
        print(f"Error deleting blog post: {e}")
        db.session.rollback()
        flash('An error occurred while deleting the post. Please try again.', 'danger')
        return redirect(url_for('blog'))

@app.route('/advert/submit', methods=['GET', 'POST'])
@login_required
def submit_advert():
    """User advert submission"""
    # Get advert pricing (admin-set per week)
    pricing = AdvertPricing.query.first()
    price_per_week = float(pricing.amount) if pricing else 500.00
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        link_url = request.form.get('link_url', '').strip()
        button_text = request.form.get('button_text', 'Learn More').strip()
        weeks = request.form.get('weeks', type=int) or 1
        
        # Validate weeks (minimum 1, maximum 52)
        if weeks < 1:
            weeks = 1
        elif weeks > 52:
            weeks = 52
        
        # Calculate total amount (weeks * price_per_week)
        total_amount = weeks * price_per_week
        
        if not title:
            flash('Title is required.', 'danger')
            return render_template('submit_advert.html', price_per_week=price_per_week)
        
        # Handle image upload or URL
        image_url = None
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename:
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                filename = secure_filename(file.filename)
                
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    # Upload to ImageKit
                    image_url = upload_image_to_imagekit(file, folder_name='adverts')
                    if not image_url:
                        flash('Failed to upload image. Please try again or use an image URL.', 'warning')
                else:
                    flash('Invalid image file type. Please upload PNG, JPG, JPEG, GIF, or WEBP.', 'danger')
                    return render_template('submit_advert.html', price_per_week=price_per_week)
        
        # If no file upload, check for image URL
        if not image_url:
            image_url = request.form.get('image_url', '').strip()
            if not image_url:
                image_url = None
        
        advert = Advert(
            title=title,
            description=description,
            image_url=image_url,
            link_url=link_url,
            button_text=button_text,
            submitted_by=current_user.id,
            amount=total_amount,  # Total amount = weeks * price_per_week
            weeks=weeks,
            status='pending',
            payment_status='pending'
        )
        
        db.session.add(advert)
        db.session.commit()
        
        # Log activity
        activity = UserActivity(
            user_id=current_user.id,
            action='advert_submission',
            description=f'User {current_user.username} submitted advert: {title} for {weeks} week(s)'
        )
        db.session.add(activity)
        db.session.commit()
        
        # Redirect directly to payment page
        flash(f'Please complete payment of ₦{total_amount:,.2f} to activate your advert for {weeks} week(s).', 'info')
        return redirect(url_for('pay_advert', advert_id=advert.id))
    
    return render_template('submit_advert.html', price_per_week=price_per_week)

def cleanup_expired_adverts():
    """Delete expired adverts automatically"""
    try:
        now = datetime.utcnow()
        expired_adverts = Advert.query.filter(
            Advert.end_date.isnot(None),
            Advert.end_date <= now,
            Advert.status == 'active'
        ).all()
        
        for advert in expired_adverts:
            # Log activity before deletion
            try:
                if advert.submitted_by:
                    activity = UserActivity(
                        user_id=advert.submitted_by,
                        action='advert_expired',
                        description=f'Advert "{advert.title}" expired and was automatically deleted'
                    )
                    db.session.add(activity)
            except Exception as e:
                print(f"Error logging expired advert activity: {e}")
            
            # Delete the expired advert
            db.session.delete(advert)
        
        if expired_adverts:
            db.session.commit()
            print(f"✓ Cleaned up {len(expired_adverts)} expired adverts")
        
        return len(expired_adverts)
    except Exception as e:
        print(f"Error cleaning up expired adverts: {e}")
        db.session.rollback()
        return 0

@app.route('/adverts/my')
@login_required
def my_adverts():
    """User's adverts"""
    # Cleanup expired adverts before showing user's adverts
    cleanup_expired_adverts()
    
    adverts = Advert.query.filter_by(submitted_by=current_user.id).order_by(Advert.submitted_at.desc()).all()
    return render_template('my_adverts.html', adverts=adverts)

@app.route('/advert/<int:advert_id>')
def advert_detail(advert_id):
    """View full advert details - public page"""
    advert = Advert.query.get_or_404(advert_id)
    
    # Only show active or approved adverts to public
    if advert.status not in ['active', 'approved']:
        if current_user.is_authenticated and current_user.id == advert.submitted_by:
            # Allow owner to see their own adverts in any status
            pass
        else:
            flash('This advertisement is not currently active.', 'warning')
            return redirect(url_for('index'))
    
    # Get related adverts (other active adverts from the same user)
    related_adverts = Advert.query.filter(
        Advert.id != advert.id,
        Advert.submitted_by == advert.submitted_by,
        Advert.status.in_(['active', 'approved'])
    ).limit(3).all()
    
    return render_template('advert_detail.html', advert=advert, related_adverts=related_adverts)

@app.route('/advert/<int:advert_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_advert(advert_id):
    """Edit advert - users can edit their own adverts"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('my_adverts'))
    
    advert = Advert.query.get_or_404(advert_id)
    
    # Check if user owns this advert
    if advert.submitted_by != current_user.id:
        flash('You do not have permission to edit this advert.', 'danger')
        return redirect(url_for('my_adverts'))
    
    # Get advert pricing
    pricing = AdvertPricing.query.first()
    price_per_week = float(pricing.amount) if pricing else 500.00
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        link_url = request.form.get('link_url', '').strip()
        button_text = request.form.get('button_text', 'Learn More').strip()
        image_url_input = request.form.get('image_url', '').strip()
        
        if not title:
            flash('Title is required.', 'danger')
            return render_template('edit_advert.html', advert=advert, price_per_week=price_per_week)
        
        try:
            # Handle image upload or URL
            image_url = None
            
            # Check if image file was uploaded
            if 'image_file' in request.files:
                file = request.files['image_file']
                if file and file.filename:
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = secure_filename(file.filename)
                    
                    if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        # Upload to ImageKit
                        image_url = upload_image_to_imagekit(file, folder_name='adverts')
                        if not image_url:
                            flash('Failed to upload image. Please try again or use an image URL.', 'warning')
                    else:
                        flash('Invalid image file type. Please upload PNG, JPG, JPEG, GIF, or WEBP.', 'danger')
                        return render_template('edit_advert.html', advert=advert, price_per_week=price_per_week)
            
            # If no file upload, use URL if provided
            if not image_url and image_url_input:
                image_url = image_url_input
            
            # Update advert
            advert.title = title
            advert.description = description if description else None
            if image_url:
                advert.image_url = image_url
            advert.link_url = link_url if link_url else None
            advert.button_text = button_text if button_text else 'Learn More'
            
            db.session.commit()
            
            # Log activity
            activity = UserActivity(
                user_id=current_user.id,
                action='edit_advert',
                description=f'User {current_user.username} edited advert: {title}'
            )
            db.session.add(activity)
            db.session.commit()
            
            flash('Advert updated successfully!', 'success')
            return redirect(url_for('my_adverts'))
        
        except Exception as e:
            print(f"Error updating advert: {e}")
            db.session.rollback()
            flash('An error occurred while updating the advert. Please try again.', 'danger')
    
    return render_template('edit_advert.html', advert=advert, price_per_week=price_per_week)

@app.route('/admin/adverts')
@admin_required
def admin_adverts():
    """Admin - View all adverts"""
    # Cleanup expired adverts before showing admin adverts
    cleanup_expired_adverts()
    
    adverts = Advert.query.order_by(Advert.submitted_at.desc()).all()
    return render_template('admin_adverts.html', adverts=adverts)

@app.route('/admin/advert/<int:advert_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_advert(advert_id):
    """Admin - Edit any advert"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('admin_adverts'))
    
    advert = Advert.query.get_or_404(advert_id)
    
    # Get advert pricing
    pricing = AdvertPricing.query.first()
    price_per_week = float(pricing.amount) if pricing else 500.00
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        link_url = request.form.get('link_url', '').strip()
        button_text = request.form.get('button_text', 'Learn More').strip()
        image_url_input = request.form.get('image_url', '').strip()
        
        if not title:
            flash('Title is required.', 'danger')
            return render_template('edit_advert.html', advert=advert, price_per_week=price_per_week)
        
        try:
            # Handle image upload or URL
            image_url = None
            
            # Check if image file was uploaded
            if 'image_file' in request.files:
                file = request.files['image_file']
                if file and file.filename:
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = secure_filename(file.filename)
                    
                    if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        # Upload to ImageKit
                        image_url = upload_image_to_imagekit(file, folder_name='adverts')
                        if not image_url:
                            flash('Failed to upload image. Please try again or use an image URL.', 'warning')
                    else:
                        flash('Invalid image file type. Please upload PNG, JPG, JPEG, GIF, or WEBP.', 'danger')
                        return render_template('edit_advert.html', advert=advert, price_per_week=price_per_week)
            
            # If no file upload, use URL if provided
            if not image_url and image_url_input:
                image_url = image_url_input
            
            # Update advert
            advert.title = title
            advert.description = description if description else None
            if image_url:
                advert.image_url = image_url
            advert.link_url = link_url if link_url else None
            advert.button_text = button_text if button_text else 'Learn More'
            
            db.session.commit()
            
            # Log activity
            activity = UserActivity(
                user_id=advert.submitted_by,
                action='advert_edited_by_admin',
                description=f'Admin edited advert: {title}'
            )
            db.session.add(activity)
            db.session.commit()
            
            flash('Advert updated successfully!', 'success')
            return redirect(url_for('admin_adverts'))
        
        except Exception as e:
            print(f"Error updating advert: {e}")
            db.session.rollback()
            flash('An error occurred while updating the advert. Please try again.', 'danger')
    
    return render_template('edit_advert.html', advert=advert, price_per_week=price_per_week)

@app.route('/admin/advert/<int:advert_id>/approve', methods=['POST'])
@admin_required
def approve_advert(advert_id):
    """Admin - Approve advert"""
    try:
        advert = Advert.query.get(advert_id)
        if not advert:
            flash('Advert not found.', 'danger')
            return redirect(url_for('admin_adverts'))
        
        payment_status = request.form.get('payment_status', 'paid')
        admin_notes = request.form.get('admin_notes', '')
        
        advert.status = 'approved'
        advert.payment_status = payment_status
        advert.approved_at = datetime.utcnow()
        advert.admin_notes = admin_notes
        db.session.commit()
        
        # Send approval email notification
        try:
            user = User.query.get(advert.submitted_by)
            if user:
                send_advert_approval_email(user, advert)
        except Exception as e:
            print(f"Error sending advert approval email: {e}")
        
        # Log activity
        try:
            activity = UserActivity(
                user_id=advert.submitted_by,
                action='advert_approved',
                description=f'Admin approved advert: {advert.title}'
            )
            db.session.add(activity)
            db.session.commit()
        except Exception as e:
            print(f"Error logging activity: {e}")
        
        flash(f'Advert "{advert.title}" has been approved. User has been notified via email.', 'success')
    except Exception as e:
        flash('Error approving advert.', 'danger')
    
    return redirect(url_for('admin_adverts'))

@app.route('/admin/advert/<int:advert_id>/reject', methods=['POST'])
@admin_required
def reject_advert(advert_id):
    """Admin - Reject advert"""
    try:
        advert = Advert.query.get(advert_id)
        if not advert:
            flash('Advert not found.', 'danger')
            return redirect(url_for('admin_adverts'))
        
        admin_notes = request.form.get('admin_notes', '')
        
        advert.status = 'rejected'
        advert.admin_notes = admin_notes
        db.session.commit()
        
        # Send rejection email notification
        try:
            user = User.query.get(advert.submitted_by)
            if user:
                send_advert_rejection_email(user, advert)
        except Exception as e:
            print(f"Error sending advert rejection email: {e}")
        
        flash(f'Advert "{advert.title}" has been rejected. User has been notified via email.', 'info')
    except Exception as e:
        flash('Error rejecting advert.', 'danger')
    
    return redirect(url_for('admin_adverts'))

@app.route('/admin/advert/<int:advert_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_advert(advert_id):
    """Admin - Deactivate advert (change status to rejected)"""
    try:
        advert = Advert.query.get(advert_id)
        if not advert:
            flash('Advert not found.', 'danger')
            return redirect(url_for('admin_adverts'))
        
        # Store title for flash message
        advert_title = advert.title
        
        # Deactivate by changing status to rejected
        advert.status = 'rejected'
        advert.admin_notes = (advert.admin_notes or '') + f'\n\nDeactivated by admin on {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}'
        db.session.commit()
        
        # Log activity
        try:
            activity = UserActivity(
                user_id=advert.submitted_by,
                action='advert_deactivated',
                description=f'Admin deactivated advert: {advert_title}'
            )
            db.session.add(activity)
            db.session.commit()
        except Exception as e:
            print(f"Error logging activity: {e}")
        
        flash(f'Advert "{advert_title}" has been deactivated successfully.', 'success')
    except Exception as e:
        print(f"Error deactivating advert: {e}")
        db.session.rollback()
        flash('Error deactivating advert. Please try again.', 'danger')
    
    return redirect(url_for('admin_adverts'))

@app.route('/admin/advert/<int:advert_id>/delete', methods=['POST'])
@admin_required
def delete_advert(advert_id):
    """Admin - Delete advert permanently"""
    try:
        advert = Advert.query.get(advert_id)
        if not advert:
            flash('Advert not found.', 'danger')
            return redirect(url_for('admin_adverts'))
        
        # Store title and user_id for flash message and activity
        advert_title = advert.title
        submitted_by = advert.submitted_by
        
        # Delete the advert
        db.session.delete(advert)
        db.session.commit()
        
        # Log activity
        try:
            if submitted_by:
                activity = UserActivity(
                    user_id=submitted_by,
                    action='advert_deleted',
                    description=f'Admin deleted advert: {advert_title}'
                )
                db.session.add(activity)
                db.session.commit()
        except Exception as e:
            print(f"Error logging activity: {e}")
        
        flash(f'Advert "{advert_title}" has been deleted successfully.', 'success')
    except Exception as e:
        print(f"Error deleting advert: {e}")
        db.session.rollback()
        flash('Error deleting advert. Please try again.', 'danger')
    
    return redirect(url_for('admin_adverts'))

@app.route('/admin/advert/create', methods=['GET', 'POST'])
@admin_required
def create_advert():
    """Admin - Create advert for free (automatically approved)"""
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('admin_adverts'))
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            link_url = request.form.get('link_url', '').strip()
            button_text = request.form.get('button_text', 'Learn More').strip()
            user_id = request.form.get('user_id', type=int)
            image_url = None
            
            # Validation
            if not title:
                flash('Title is required.', 'danger')
                users = User.query.filter_by(is_active=True).order_by(User.username).all()
                return render_template('admin_create_advert.html', users=users)
            
            if not user_id:
                flash('Please select a user.', 'danger')
                users = User.query.filter_by(is_active=True).order_by(User.username).all()
                return render_template('admin_create_advert.html', users=users)
            
            # Check if user exists
            user = User.query.get(user_id)
            if not user:
                flash('Selected user not found.', 'danger')
                users = User.query.filter_by(is_active=True).order_by(User.username).all()
                return render_template('admin_create_advert.html', users=users)
            
            # Handle image upload or URL
            image_url = None
            
            # Check if image file was uploaded
            if 'image_file' in request.files:
                file = request.files['image_file']
                if file and file.filename:
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = secure_filename(file.filename)
                    
                    if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        # Upload to ImageKit
                        image_url = upload_image_to_imagekit(file, folder_name='adverts')
                        if not image_url:
                            flash('Failed to upload image. Please try again or use an image URL.', 'warning')
                    else:
                        flash('Invalid image file type. Please upload PNG, JPG, JPEG, GIF, or WEBP.', 'danger')
                        users = User.query.filter_by(is_active=True).order_by(User.username).all()
                        return render_template('admin_create_advert.html', users=users)
            
            # If no file upload, check for image URL
            if not image_url:
                image_url_input = request.form.get('image_url', '').strip()
                if not image_url_input:
                    flash('Please upload an image or provide an image URL.', 'danger')
                    users = User.query.filter_by(is_active=True).order_by(User.username).all()
                    return render_template('admin_create_advert.html', users=users)
                
                image_url = image_url_input
                
                # Validate URL format
                if not image_url.startswith(('http://', 'https://')):
                    flash('Please provide a valid image URL starting with http:// or https://', 'danger')
                    users = User.query.filter_by(is_active=True).order_by(User.username).all()
                    return render_template('admin_create_advert.html', users=users)
            
            # Get weeks (default 1)
            weeks = request.form.get('weeks', type=int) or 1
            if weeks < 1:
                weeks = 1
            elif weeks > 52:
                weeks = 52
            
            try:
                # Create advert (free, automatically approved and active)
                advert = Advert(
                    title=title,
                    description=description if description else None,
                    image_url=image_url,
                    link_url=link_url if link_url else None,
                    button_text=button_text if button_text else 'Learn More',
                    submitted_by=user_id,
                    amount=0.00,  # Free for admin-created adverts
                    weeks=weeks,
                    status='active',  # Automatically approved and active
                    payment_status='paid',  # Free = paid
                    approved_at=datetime.utcnow(),
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(weeks=weeks),
                    admin_notes='Created by admin (free)'
                )
                
                db.session.add(advert)
                db.session.commit()
                
                # Log activity
                try:
                    activity = UserActivity(
                        user_id=user_id,
                        action='advert_created_by_admin',
                        description=f'Admin created advert: {title}'
                    )
                    db.session.add(activity)
                    db.session.commit()
                except Exception as e:
                    print(f"Error logging activity: {e}")
                
                flash(f'Advert "{title}" created successfully and approved (free)!', 'success')
                return redirect(url_for('admin_adverts'))
            except Exception as e:
                print(f"Error creating advert: {e}")
                import traceback
                traceback.print_exc()  # Print full traceback for debugging
                db.session.rollback()
                flash('Error creating advert. Please try again.', 'danger')
                # Return form with error instead of redirecting
                try:
                    users = User.query.filter_by(is_active=True).order_by(User.username).all()
                    return render_template('admin_create_advert.html', users=users)
                except Exception as render_error:
                    print(f"Error rendering form after error: {render_error}")
                    import traceback
                    traceback.print_exc()
                    return redirect(url_for('admin_adverts'))
        except Exception as e:
            # Catch any unhandled exceptions in POST handler
            error_msg = str(e)
            print(f"Unhandled exception in POST handler: {error_msg}")
            print(f"Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            
            # Provide more specific error message
            if 'weeks' in error_msg.lower() or 'start_date' in error_msg.lower() or 'end_date' in error_msg.lower():
                flash(f'Database error: {error_msg}. Please ensure the database schema is up to date.', 'danger')
            elif 'image' in error_msg.lower() or 'file' in error_msg.lower():
                flash(f'File upload error: {error_msg}. Please try using an image URL instead.', 'danger')
            else:
                flash(f'An unexpected error occurred: {error_msg}. Please try again.', 'danger')
            
            try:
                users = User.query.filter_by(is_active=True).order_by(User.username).all()
                return render_template('admin_create_advert.html', users=users)
            except Exception as render_err:
                print(f"Error rendering form after error: {render_err}")
                traceback.print_exc()
                return redirect(url_for('admin_adverts'))
    
    # GET request - show form
    if not db_connected:
        flash('Database not available. Please try again later.', 'danger')
        return redirect(url_for('admin_adverts'))
    
    try:
        users = User.query.filter_by(is_active=True).order_by(User.username).all()
        return render_template('admin_create_advert.html', users=users)
    except Exception as e:
        print(f"Error loading create advert form: {e}")
        flash('Error loading the form. Please try again.', 'danger')
        return redirect(url_for('admin_adverts'))

@app.route('/admin/post/create', methods=['GET', 'POST'])
@admin_required
def admin_create_post():
    """Admin - Create blog post (assigned to admin name as blogger)"""
    # Get or create admin user account for blog posts
    admin_username = current_user.username if hasattr(current_user, 'username') else 'admin'
    admin_email = current_user.email if hasattr(current_user, 'email') else 'admin@teacherstribe.com'
    
    # Try to find existing admin user account
    admin_user = User.query.filter_by(username=admin_username).first()
    
    # If not found, create one for blog posts
    if not admin_user:
        try:
            admin_user = User(
                username=admin_username,
                email=admin_email,
                full_name=f'{admin_username.title()} (Admin Blogger)',
                is_active=True,
                email_verified=True
            )
            # Set a dummy password (won't be used for login since admin logs in via Admin model)
            admin_user.set_password('dummy_password_not_used')
            db.session.add(admin_user)
            db.session.commit()
        except Exception as e:
            print(f"Error creating admin user account: {e}")
            # If username exists, try with admin prefix
            admin_username = f'admin_blogger'
            admin_user = User.query.filter_by(username=admin_username).first()
            if not admin_user:
                admin_user = User(
                    username=admin_username,
                    email='admin@teacherstribe.com',
                    full_name='Admin Blogger',
                    is_active=True,
                    email_verified=True
                )
                admin_user.set_password('dummy_password_not_used')
                db.session.add(admin_user)
                db.session.commit()
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        image_url = request.form.get('image_url', '').strip()
        
        # Validation
        if not title or not content:
            flash('Please provide both title and content.', 'danger')
            return render_template('admin_create_post.html', admin_name=admin_user.full_name or admin_user.username)
        
        if len(title) > 500:
            flash('Title is too long. Maximum 500 characters.', 'danger')
            return render_template('admin_create_post.html', admin_name=admin_user.full_name or admin_user.username)
        
        try:
            # Handle image upload
            final_image_url = None
            
            # Check if image file was uploaded
            if 'image_file' in request.files:
                image_file = request.files['image_file']
                if image_file and image_file.filename:
                    # Validate file type
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = secure_filename(image_file.filename)
                    if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        # Upload to ImageKit
                        final_image_url = upload_image_to_imagekit(image_file, folder_name='posts')
                        if not final_image_url:
                            flash('Failed to upload image. Please try again or use an image URL.', 'warning')
            
            # If no file upload, use URL if provided
            if not final_image_url and image_url:
                final_image_url = image_url
            
            # Create blog post assigned to admin user
            post = BlogPost(
                title=title,
                content=content,
                image_url=final_image_url,
                author_id=admin_user.id
            )
            db.session.add(post)
            db.session.commit()
            
            # Log activity
            try:
                activity = UserActivity(
                    user_id=admin_user.id,
                    action='post_created_by_admin',
                    description=f'Admin created blog post: {title[:50]}'
                )
                db.session.add(activity)
                db.session.commit()
            except Exception as e:
                print(f"Error logging activity: {e}")
            
            flash(f'Blog post "{title}" created successfully as {admin_user.full_name or admin_user.username}!', 'success')
            return redirect(url_for('post_detail', post_id=post.id))
        
        except Exception as e:
            print(f"Error creating blog post: {e}")
            db.session.rollback()
            flash('An error occurred while creating the post. Please try again.', 'danger')
    
    # GET request - show form
    admin_name = admin_user.full_name or admin_user.username
    return render_template('admin_create_post.html', admin_name=admin_name)

@app.route('/admin/advert/pricing', methods=['GET', 'POST'])
@admin_required
def admin_advert_pricing():
    """Admin - Set advert pricing"""
    pricing = AdvertPricing.query.first()
    
    if request.method == 'POST':
        amount = request.form.get('amount')
        
        try:
            amount_float = float(amount) if amount else 0.00
            
            # Validate amount is non-negative
            if amount_float < 0:
                flash('Amount cannot be negative. Please enter a valid positive number or zero.', 'danger')
                return redirect(url_for('admin_advert_pricing'))
            
            # Update or create pricing record
            if pricing:
                pricing.amount = amount_float
                pricing.updated_at = datetime.utcnow()
            else:
                pricing = AdvertPricing(amount=amount_float)
                db.session.add(pricing)
            
            db.session.commit()
            flash(f'Advert pricing updated to ₦{amount_float:,.2f} per week', 'success')
        except ValueError:
            flash('Invalid amount. Please enter a valid number.', 'danger')
        except Exception as e:
            print(f"Error updating pricing: {e}")
            db.session.rollback()
            flash('Error updating pricing. Please try again.', 'danger')
        
        return redirect(url_for('admin_advert_pricing'))
    
    current_amount = float(pricing.amount) if pricing else 0.00
    return render_template('admin_advert_pricing.html', current_amount=current_amount)

@app.route('/advert/<int:advert_id>/pay', methods=['GET', 'POST'])
@login_required
def pay_advert(advert_id):
    """Pay for advert using Paystack - auto-initiates payment"""
    advert = Advert.query.get_or_404(advert_id)
    
    # Verify user owns the advert
    if advert.submitted_by != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('my_adverts'))
    
    # Check if already paid
    if advert.payment_status == 'paid':
        flash('This advert has already been paid for.', 'info')
        return redirect(url_for('my_adverts'))
    
    # Auto-initiate Paystack payment (both GET and POST)
    # Initialize Paystack payment
    amount_in_kobo = int(float(advert.amount) * 100)  # Convert to kobo (Paystack currency)
    email = current_user.email
    reference = f"ADV_{advert.id}_{int(datetime.utcnow().timestamp())}"
    
    # Create Paystack payment initialization
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'amount': amount_in_kobo,
        'email': email,
        'reference': reference,
        'callback_url': f"{APP_URL}/advert/{advert_id}/payment-callback",
        'metadata': {
            'advert_id': advert.id,
            'user_id': current_user.id
        }
    }
    
    try:
        response = requests.post('https://api.paystack.co/transaction/initialize', 
                                json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status'):
                authorization_url = data['data']['authorization_url']
                # Store reference in session
                session['payment_reference'] = reference
                return redirect(authorization_url)
            else:
                flash('Payment initialization failed. Please try again.', 'danger')
        else:
            flash('Error initializing payment. Please try again.', 'danger')
    except Exception as e:
        print(f"Paystack error: {e}")
        flash('Payment service unavailable. Please try again later.', 'danger')
    
    # If payment initialization failed, show fallback page
    return render_template('pay_advert.html', advert=advert, paystack_public_key=PAYSTACK_PUBLIC_KEY)

@app.route('/advert/<int:advert_id>/payment-callback')
@login_required
def payment_callback(advert_id):
    """Handle Paystack payment callback"""
    advert = Advert.query.get_or_404(advert_id)
    reference = request.args.get('reference')
    
    if not reference:
        flash('Payment reference not found.', 'danger')
        return redirect(url_for('my_adverts'))
    
    # Verify payment with Paystack
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}',
                                headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') and data['data']['status'] == 'success':
                # Payment successful - Auto-approve and activate advert
                advert.payment_status = 'paid'
                advert.status = 'active'  # Auto-approve and activate
                advert.approved_at = datetime.utcnow()
                
                # Set start and end dates based on weeks
                advert.start_date = datetime.utcnow()
                advert.end_date = datetime.utcnow() + timedelta(weeks=advert.weeks)
                
                db.session.commit()
                
                # Send payment confirmation email
                try:
                    send_payment_confirmation_email(current_user, advert)
                except Exception as e:
                    print(f"Error sending payment confirmation email: {e}")
                
                flash(f'Payment successful! Your advert is now active and will run for {advert.weeks} week(s) until {advert.end_date.strftime("%B %d, %Y")}.', 'success')
                
                # Log activity (admins don't use this route)
                is_admin = current_user.__class__.__name__ == 'Admin'
                if not is_admin:
                    activity = UserActivity(
                        user_id=current_user.id,
                        action='advert_payment',
                        description=f'Payment received and advert activated for {advert.weeks} week(s): {advert.title}'
                    )
                    db.session.add(activity)
                    db.session.commit()
            else:
                flash('Payment verification failed. Please contact support.', 'danger')
        else:
            flash('Could not verify payment. Please contact support.', 'danger')
    except Exception as e:
        print(f"Payment verification error: {e}")
        flash('Payment verification error. Please contact support.', 'danger')
    
    return redirect(url_for('my_adverts'))

@app.route('/donate', methods=['GET', 'POST'])
def donate():
    """Donation page with Paystack integration"""
    # Initialize Paystack payment for donation
    if request.method == 'POST':
        # Get donation amount from form
        amount = request.form.get('amount', '').strip()
        custom_amount = request.form.get('custom_amount', '').strip()
        
        # Validate amount
        if custom_amount:
            try:
                amount_float = float(custom_amount)
                if amount_float < 100:  # Minimum 100 naira (1 naira in kobo)
                    flash('Minimum donation amount is ₦100.', 'danger')
                    return render_template('donate.html')
                amount_in_kobo = int(amount_float * 100)
            except ValueError:
                flash('Invalid donation amount.', 'danger')
                return render_template('donate.html')
        elif amount:
            try:
                amount_float = float(amount)
                if amount_float < 100:
                    flash('Minimum donation amount is ₦100.', 'danger')
                    return render_template('donate.html')
                amount_in_kobo = int(amount_float * 100)
            except ValueError:
                flash('Invalid donation amount.', 'danger')
                return render_template('donate.html')
        else:
            flash('Please select or enter a donation amount.', 'danger')
            return render_template('donate.html')
        
        # Get user email if authenticated, otherwise use a placeholder
        if current_user.is_authenticated:
            email = current_user.email
            user_id = current_user.id
        else:
            # For non-authenticated users, require email
            email = request.form.get('donor_email', '').strip()
            if not email or '@' not in email:
                flash('Please provide a valid email address.', 'danger')
                return render_template('donate.html')
            user_id = None
        
        # Create reference
        reference = f"DON_{int(datetime.utcnow().timestamp())}"
        
        # Initialize Paystack payment
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'amount': amount_in_kobo,
            'email': email,
            'reference': reference,
            'callback_url': f"{APP_URL}/donate/callback?amount={amount_float:.2f}",
            'metadata': {
                'user_id': user_id,
                'donation_type': 'platform_support'
            }
        }
        
        try:
            response = requests.post('https://api.paystack.co/transaction/initialize', 
                                    json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    authorization_url = data['data']['authorization_url']
                    session['donation_reference'] = reference
                    session['donation_amount'] = amount_float
                    return redirect(authorization_url)
                else:
                    flash('Payment initialization failed. Please try again.', 'danger')
            else:
                flash('Error initializing payment. Please try again.', 'danger')
        except Exception as e:
            print(f"Paystack error: {e}")
            flash('Payment service unavailable. Please try again later.', 'danger')
    
    return render_template('donate.html', paystack_public_key=PAYSTACK_PUBLIC_KEY)

@app.route('/donate/callback')
def donation_callback():
    """Handle donation payment callback"""
    reference = request.args.get('reference')
    amount = request.args.get('amount')
    
    if not reference:
        flash('Payment reference not found.', 'danger')
        return redirect(url_for('donate'))
    
    # Verify payment with Paystack
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}',
                                headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') and data['data']['status'] == 'success':
                # Payment successful
                flash(f'Thank you for your donation of ₦{float(amount):,.2f}! Your support helps us grow and innovate. 🙏', 'success')
                
                # Log activity if user is authenticated and is a regular user (not admin)
                if db_connected and current_user.is_authenticated:
                    is_admin = current_user.__class__.__name__ == 'Admin'
                    if not is_admin:
                        try:
                            activity = UserActivity(
                                user_id=current_user.id,
                                action='donation',
                                description=f'Donated ₦{float(amount):,.2f} to support platform growth'
                            )
                            db.session.add(activity)
                            db.session.commit()
                        except Exception as e:
                            print(f"Error logging donation activity: {e}")
            else:
                flash('Payment verification failed. Please contact support.', 'danger')
        else:
            flash('Could not verify payment. Please contact support.', 'danger')
    except Exception as e:
        print(f"Payment verification error: {e}")
        flash('Payment verification error. Please contact support.', 'danger')
    
    return redirect(url_for('index'))

# SocketIO events for real-time features
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('status', {'msg': "Connected to Educators' Tribe"})

@socketio.on('join')
def handle_join(data):
    """Handle room join"""
    room = data.get('room', 'general')
    join_room(room)
    emit('status', {'msg': f'Joined room: {room}'}, room=room)

# Initialize database and create admin user
def init_db():
    """Create database tables and default admin"""
    if not db_connected:
        print("⚠ Skipping database initialization - PostgreSQL not connected")
        return
    
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            print("✓ Database tables created")
            
            # Migrate: Add image_url column to blog_posts if it doesn't exist
            try:
                # Check if column exists
                with db.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name='blog_posts' AND column_name='image_url'
                    """))
                    column_exists = result.fetchone() is not None
                    
                    if not column_exists:
                        print("⚠ Migrating blog_posts table: adding image_url column...")
                        conn.execute(text("ALTER TABLE blog_posts ADD COLUMN image_url VARCHAR(1000)"))
                        conn.commit()
                        print("✓ Migration complete: image_url column added to blog_posts")
                    else:
                        print("✓ image_url column already exists in blog_posts")
            except Exception as e:
                print(f"⚠ Migration check failed (this is OK if column already exists): {e}")
            
            # Migrate: Add profile_picture column to users if it doesn't exist
            try:
                # Check if column exists
                with db.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name='users' AND column_name='profile_picture'
                    """))
                    column_exists = result.fetchone() is not None
                    
                    if not column_exists:
                        print("⚠ Migrating users table: adding profile_picture column...")
                        conn.execute(text("ALTER TABLE users ADD COLUMN profile_picture VARCHAR(1000)"))
                        conn.commit()
                        print("✓ Migration complete: profile_picture column added to users")
                    else:
                        print("✓ profile_picture column already exists in users")
            except Exception as e:
                print(f"⚠ Migration check failed (this is OK if column already exists): {e}")
            
            # Migrate: Add weeks, start_date, and end_date columns to adverts table if they don't exist
            try:
                with db.engine.connect() as conn:
                    # Check which columns exist
                    result = conn.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name='adverts' AND column_name IN ('weeks', 'start_date', 'end_date')
                    """))
                    existing_columns = [row[0] for row in result]
                    
                    # Add weeks column if it doesn't exist
                    if 'weeks' not in existing_columns:
                        print("⚠ Migrating adverts table: adding weeks column...")
                        conn.execute(text("ALTER TABLE adverts ADD COLUMN weeks INTEGER NOT NULL DEFAULT 1"))
                        conn.commit()
                        print("✓ Migration complete: weeks column added to adverts")
                    else:
                        print("✓ weeks column already exists in adverts")
                    
                    # Add start_date column if it doesn't exist
                    if 'start_date' not in existing_columns:
                        print("⚠ Migrating adverts table: adding start_date column...")
                        conn.execute(text("ALTER TABLE adverts ADD COLUMN start_date TIMESTAMP"))
                        conn.commit()
                        print("✓ Migration complete: start_date column added to adverts")
                    else:
                        print("✓ start_date column already exists in adverts")
                    
                    # Add end_date column if it doesn't exist
                    if 'end_date' not in existing_columns:
                        print("⚠ Migrating adverts table: adding end_date column...")
                        conn.execute(text("ALTER TABLE adverts ADD COLUMN end_date TIMESTAMP"))
                        conn.commit()
                        print("✓ Migration complete: end_date column added to adverts")
                    else:
                        print("✓ end_date column already exists in adverts")
            except Exception as e:
                print(f"⚠ Error during adverts migration: {e}")
            
            # Create default admin if doesn't exist
            admin = Admin.query.filter_by(username='admin').first()
            if not admin:
                admin = Admin(
                    username='admin',
                    email='admin@teacherstribe.com'
                )
                admin.set_password('admin123')  # Change this in production!
                db.session.add(admin)
                db.session.commit()
                print("=" * 60)
                print("ADMIN CREDENTIALS CREATED:")
                print("Username: admin")
                print("Password: admin123")
                print("=" * 60)
            
            # Create default advert pricing
            pricing = AdvertPricing.query.first()
            if not pricing:
                pricing = AdvertPricing(amount=500.00)  # Default 500 naira per week
                db.session.add(pricing)
                db.session.commit()
                print("✓ Default advert pricing created: ₦500.00 per week (Admin can update this)")
            else:
                print(f"✓ Advert pricing: ₦{float(pricing.amount):,.2f} per week")
            
            # Migrate: Add email_verified column to users if it doesn't exist
            try:
                with db.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name='users' AND column_name='email_verified'
                    """))
                    column_exists = result.fetchone() is not None
                    
                    if not column_exists:
                        print("⚠ Migrating users table: adding email_verified column...")
                        conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE NOT NULL"))
                        conn.commit()
                        print("✓ Migration complete: email_verified column added to users")
                    else:
                        print("✓ email_verified column already exists in users")
            except Exception as e:
                print(f"⚠ Migration check failed (this is OK if column already exists): {e}")
            
            # Create demo users
            demo_users = [
                {'username': 'teacher_john', 'email': 'john.teacher@example.com', 'full_name': 'John Teacher', 'password': 'demo123'},
                {'username': 'educator_mary', 'email': 'mary.educator@example.com', 'full_name': 'Mary Educator', 'password': 'demo123'},
                {'username': 'professor_david', 'email': 'david.prof@example.com', 'full_name': 'Professor David', 'password': 'demo123'},
            ]
            
            for user_data in demo_users:
                existing_user = User.query.filter_by(username=user_data['username']).first()
                if not existing_user:
                    user = User(
                        username=user_data['username'],
                        email=user_data['email'],
                        full_name=user_data['full_name'],
                        is_active=True
                    )
                    user.set_password(user_data['password'])
                    db.session.add(user)
                    db.session.commit()
                    print(f"Demo user created: {user_data['username']} / {user_data['password']}")
            
            print("\n" + "=" * 60)
            print("DEMO CREDENTIALS:")
            print("-" * 60)
            print("ADMIN:")
            print("  Username: admin")
            print("  Password: admin123")
            print("\nDEMO USERS:")
            for user_data in demo_users:
                print(f"  Username: {user_data['username']}")
                print(f"  Password: {user_data['password']}")
                print(f"  Name: {user_data['full_name']}")
                print(f"  Email: {user_data['email']}")
                print()
            print("=" * 60)
            
            # Initial news fetch
            try:
                with app.app_context():
                    fetch_education_news()
            except Exception as e:
                print(f"⚠ Error fetching initial news: {e}")
        
    except Exception as e:
        print(f"⚠ Error initializing database: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start news fetcher thread (only if PostgreSQL is connected)
    if db_connected:
        thread = threading.Thread(target=news_fetcher_thread, daemon=True)
        thread.start()
    else:
        print("⚠ Application starting without database connection")
        print("⚠ Some features may not work properly until PostgreSQL is connected")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
