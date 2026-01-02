from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, make_response
from flask_login import login_user, logout_user, current_user, login_required
from services.auth_service import auth_service
from services.audit_service import audit_service
from models.user import User
from bson.objectid import ObjectId

auth_bp = Blueprint('auth', __name__)

# ============================================================================
# PAGE ROUTES
# ============================================================================

@auth_bp.route('/login')
def login_page():
    """Render login page with cache busting and redirect loop protection"""
    # FIX: Check for 'logout' flag to bypass the auto-redirect to dashboard.
    # This prevents the loop where logout redirects to login, which redirects back to dashboard.
    is_logging_out = request.args.get('logout') == 'success'
    
    if current_user.is_authenticated and not is_logging_out:
        return redirect(get_dashboard_url(current_user.role))
    
    response = make_response(render_template('login.html'))
    # Prevent caching of the login page to ensure auth state is always fresh
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@auth_bp.route('/register')
def register_page():
    """Render registration page with cache busting"""
    response = make_response(render_template('register.html'))
    # Prevent caching of this page
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@auth_bp.route('/logout')
def logout():
    """Logout user and clear session definitely"""
    if current_user.is_authenticated:
        # LOG LOGOUT
        audit_service.log(
            action_type="user_logout",
            performed_by=current_user.id,
            details=f"User {current_user.name} logged out"
        )
        logout_user()
    
    session.clear()
    
    # Redirect to login with a 'logout=success' parameter to bypass auto-redirect logic
    response = redirect(url_for('auth.login_page', logout='success'))
    
    # Force the browser to treat this redirect as a fresh state
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ============================================================================
# API ROUTES
# ============================================================================

@auth_bp.route('/api/register', methods=['POST'])
def register():
    """Register new user (always as 'user' role)"""
    try:
        # Force session clear on registration attempt to prevent cross-contamination
        if current_user.is_authenticated:
            logout_user()
        session.clear()
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        # Extract and validate data
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        password = data.get('password', '')
        
        if not name or not email or not password:
            return jsonify({
                "success": False,
                "message": "Name, email, and password are required"
            }), 400
        
        # CRITICAL: Public registration is ALWAYS for 'user' role only
        result = auth_service.register_user(
            email=email,
            password=password,
            name=name,
            phone=phone,
            role='user'
        )
        
        if result['success']:
            # LOG REGISTRATION
            audit_service.log(
                action_type="user_registered",
                performed_by=result.get('user_id'),
                details=f"New user registered: {name} ({email})"
            )
            
            return jsonify({
                "success": True,
                "message": "Registration successful! Please login.",
                "redirect": "/auth/login?role=user"
            }), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"Registration error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "Registration failed. Please try again."
        }), 500

@auth_bp.route('/api/login', methods=['POST'])
def login():
    """Login user with role verification"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        email = data.get('email', '').strip()
        password = data.get('password', '')
        expected_role = data.get('role', 'user')
        
        if not email or not password:
            return jsonify({
                "success": False,
                "message": "Email and password are required"
            }), 400
        
        # Validate role is one of the allowed values
        allowed_roles = ['user', 'admin', 'bouncer', 'super_admin']
        if expected_role not in allowed_roles:
            return jsonify({
                "success": False,
                "message": "Invalid role"
            }), 400
        
        result = auth_service.login_user(
            email=email,
            password=password,
            expected_role=expected_role
        )
        
        if not result['success']:
            audit_service.log_system_action(
                action_type="login_failed",
                details=f"Failed login attempt for {email} as {expected_role}",
                metadata={"email": email, "attempted_role": expected_role}
            )
            return jsonify(result), 401
        
        user_data = result['user']
        user_role = result['role']
        
        # Create User object for Flask-Login
        user = User(
            user_id=str(user_data['_id']),
            email=user_data['email'],
            name=user_data['name'],
            role=user_role
        )
        
        # Login the user (creates session)
        login_user(user, remember=True)
        
        # Store additional info in session
        session['user_role'] = user_role
        session['user_name'] = user_data['name']
        
        # LOG SUCCESSFUL LOGIN
        audit_service.log(
            action_type="user_login",
            performed_by=str(user_data['_id']),
            details=f"User {user_data['name']} logged in as {user_role}"
        )
        
        return jsonify({
            "success": True,
            "message": "Login successful",
            "role": user_role,
            "redirect": get_dashboard_url(user_role)
        }), 200
        
    except Exception as e:
        print(f"Login error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "Login failed. Please try again."
        }), 500

@auth_bp.route('/api/logout', methods=['POST', 'GET'])
def api_logout():
    """Logout API endpoint"""
    if current_user.is_authenticated:
        audit_service.log(
            action_type="user_logout",
            performed_by=current_user.id,
            details=f"User {current_user.name} logged out"
        )
        logout_user()
    
    session.clear()
    return jsonify({
        "success": True,
        "message": "Logged out successfully"
    })

@auth_bp.route('/api/profile')
@login_required
def get_profile():
    """Get current user profile"""
    try:
        user_data = auth_service.get_user_data_by_id(current_user.id)
        if not user_data:
            return jsonify({
                "success": False,
                "message": "User not found"
            }), 404
        
        user_data['_id'] = str(user_data['_id'])
        if 'password' in user_data:
            del user_data['password'] 
        
        return jsonify({
            "success": True,
            "user": user_data
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@auth_bp.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        if not old_password or not new_password:
            return jsonify({
                "success": False,
                "message": "Old and new passwords are required"
            }), 400
        
        result = auth_service.change_password(
            user_id=current_user.id,
            old_password=old_password,
            new_password=new_password
        )
        
        if result.get('success'):
            audit_service.log(
                action_type="password_changed",
                performed_by=current_user.id,
                details=f"User {current_user.name} changed their password"
            )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_dashboard_url(role):
    """Get the appropriate dashboard URL based on user role"""
    dashboards = {
        'user': '/user/dashboard',
        'admin': '/admin/dashboard',
        'bouncer': '/bouncer/dashboard',
        'super_admin': '/super-admin/dashboard'
    }
    return dashboards.get(role, '/user/dashboard')