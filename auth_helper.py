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

        # Mapping profile data to a class for dot-notation access in Jinja2
        profile_data = data.get('profile', {})
        class Profile:
            def __init__(self, p_data):
                self.country = p_data.get('country', 'N/A')
                self.timezone = p_data.get('timezone', 'UTC')
                self.bio = p_data.get('bio', '')
                self.language = p_data.get('language', 'en')

        self.profile = Profile(profile_data)

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
