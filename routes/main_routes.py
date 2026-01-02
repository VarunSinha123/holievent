from flask import Blueprint, render_template, jsonify
from services.pass_service import pass_service
from services.event_service import event_service

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main landing page"""
    return render_template('login.html')

@main_bp.route('/admin')
def admin_dashboard():
    """Super admin dashboard"""
    return render_template('super_admin_dashboard.html')

@main_bp.route('/api/stats', methods=['GET'])
def get_stats():
    """Get event statistics with ticket type breakdown"""
    stats = pass_service.get_stats()
    return jsonify(stats)

@main_bp.route('/api/dashboard-stats', methods=['GET'])
def get_dashboard_stats():
    """Get comprehensive dashboard statistics (Passes and Events only)"""
    try:
        # Pass statistics
        pass_stats = pass_service.get_stats()
        
        # Event statistics
        total_events = event_service.get_total_events()
        active_events = event_service.count_active_events()
        
        # Combine available stats
        dashboard_stats = {
            "success": True,
            "passes": pass_stats,
            "events": {
                "total": total_events,
                "active": active_events
            }
        }
        
        return jsonify(dashboard_stats)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500