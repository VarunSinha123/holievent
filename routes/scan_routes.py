from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from services.scan_service import scan_service
from services.bouncer_service import bouncer_service
from services.audit_service import audit_service  # Added for audit logging
from services.database import db
from bson.objectid import ObjectId
from bson import json_util
import json
from datetime import datetime

# IMPORTANT: In app.py, register this blueprint with:
# app.register_blueprint(scan_bp, url_prefix='/bouncer')
scan_bp = Blueprint('scan', __name__)

def safe_get_id(obj):
    """Safely get string ID from current_user object"""
    try:
        if hasattr(obj, 'get_id'): return obj.get_id()
        if hasattr(obj, 'id'): return str(obj.id)
        return None
    except:
        return None

def bouncer_required(f):
    """Decorator for bouncer access"""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        role = getattr(current_user, 'role', None)
        if role not in ['bouncer', 'admin', 'super_admin']:
            return jsonify({"success": False, "message": "Security clearance required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator for admin and super_admin access"""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        role = getattr(current_user, 'role', None)
        if role not in ['admin', 'super_admin']:
            return jsonify({"success": False, "message": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# PAGE ROUTES
# ============================================================================

@scan_bp.route('/')
@scan_bp.route('/dashboard')
@bouncer_required
def dashboard():
    """Bouncer Dashboard"""
    return render_template('bouncer_dashboard.html')

@scan_bp.route('/scan')
@bouncer_required
def scan_page():
    """QR Scanner Page"""
    return render_template('bouncer_scan.html')

@scan_bp.route('/management')
@admin_required
def management_page():
    """Bouncer Management Page (Admin only)"""
    return render_template('bouncer_management.html')

# ============================================================================
# SCANNER API
# ============================================================================

@scan_bp.route('/api/scan', methods=['POST'])
@bouncer_required
def verify_scan():
    """Process a scan"""
    try:
        data = request.json or {}
        serial_number = str(data.get('serial_number', '')).strip().upper()
        event_id = data.get('event_id')
        
        if not serial_number:
            return jsonify({"success": False, "message": "Serial number required"}), 400
            
        if not event_id or event_id == "undefined" or not ObjectId.is_valid(event_id):
            return jsonify({"success": False, "message": "Valid Event ID required"}), 400
        
        user_id = safe_get_id(current_user)
        bouncer_id = None
        
        # Find bouncer assignment for scan count tracking
        if getattr(current_user, 'role', None) == 'bouncer' and user_id:
            assign = db.bouncers.find_one({
                "user_id": ObjectId(user_id), 
                "event_id": ObjectId(event_id), 
                "status": "active"
            })
            if assign: 
                bouncer_id = str(assign['_id'])

        # Call scan service
        result = scan_service.scan_pass(
            serial_number=serial_number,
            event_id=event_id,
            bouncer_id=bouncer_id,
            scanned_by=user_id
        )
        
        return json.loads(json_util.dumps(result))
    except Exception as e:
        print(f"Scan API Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Server Error: {str(e)}"}), 500

@scan_bp.route('/api/event-info/<event_id>', methods=['GET'])
@bouncer_required
def get_event_info(event_id):
    """Get event information by ID"""
    try:
        if not event_id or event_id == "undefined" or not ObjectId.is_valid(event_id):
            return jsonify({"success": False, "message": "Invalid Event ID"}), 400

        event = db.events.find_one({"_id": ObjectId(event_id)})
        if not event:
            return jsonify({"success": False, "message": "Event Not Found"}), 404
            
        return jsonify({
            "success": True,
            "name": event.get('name', 'Unknown Event'),
            "venue": event.get('venue', 'Unknown Venue'),
            "date": str(event.get('date', ''))
        })
    except Exception as e:
        print(f"Event Info Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scan_bp.route('/api/stats', methods=['GET'])
@bouncer_required
def get_stats():
    """Get scan statistics - Returns both bouncer-specific and event-wide stats"""
    try:
        event_id = request.args.get('event_id')
        user_id = safe_get_id(current_user)
        
        if not event_id or event_id == "undefined" or not ObjectId.is_valid(event_id):
            return jsonify({
                "success": False, 
                "message": "Valid event ID required"
            }), 400
        
        if not user_id:
            return jsonify({
                "success": False,
                "message": "User identification failed"
            }), 400
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Query for ALL scans at this event (event-wide stats)
        event_query = {"event_id": ObjectId(event_id)}
        
        total_scans = db.scans.count_documents(event_query)
        valid_scans = db.scans.count_documents({**event_query, "status": "valid"})
        invalid_scans = total_scans - valid_scans
        today_scans_event = db.scans.count_documents({
            **event_query, 
            "scanned_at": {"$gte": today_start}
        })
        
        # Query for THIS BOUNCER's scans (user-specific stats)
        bouncer_query = {
            "event_id": ObjectId(event_id),
            "scanned_by": ObjectId(user_id)
        }
        
        my_total_scans = db.scans.count_documents(bouncer_query)
        my_today_scans = db.scans.count_documents({
            **bouncer_query,
            "scanned_at": {"$gte": today_start}
        })
        
        # Also get the bouncer assignment scan count (should match my_total_scans)
        assignment = db.bouncers.find_one({
            "user_id": ObjectId(user_id),
            "event_id": ObjectId(event_id),
            "status": "active"
        })
        
        assignment_count = assignment.get('scans_count', 0) if assignment else 0
        
        return jsonify({
            "success": True,
            "stats": {
                # Event-wide stats (ALL scans at this event)
                "total_scans": total_scans,
                "valid_scans": valid_scans,
                "invalid_scans": invalid_scans,
                "today_scans": today_scans_event,
                
                # Bouncer-specific stats (THIS bouncer's scans)
                "my_total_scans": my_total_scans,
                "my_today_scans": my_today_scans,
                "assignment_scans_count": assignment_count
            },
            # For backward compatibility
            "my_today_count": my_today_scans
        })
        
    except Exception as e:
        print(f"Stats Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": f"Stats Error: {str(e)}"
        }), 500

@scan_bp.route('/api/scan-history', methods=['GET'])
@bouncer_required
def scan_history():
    """Get scan history - Shows only this bouncer's scans if they're a bouncer"""
    try:
        event_id = request.args.get('event_id')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        user_id = safe_get_id(current_user)
        
        query = {}
        
        # If event specified, filter by event
        if event_id and event_id != "undefined" and ObjectId.is_valid(event_id):
            query['event_id'] = ObjectId(event_id)
        
        # If user is bouncer, show only their scans
        if getattr(current_user, 'role', None) == 'bouncer' and user_id:
            query['scanned_by'] = ObjectId(user_id)
            
        scans = list(
            db.scans.find(query)
            .sort("scanned_at", -1)
            .skip((page-1)*per_page)
            .limit(per_page)
        )
        
        total = db.scans.count_documents(query)
        
        return jsonify({
            "success": True, 
            "scans": json.loads(json_util.dumps(scans)), 
            "total": total,
            "page": page,
            "per_page": per_page
        })
        
    except Exception as e:
        print(f"History Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": str(e)
        }), 500

# ============================================================================
# ASSIGNMENT API
# ============================================================================

@scan_bp.route('/api/event', methods=['GET'])
@scan_bp.route('/api/my-assignments', methods=['GET'])
@bouncer_required
def my_assignments():
    """Get bouncer's event assignments"""
    try:
        uid = safe_get_id(current_user)
        if not uid:
            return jsonify({
                "success": False, 
                "message": "User identification failed",
                "events": [],
                "assignments": []
            }), 400
            
        events = bouncer_service.get_bouncer_events(uid)
        return jsonify({
            "success": True, 
            "assignments": events, 
            "events": events
        })
    except Exception as e:
        print(f"Assignments Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": str(e),
            "events": [],
            "assignments": []
        }), 500

# ============================================================================
# ADMIN MANAGEMENT API
# ============================================================================

@scan_bp.route('/api/list', methods=['GET'])
@admin_required
def list_bouncer_assignments():
    """List all bouncer assignments (Admin only)"""
    try:
        event_id = request.args.get('event_id')
        if event_id in [None, '', 'null', 'undefined']: 
            event_id = None
        
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        bouncers = bouncer_service.get_all_bouncers(
            event_id=event_id, 
            skip=(page-1)*per_page, 
            limit=per_page
        )
        total = bouncer_service.get_total_bouncers(event_id=event_id)
        
        return json.loads(json_util.dumps({
            "success": True, 
            "bouncers": bouncers, 
            "total": total
        }))
    except Exception as e:
        print(f"List Bouncers Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scan_bp.route('/api/create', methods=['POST'])
@admin_required
def create_bouncer_api():
    """Create a new bouncer assignment (Admin only)"""
    try:
        data = request.json
        result = bouncer_service.create_bouncer(
            name=data.get('name'),
            email=data.get('email'),
            password=data.get('password'),
            phone=data.get('phone'),
            event_id=data.get('event_id'),
            assigned_by=safe_get_id(current_user)
        )
        
        # LOG BOUNCER CREATION/ASSIGNMENT
        if result.get('success'):
            audit_service.log(
                action_type="bouncer_created",
                performed_by=safe_get_id(current_user),
                details=f"Bouncer '{data.get('name')}' account created and assigned to event",
                target_user=result.get('bouncer_id')
            )
            
        return jsonify(result), 201 if result['success'] else 400
    except Exception as e:
        print(f"Create Bouncer Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scan_bp.route('/api/delete/<bouncer_id>', methods=['DELETE'])
@admin_required
def delete_bouncer_assignment(bouncer_id):
    """Delete a bouncer assignment (Admin only)"""
    try:
        # Get assignment details for log before removal
        assign = db.bouncers.find_one({"_id": ObjectId(bouncer_id)})
        
        success = bouncer_service.remove_bouncer(bouncer_id)
        
        # LOG BOUNCER REMOVAL
        if success and assign:
            audit_service.log(
                action_type="bouncer_removed",
                performed_by=safe_get_id(current_user),
                details=f"Bouncer assignment record permanently removed (ID: {bouncer_id})",
                target_user=str(assign.get('user_id'))
            )
            
        return jsonify({
            "success": success, 
            "message": "Assignment removed" if success else "Failed to remove assignment"
        })
    except Exception as e:
        print(f"Delete Bouncer Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scan_bp.route('/api/users-available', methods=['GET'])
@admin_required
def get_available_users():
    """Get list of users with bouncer role (Admin only)"""
    try:
        bouncer_users = list(db.users.find({"role": "bouncer"}, {"password": 0}))
        users = [
            {
                'id': str(u['_id']), 
                'name': u.get('name'), 
                'email': u.get('email')
            } 
            for u in bouncer_users
        ]
        return jsonify({"success": True, "users": users})
    except Exception as e:
        print(f"Available Users Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500