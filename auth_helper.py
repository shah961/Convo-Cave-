import os
from flask_login import UserMixin
from firebase_admin import db as firebase_db

class SessionUser(UserMixin):
    """
    An expanded User model to bridge Firebase NoSQL records
    with Flask-Login sessions seamlessly on Vercel.
    """
    def __init__(self, user_id, data):
        self.id = user_id
        self.username = data.get('username')
        self.email = data.get('email')
        self.full_name = data.get('full_name', '')
        self.profile_pic = data.get('profile_pic', '')
        self.is_admin = data.get('is_admin', False)
        self.is_suspended = data.get('is_suspended', False)
        self.is_banned = data.get('is_banned', False)
        self.phone = data.get('phone', '')
        self.dob = data.get('dob', '')
        
        self.profile = {
            "country": data.get("country", "Pakistan"),
            "language": data.get("language", "en"),
            "timezone": data.get("timezone", "PKT"),
            "bio": data.get("bio", "Go Protocol Active.")
        }

        self.settings = data.get('settings', {
            "privacy": {
                "last_seen": "everyone",
                "online_status": "everyone",
                "profile_photo": "everyone",
                "about": "everyone",
                "read_receipts": True
            },
            "appearance": {
                "theme": "dark",
                "font_size": "standard",
                "wallpaper": "default"
            },
            "notifications": {
                "messages": True,
                "calls": True,
                "groups": True
            }
        })

def get_session_user(user_id):
    """
    Fetches user data from Firebase Realtime Database and initializes a session user object.
    Used by Flask-Login's user_loader engine.
    """
    if not user_id:
        return None
    try:
        user_snapshot = firebase_db.reference(f'users/{user_id}').get()
        if user_snapshot:
            return SessionUser(user_id, user_snapshot)
    except Exception as e:
        print(f"Error loading session user: {e}")
    return None
