from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from services.database import db
from models.user import User
from bson.objectid import ObjectId
import re

class AuthService:
    """Service for user authentication and management"""
    
    def __init__(self):
        """Initialize auth service"""
        # Removed automatic admin/super_admin creation as requested
        pass
    
    def validate_email(self, email):
        """Validate email format using regex"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def validate_password(self, password):
        """Validate password strength"""
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        return True, "Valid"
    
    def register_user(self, email, password, name, phone='', role='user'):
        """
        Register a new user in the system
        
        Args:
            email (str): User's email
            password (str): User's password (plain text)
            name (str): User's full name
            phone (str): User's phone number (optional)
            role (str): User's role (default: 'user')
        
        Returns:
            dict: Success status and message
        """
        try:
            # Normalize email
            email = email.strip().lower()
            
            # Validate email
            if not self.validate_email(email):
                return {"success": False, "message": "Invalid email format"}
            
            # Check if user already exists
            existing_user = db.users.find_one({"email": email})
            if existing_user:
                return {"success": False, "message": "Email already registered"}
            
            # Validate password
            valid, msg = self.validate_password(password)
            if not valid:
                return {"success": False, "message": msg}
            
            # Hash password using scrypt
            hashed_password = generate_password_hash(password, method='scrypt')
            
            # Create user document
            user_data = {
                "email": email,
                "password": hashed_password,
                "name": name.strip(),
                "phone": phone.strip() if phone else "",
                "role": role,
                "created_at": datetime.now(),
                "is_active": True
            }
            
            result = db.users.insert_one(user_data)
            
            print(f"✅ User registered: {email} as {role}")
            
            return {
                "success": True,
                "message": "Registration successful",
                "user_id": str(result.inserted_id)
            }
            
        except Exception as e:
            print(f"❌ Registration error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": "Registration failed. Please try again."
            }
    
    def login_user(self, email, password, expected_role=None):
        """
        Authenticate user and verify role
        
        Args:
            email (str): User's email
            password (str): User's password (plain text)
            expected_role (str): Role user is trying to login as (optional)
        
        Returns:
            dict: Success status, message, user_data dict, and role
        """
        try:
            # Normalize email
            email = email.strip().lower()
            
            print(f"🔐 Login attempt: {email} as {expected_role}")
            
            # Find user by email
            user_data = db.users.find_one({"email": email})
            
            if not user_data:
                print(f"❌ User not found: {email}")
                return {
                    "success": False,
                    "message": "Invalid email or password"
                }
            
            # Check if account is active
            if not user_data.get('is_active', True):
                print(f"❌ Account disabled: {email}")
                return {
                    "success": False,
                    "message": "Account is disabled. Contact administrator."
                }
            
            # Verify hashed password
            if not check_password_hash(user_data['password'], password):
                print(f"❌ Invalid password for: {email}")
                return {
                    "success": False,
                    "message": "Invalid email or password"
                }
            
            user_role = user_data.get('role', 'user')
            
            # Verify role if restricted login is requested
            if expected_role and user_role != expected_role:
                print(f"❌ Role mismatch: User is {user_role}, tried to login as {expected_role}")
                return {
                    "success": False,
                    "message": f"Invalid credentials for {expected_role} login. Your account is registered as {user_role}."
                }
            
            # Update last login timestamp
            db.users.update_one(
                {"_id": user_data['_id']},
                {"$set": {"last_login": datetime.now()}}
            )
            
            print(f"✅ Login successful: {email} as {user_role}")
            
            return {
                "success": True,
                "message": "Login successful",
                "user": user_data,
                "role": user_role
            }
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": "Login failed. Please try again."
            }
    
    def get_user_by_id(self, user_id):
        """
        Get user by ID for Flask-Login loader
        
        Args:
            user_id (str): User's MongoDB ObjectId as string
        
        Returns:
            User: User model instance or None
        """
        try:
            user_data = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user_data or not user_data.get('is_active', True):
                return None
            
            # Map database dictionary to User model
            user = User(
                user_id=str(user_data['_id']),
                email=user_data['email'],
                name=user_data['name'],
                role=user_data.get('role', 'user'),
                phone=user_data.get('phone', ''),
                is_active=user_data.get('is_active', True)
            )
            
            return user
            
        except Exception as e:
            print(f"Error getting user by ID: {e}")
            return None
    
    def get_user_by_email(self, email):
        """Get user by email and return as User object"""
        try:
            email = email.strip().lower()
            user_data = db.users.find_one({"email": email})
            
            if not user_data:
                return None
            
            return User(
                user_id=str(user_data['_id']),
                email=user_data['email'],
                name=user_data['name'],
                role=user_data.get('role', 'user'),
                phone=user_data.get('phone', ''),
                is_active=user_data.get('is_active', True)
            )
            
        except Exception as e:
            print(f"Error getting user by email: {e}")
            return None
    
    def get_user_data_by_id(self, user_id):
        """Get raw user data dictionary from database"""
        try:
            return db.users.find_one({"_id": ObjectId(user_id)})
        except Exception as e:
            print(f"Error getting user data by ID: {e}")
            return None
    
    def update_user_profile(self, user_id, name=None, phone=None):
        """Update user profile details"""
        try:
            update_data = {}
            if name:
                update_data['name'] = name.strip()
            if phone is not None:
                update_data['phone'] = phone.strip()
            
            if not update_data:
                return {"success": False, "message": "No data to update"}
            
            result = db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                return {"success": True, "message": "Profile updated successfully"}
            
            return {"success": False, "message": "No changes made"}
            
        except Exception as e:
            print(f"Profile update error: {e}")
            return {"success": False, "message": "Update failed"}
    
    def change_password(self, user_id, old_password, new_password):
        """Verify old password and set new password"""
        try:
            user_data = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user_data:
                return {"success": False, "message": "User not found"}
            
            # Verify current password
            if not check_password_hash(user_data['password'], old_password):
                return {"success": False, "message": "Current password is incorrect"}
            
            # Validate strength of new password
            valid, msg = self.validate_password(new_password)
            if not valid:
                return {"success": False, "message": msg}
            
            # Hash and store new password
            new_hash = generate_password_hash(new_password, method='scrypt')
            db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {
                    "password": new_hash,
                    "password_changed_at": datetime.now()
                }}
            )
            
            return {"success": True, "message": "Password changed successfully"}
            
        except Exception as e:
            print(f"Password change error: {e}")
            return {"success": False, "message": "Password change failed"}
    
    def get_all_users(self, role=None, skip=0, limit=50):
        """Fetch list of users (Admin tool)"""
        try:
            query = {}
            if role:
                query['role'] = role
            
            users = list(db.users.find(query, {"password": 0})
                        .sort("created_at", -1)
                        .skip(skip)
                        .limit(limit))
            
            return users
            
        except Exception as e:
            print(f"Error fetching users: {e}")
            return []
    
    def toggle_user_status(self, user_id, is_active):
        """Enable or disable a user account (Admin tool)"""
        try:
            result = db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"is_active": is_active}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error toggling user status: {e}")
            return False

# Export singleton instance
auth_service = AuthService()