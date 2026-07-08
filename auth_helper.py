import os
from flask_login import UserMixin
from firebase_admin import db as firebase_db

class SessionUser(UserMixin):
    """
    A lightweight, stateless User model to bridge Firebase NoSQL records
    with Flask-Login sessions seamlessly on Vercel serverless containers.
    """
    def __init__(self, user_id, data):
        self.id = user_id
        self.username = data.get('username')
        self.email = data.get('email')
        self.is_admin = data.get('is_admin', False)
        self.is_suspended = data.get('is_suspended', False)
        self.is_banned = data.get('is_banned', False)
        
        # 🌟 Added safe fallback structure to prevent template UndefinedErrors (line 260 crash fix)
        self.profile = {
            "country": data.get("country", "Pakistan"),
            "bio": data.get("bio", "Secure node active.")
        }

def get_session_user(user_id):
    """
    Fetches user data from Firebase Realtime Database and initializes a session user object.
    Used by Flask-Login's user_loader engine.
    """
    if not user_id:
        return None
    try:
        # Pull records directly from the secure /users node path
        user_snapshot = firebase_db.reference(f'users/{user_id}').get()
        if user_snapshot:
            return SessionUser(user_id, user_snapshot)
    except Exception as e:
        print(f"Error loading session user: {e}")
    return None
    
