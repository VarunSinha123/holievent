from flask import Flask, request, jsonify, session, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from functools import wraps
from datetime import timedelta
import os

# Configuration Class
class Config:
    # Flask Core
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    
    # MongoDB Connection
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'event_pass_system')
    
    # AWS S3
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
    
    # Limits & Security
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    BCRYPT_LOG_ROUNDS = 12
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

    @staticmethod
    def allowed_file(filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Session Persistence & Security
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    app.config['SESSION_COOKIE_SECURE'] = (Config.FLASK_ENV == 'production')
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = "strong"
    
    @login_manager.user_loader
    def load_user(user_id):
        from services.auth_service import auth_service
        return auth_service.get_user_by_id(user_id)
    
    @login_manager.unauthorized_handler
    def unauthorized():
        session.clear()
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "Authentication required"}), 401
        return redirect(url_for('auth.login_page'))
    
    # --- Role-Based Access Decorators ---
    def admin_required(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in ['admin', 'super_admin']:
                if request.path.startswith('/api/'):
                    return jsonify({"success": False, "message": "Admin access required"}), 403
                return "Forbidden: Admin access required", 403
            return f(*args, **kwargs)
        return decorated_function
    
    def super_admin_required(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != 'super_admin':
                if request.path.startswith('/api/'):
                    return jsonify({"success": False, "message": "Super Admin access required"}), 403
                return "Forbidden: Super Admin access required", 403
            return f(*args, **kwargs)
        return decorated_function
    
    def bouncer_required(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            allowed_roles = ['bouncer', 'admin', 'super_admin']
            if not current_user.is_authenticated or current_user.role not in allowed_roles:
                if request.path.startswith('/api/'):
                    return jsonify({"success": False, "message": "Security clearance required"}), 403
                return "Forbidden: Bouncer access required", 403
            return f(*args, **kwargs)
        return decorated_function

    app.admin_required = admin_required
    app.super_admin_required = super_admin_required
    app.bouncer_required = bouncer_required

    # --- Blueprint Registration ---
    from routes.auth_routes import auth_bp
    from routes.admin_routes import admin_bp
    from routes.super_admin_routes import super_admin_bp
    from routes.bouncer_routes import bouncer_bp
    from routes.user_routes import user_bp
    from routes.event_routes import event_bp
    from routes.main_routes import main_bp
    from routes.pass_routes import pass_bp
    from routes.scan_routes import scan_bp
    from routes.bulk_qr_routes import bulk_qr_bp  # ADDED THIS LINE
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(super_admin_bp, url_prefix='/super-admin')
    app.register_blueprint(bouncer_bp, url_prefix='/bouncer')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(event_bp, url_prefix='/event')
    app.register_blueprint(pass_bp, url_prefix='/pass')
    app.register_blueprint(scan_bp, url_prefix='/scan')
    app.register_blueprint(bulk_qr_bp)  # ADDED THIS LINE - no prefix because it has url_prefix='/bulk-qr' in the blueprint itself
    app.register_blueprint(main_bp) 
    
    # --- Security Headers ---
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
        )
        response.headers['Content-Security-Policy'] = csp_policy
        
        if app.config['FLASK_ENV'] == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            
        return response
    
    # --- Error Handlers ---
    @app.errorhandler(401)
    def unauthorized_error(e):
        session.clear()
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        return redirect(url_for('auth.login_page'))
    
    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "Access forbidden"}), 403
        return "Access Forbidden - Missing permissions", 403
    
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "Endpoint not found"}), 404
        return "Page Not Found", 404
    
    @app.errorhandler(500)
    def internal_error(e):
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "Critical server error"}), 500
        return "Internal Server Error", 500
    
    # --- Root Route Logic ---
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            try:
                from services.auth_service import auth_service
                fresh_user = auth_service.get_user_by_id(current_user.id)
                
                if not fresh_user or not fresh_user.get('is_active', True):
                    from flask_login import logout_user
                    logout_user()
                    session.clear()
                    return redirect(url_for('auth.login_page'))
                
                # Role redirection logic
                role_map = {
                    'super_admin': 'super_admin.dashboard',
                    'admin': 'admin.dashboard',
                    'bouncer': 'bouncer.dashboard'
                }
                endpoint = role_map.get(current_user.role, 'user.dashboard')
                return redirect(url_for(endpoint))

            except Exception:
                from flask_login import logout_user
                logout_user()
                session.clear()
                return redirect(url_for('auth.login_page'))
        
        return redirect(url_for('auth.login_page'))
    
    @app.route('/health')
    def health_check():
        return jsonify({
            "status": "healthy",
            "auth_status": "authenticated" if current_user.is_authenticated else "anonymous",
            "session_exists": bool(session)
        })
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(
        debug=(app.config['FLASK_ENV'] == 'development'),
        host='0.0.0.0',
        port=5000
    )