from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# Association table for User-to-Chat participants (Handles DMs, Groups, and Channels)
chat_participants = db.Table('chat_participants',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('chat_id', db.Integer, db.ForeignKey('chats.id', ondelete='CASCADE'), primary_key=True),
    db.Column('joined_at', db.DateTime, default=datetime.utcnow)
)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    # Core Relationships
    profile = db.relationship('Profile', backref='user', uselist=False, cascade='all, delete-orphan')
    chats = db.relationship('Chat', secondary=chat_participants, back_populates='participants')
    messages = db.relationship('Message', backref='sender', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')
    settings = db.relationship('UserSetting', backref='user', uselist=False, cascade='all, delete-orphan')

class Profile(db.Model):
    __tablename__ = 'profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    avatar_url = db.Column(db.String(256), default='/static/avatars/default.png')
    banner_url = db.Column(db.String(256))
    bio = db.Column(db.Text)
    country = db.Column(db.String(100))
    language = db.Column(db.String(10), default='en')
    timezone = db.Column(db.String(50), default='UTC')
    online_status = db.Column(db.String(20), default='offline')  # online, offline, idle, dnd
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

class UserSetting(db.Model):
    __tablename__ = 'user_settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    dark_mode = db.Column(db.Boolean, default=True)
    chat_wallpaper = db.Column(db.String(100))
    font_size = db.Column(db.Integer, default=14)
    accent_color = db.Column(db.String(20), default='#9d4edd')

    # Privacy configurations
    hide_last_seen = db.Column(db.Boolean, default=False)
    hide_online_status = db.Column(db.Boolean, default=False)
    hide_read_receipts = db.Column(db.Boolean, default=False)
    disable_calls = db.Column(db.Boolean, default=False)

class Chat(db.Model):
    __tablename__ = 'chats'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)  # Nullable for DMs, active string for Group/Channel
    is_group = db.Column(db.Boolean, default=False)
    is_channel = db.Column(db.Boolean, default=False)
    group_avatar = db.Column(db.String(256))
    group_description = db.Column(db.Text)
    group_rules = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    participants = db.relationship('User', secondary=chat_participants, back_populates='chats')
    messages = db.relationship('Message', backref='chat', cascade='all, delete-orphan', lazy='dynamic')
    calls = db.relationship('Call', backref='chat', cascade='all, delete-orphan', lazy='dynamic')

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, image, file, voice, code, video, gif
    file_url = db.Column(db.String(512), nullable=True)
    file_name = db.Column(db.String(256), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_edited = db.Column(db.Boolean, default=False)

    # NEW STATUS TRACKING COLUMN ('sent', 'delivered', 'read')
    status = db.Column(db.String(20), default='sent')

    # Relationships
    reactions = db.relationship('MessageReaction', backref='message', cascade='all, delete-orphan', lazy='dynamic')

class MessageReaction(db.Model):
    __tablename__ = 'message_reactions'
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    emoji = db.Column(db.String(10), nullable=False)

class Contact(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    contact_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, blocked
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Call(db.Model):
    __tablename__ = 'calls'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False)
    caller_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    call_type = db.Column(db.String(10), default='voice')  # voice, video
    status = db.Column(db.String(20), default='missed')  # completed, missed, busy, active
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = db.Column(db.String(50))  # message, call, mention, system
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reported_message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True)
    reason = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, resolved, dismissed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(100), nullable=False)  # "login_failed", "user_banned", "msg_moderated"
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)