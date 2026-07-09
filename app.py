import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

import firebase_admin
from firebase_admin import credentials, auth, db as firebase_db

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'convo-cave-enterprise-encryption-secret')

# Initialize Firebase Admin SDK using Environment Variables for Vercel Serverless Safety
firebase_creds_dict = {
    "type": "service_account",
    "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
    "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.environ.get("FIREBASE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ.get("FIREBASE_CLIENT_CERT_URL")
}

# The Realtime Database URL will be provided by your Firebase dashboard project overview
DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL", "https://YOUR-PROJECT-ID-DEFAULT.firebaseio.com/")

if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_creds_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL
    })

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Modified user loader for NoSQL user records referencing auth_helper
@login_manager.user_loader
def load_user(user_id):
    from auth_helper import get_session_user
    return get_session_user(user_id)


# ==========================================
# AUTHENTICATION ROUTING
# ==========================================

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        
        if not username or not email or not password:
            flash('All credential metrics are required.')
            return redirect(url_for('signup'))

        # NoSQL Query: Check if the username parameter already exists under our /users tree
        users_ref = firebase_db.reference('users')
        existing_users = users_ref.order_by_child('username').equal_to(username).get()
        if existing_users:
            flash('Username parameter already registered.')
            return redirect(url_for('signup'))
            
        # Check if email is already taken
        existing_emails = users_ref.order_by_child('email').equal_to(email).get()
        if existing_emails:
            flash('Email parameter already registered.')
            return redirect(url_for('signup'))
            
        hashed_password = generate_password_hash(password, method='scrypt')
        
        # Fetch current user snapshot count to determine the first master administrator
        all_users = users_ref.get()
        is_first = True if not all_users else False
        
        # Create a new unique node ID inside the Firebase JSON tree
        new_user_ref = users_ref.push()
        user_id = new_user_ref.key
        
        # Construct our decoupled user schema data profile
        user_payload = {
            "username": username,
            "email": email,
            "password_hash": hashed_password,
            "is_admin": is_first,
            "is_suspended": False,
            "is_banned": False,
            "created_at": int(datetime.utcnow().timestamp() * 1000)
        }
        
        # Write directly to the database via NoSQL document push
        new_user_ref.set(user_payload)
        
        flash('Account verified. Proceed to log in.')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Safely try getting 'login_input', falling back to 'username' or 'email' fields from HTML form
        raw_input = request.form.get('login_input') or request.form.get('username') or request.form.get('email') or ""
        login_input = raw_input.strip().lower()
        
        if not login_input:
            flash('Please enter your username or email address.')
            return redirect(url_for('login'))
            
        password = request.form.get('password')
        
        users_ref = firebase_db.reference('users')
        
        # Search NoSQL snapshot references matching either username or email input fields
        user_record = None
        user_id = None
        
        by_username = users_ref.order_by_child('username').equal_to(login_input).get()
        if by_username:
            user_id = list(by_username.keys())[0]
            user_record = by_username[user_id]
        else:
            by_email = users_ref.order_by_child('email').equal_to(login_input).get()
            if by_email:
                user_id = list(by_email.keys())[0]
                user_record = by_email[user_id]
                
        if not user_record or not check_password_hash(user_record.get('password_hash', ''), password):
            flash('Invalid login authentication vectors.')
            return redirect(url_for('login'))
            
        if user_record.get('is_banned', False):
            flash('Access terminated. Account banned by administration.')
            return redirect(url_for('login'))
            
        # Initialize our lightweight SessionUser instance to bind with Flask-Login
        from auth_helper import SessionUser
        session_user = SessionUser(user_id, user_record)
        login_user(session_user)
        
        # Mint our secure, serverless Firebase Custom Token for direct browser socket syncing!
        try:
            custom_token = auth.create_custom_token(user_id)
            session['firebase_token'] = custom_token.decode('utf-8') if isinstance(custom_token, bytes) else custom_token
        except Exception as e:
            print(f"Token generation breakdown: {e}")
            flash('Token engine error. Please retry initialization.')
            return redirect(url_for('login'))
            
        return redirect(url_for('dashboard'))
        
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('firebase_token', None)
    return redirect(url_for('landing'))

# ==========================================
# DASHBOARD LAYOUT & CONFIGURATION ROUTING
# ==========================================

@app.route('/dashboard')
@login_required
def dashboard():
    firebase_token = session.get('firebase_token', '')
    
    # Gather configuration fields from environment variables safely for the client side
    firebase_config = {
        "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        "databaseURL": os.environ.get("FIREBASE_DATABASE_URL", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", "")
    }
    
    # Create a dummy default_room object to keep dashboard.html from throwing an UndefinedError
    default_room_fallback = {
        "id": "general",
        "name": "# general"
    }
    
    return render_template('dashboard.html', 
                           firebase_token=firebase_token,
                           firebase_config=firebase_config,
                           user_id=current_user.id,
                           username=current_user.username,
                           default_room=default_room_fallback)

# ==========================================
# ADMINISTRATIVE CONTROL ROUTING (ADMIN PANEL)
# ==========================================

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    # Security Guard: Check if current node session has admin privileges
    if not getattr(current_user, 'is_admin', False):
        flash('Access Denied: Master Administration credentials required.')
        return redirect(url_for('dashboard'))

    users_ref = firebase_db.reference('users')
    rooms_ref = firebase_db.reference('rooms')

    # Handle Admin Actions (Post Requests like Ban, Unban, Delete Room)
    if request.method == 'POST':
        action = request.form.get('action')
        target_id = request.form.get('target_id')

        if action == 'ban_user' and target_id:
            users_ref.child(target_id).update({"is_banned": True})
            flash(f'User Node [{target_id[:8]}] successfully suspended.')
        
        elif action == 'unban_user' and target_id:
            users_ref.child(target_id).update({"is_banned": False})
            flash(f'User Node [{target_id[:8]}] operational clearance restored.')

        elif action == 'delete_room' and target_id:
            # Delete room configuration and its message cluster tree node
            rooms_ref.child(target_id).delete()
            firebase_db.reference(f'messages/{target_id}').delete()
            flash(f'Communication Room [{target_id}] permanently purged.')

        return redirect(url_for('admin_panel'))

    # Fetch fresh real-time NoSQL snapshots for the admin layout view
    all_users = users_ref.get() or {}
    all_rooms = rooms_ref.get() or {}

    return render_template('admin.html', 
                           users=all_users, 
                           rooms=all_rooms, 
                           username=current_user.username)
    

# Serverless WSGI engine entry point fallback configuration
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
