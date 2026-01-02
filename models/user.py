from flask_login import UserMixin

class User(UserMixin):
    """User model for Flask-Login"""
    
    def __init__(self, user_id, email, name, role, phone='', is_active=True):
        """
        Initialize User object
        
        Args:
            user_id (str): User's MongoDB ObjectId as string
            email (str): User's email
            name (str): User's full name
            role (str): User's role (user, admin, bouncer, super_admin)
            phone (str): User's phone number (optional)
            is_active (bool): Whether user account is active
        """
        self.id = user_id
        self.email = email
        self.name = name
        self.role = role
        self.phone = phone
        self._is_active = is_active
    
    def get_id(self):
        """Return user ID for Flask-Login"""
        return self.id
    
    @property
    def is_active(self):
        """Return True if user is active"""
        return self._is_active
    
    @is_active.setter
    def is_active(self, value):
        """Allow setting is_active"""
        self._is_active = value
    
    def __repr__(self):
        return f'<User {self.email} ({self.role})>'