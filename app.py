import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import json
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

# Modified user loader for our upcoming NoSQL user records
@login_manager.user_loader
def load_user(user_id):
    # We will define a lightweight session User class in the next phase to bridge Flask-Login
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
        username = request.form.get('username').strip().lower()
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        
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
        login_input = request.form.get('login_input').strip().lower()
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
            # Decoupled string storage via the secure browser cookie flask session dict
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
    log = AuditLog(user_id=current_user.id, action="user_logged_out", ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()
    logout_user()
    return redirect(url_for('landing'))

# ==========================================
# DASHBOARD & ASYNC DATA ENDPOINTS
# ==========================================

@app.route('/dashboard')
@login_required
def dashboard():
    firebase_token = session.get('firebase_token', '')
    
    # Gather configuration fields from environment variables safely
    firebase_config = {
        "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        "databaseURL": os.environ.get("FIREBASE_DATABASE_URL", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", "")
    }
    
    return render_template('dashboard.html', 
                           firebase_token=firebase_token,
                           firebase_config=firebase_config,
                           user_id=current_user.id,
                           username=current_user.username)


@app.route('/api/messages/<int:chat_id>')
@login_required
def get_chat_messages(chat_id):
    # This HTTP route now purely handles fetching database history
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.created_at.asc()).all()
    output = []
    for m in messages:
        sender_name = m.sender.username if m.sender else "System"
        reactions_data = {}
        for r in m.reactions.all():
            reactions_data[r.emoji] = reactions_data.get(r.emoji, 0) + 1
            
        output.append({
            'id': m.id,
            'chat_id': m.chat_id,
            'user_id': m.user_id,
            'username': sender_name,
            'content': m.content,
            'message_type': m.message_type,
            'file_url': m.file_url,
            'file_name': m.file_name,
            'file_size': m.file_size,
            'status': m.status,
            'time': m.created_at.strftime('%I:%M %p'),
            'reactions': reactions_data
        })
    return jsonify(output)
@app.route('/api/create-room', methods=['POST'])
@login_required
def create_room():
    data = request.get_json()
    room_name = data.get('name', '').strip()
    room_desc = data.get('desc', '').strip()
    
    if not room_name:
        return jsonify({'error': 'Room name cannot be empty'}), 400
        
    if not room_name.startswith('# '):
        room_name = f"# {room_name}"
        
    new_chat = Chat(name=room_name, is_group=True, group_description=room_desc)
    db.session.add(new_chat)
    db.session.commit()
    
    return jsonify({'id': new_chat.id, 'name': new_chat.name, 'desc': new_chat.group_description})

# ==========================================
# FILE SHARING ENDPOINT
# ==========================================

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files or 'chat_id' not in request.form:
        return jsonify({'error': 'Missing upload variables'}), 400
        
    file = request.files['file']
    chat_id = request.form.get('chat_id')
    
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
        
    filename = secure_filename(file.filename)
    unique_filename = f"{int(datetime.utcnow().timestamp())}_{filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(file_path)
    
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    msg_type = 'file'
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
        msg_type = 'image'
    elif ext in ['mp4', 'webm', 'ogg']:
        msg_type = 'video'
    elif ext in ['mp3', 'wav']:
        msg_type = 'audio'
        
    file_url = f"/static/uploads/{unique_filename}"
    file_size_bytes = os.path.getsize(file_path)
    
    new_msg = Message(
        chat_id=int(chat_id),
        user_id=current_user.id,
        content=f"Sent a file: {filename}",
        message_type=msg_type,
        file_url=file_url,
        file_name=filename,
        file_size=file_size_bytes,
        status='sent'
    )
    db.session.add(new_msg)
    db.session.commit()
    
    socket_payload = {
        'id': new_msg.id,
        'chat_id': new_msg.chat_id,
        'user_id': current_user.id,
        'username': current_user.username,
        'content': new_msg.content,
        'message_type': msg_type,
        'file_url': file_url,
        'file_name': filename,
        'file_size': file_size_bytes,
        'status': 'sent',
        'time': new_msg.created_at.strftime('%I:%M %p'),
        'reactions': {}
    }
    socketio.emit('chat_msg_broadcast', socket_payload, room=str(chat_id))
    
    return jsonify(socket_payload)

# ==========================================
# REACTION SYSTEM ENDPOINT
# ==========================================

@app.route('/api/react', methods=['POST'])
@login_required
def add_reaction():
    data = request.get_json()
    message_id = data.get('message_id')
    emoji = data.get('emoji')
    chat_id = data.get('chat_id')
    
    if not message_id or not emoji or not chat_id:
        return jsonify({'error': 'Missing parameters'}), 400
        
    existing = MessageReaction.query.filter_by(message_id=message_id, user_id=current_user.id, emoji=emoji).first()
    
    if existing:
        db.session.delete(existing)
        action = "removed"
    else:
        new_react = MessageReaction(message_id=message_id, user_id=current_user.id, emoji=emoji)
        db.session.add(new_react)
        action = "added"
        
    db.session.commit()
    
    totals = {}
    for r in MessageReaction.query.filter_by(message_id=message_id).all():
        totals[r.emoji] = totals.get(r.emoji, 0) + 1
        
    payload = {
        'message_id': message_id,
        'reactions': totals
    }
    socketio.emit('reaction_update', payload, room=str(chat_id))
    return jsonify({'status': 'success', 'action': action, 'totals': totals})

# ==========================================
# PRIVATE 1-TO-1 DIRECT MESSAGING (DM) GATEWAY
# ==========================================

@app.route('/api/dm/<int:recipient_id>')
@login_required
def get_or_create_dm(recipient_id):
    recipient = User.query.get_or_404(recipient_id)
    my_dms = Chat.query.filter_by(is_group=False).join(Chat.participants).filter(User.id == current_user.id).all()
    
    dm_chat = None
    for chat in my_dms:
        if recipient in chat.participants:
            dm_chat = chat
            break
            
    if not dm_chat:
        dm_chat = Chat(is_group=False, name=None)
        dm_chat.participants.append(current_user)
        dm_chat.participants.append(recipient)
        db.session.add(dm_chat)
        db.session.commit()
        
    return jsonify({
        'id': dm_chat.id,
        'name': recipient.username,
        'desc': recipient.profile.bio or 'Secure 1-to-1 transmission line active.'
    })

# ==========================================
# ADMIN PORTAL ROUTING
# ==========================================

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return "Access metrics missing.", 403
    users = User.query.all()
    messages = Message.query.all()
    reports = Report.query.all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(50).all()
    return render_template('admin.html', users=users, recent_messages=messages, reports=reports, audit_logs=audit_logs, total_messages=len(messages))

@app.route('/admin/ban-user/<int:user_id>', methods=['POST'])
@login_required
def ban_user(user_id):
    if not current_user.is_admin:
        return "Unauthorized action.", 403
    user = User.query.get(user_id)
    if user and not user.is_admin:
        user.is_banned = True
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete-message/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    if not current_user.is_admin:
        return "Unauthorized action.", 403
    msg = Message.query.get(message_id)
    if msg:
        db.session.delete(msg)
        db.session.commit()
    return redirect(url_for('admin_panel'))

# ==========================================
# SOCKET NETWORKING SERVICE (SCOPED ROOMS)
# ==========================================

@socketio.on('join')
def on_join(data):
    if current_user.is_authenticated:
        room = str(data['room_id'])
        join_room(room)

@socketio.on('leave')
def on_leave(data):
    if current_user.is_authenticated:
        room = str(data['room_id'])
        leave_room(room)

@socketio.on('new_chat_msg')
def handle_incoming_socket_message(data):
    if current_user.is_authenticated:
        content = data.get('message', '').strip()
        room_id = data.get('room_id')
        if content and room_id:
            new_msg = Message(content=content, user_id=current_user.id, chat_id=int(room_id), status='sent')
            db.session.add(new_msg)
            db.session.commit()
            
            emit('chat_msg_broadcast', {
                'id': new_msg.id,
                'chat_id': new_msg.chat_id,
                'user_id': current_user.id,
                'username': current_user.username,
                'content': content,
                'message_type': 'text',
                'status': 'sent',
                'time': new_msg.created_at.strftime('%I:%M %p'),
                'reactions': {}
            }, room=str(room_id))

# ==========================================
# MESSAGE TICK STATUS SOCKET EVENTS
# ==========================================

@socketio.on('opened_room')
def handle_opened_room(data):
    # Triggers sequentially after join_room has established the socket handshake
    if current_user.is_authenticated:
        room_id = data.get('room_id')
        if room_id:
            unread_messages = Message.query.filter_by(chat_id=int(room_id)).filter(Message.user_id != current_user.id).filter(Message.status != 'read').all()
            if unread_messages:
                for m in unread_messages:
                    m.status = 'read'
                db.session.commit()
                # Broadcast global read acknowledgment to the room
                socketio.emit('chat_marked_read', {'chat_id': int(room_id)}, room=str(room_id))

@socketio.on('message_delivered_ack')
def handle_delivery_ack(data):
    msg_id = data.get('message_id')
    chat_id = data.get('chat_id')
    msg = Message.query.get(msg_id)
    if msg and msg.status == 'sent':
        msg.status = 'delivered'
        db.session.commit()
        # Broadcast via global socketio context
        socketio.emit('message_status_update', {'message_id': msg_id, 'status': 'delivered'}, room=str(chat_id))

@socketio.on('message_seen_ack')
def handle_seen_ack(data):
    msg_id = data.get('message_id')
    chat_id = data.get('chat_id')
    msg = Message.query.get(msg_id)
    if msg and msg.status in ['sent', 'delivered']:
        msg.status = 'read'
        db.session.commit()
        # Broadcast via global socketio context
        socketio.emit('message_status_update', {'message_id': msg_id, 'status': 'read'}, room=str(chat_id))

        
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)