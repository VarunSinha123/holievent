from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_required, current_user
from services.bouncer_service import bouncer_service
from services.scan_service import scan_service
from services.audit_service import audit_service  # Added import
from services.database import db
from bson import json_util
from bson.objectid import ObjectId
from datetime import datetime
import json

bouncer_bp = Blueprint('bouncer', __name__)

def admin_required(f):
    """Decorator for admin and super_admin access"""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['admin', 'super_admin']:
            return jsonify({"success": False, "message": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def bouncer_required(f):
    """Decorator for bouncer access"""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['bouncer', 'admin', 'super_admin']:
            return jsonify({"success": False, "message": "Bouncer access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# BOUNCER PAGES
# ============================================================================

@bouncer_bp.route('/dashboard')
@bouncer_required
def dashboard():
    """Render the bouncer dashboard"""
    return render_template('bouncer_dashboard.html')

@bouncer_bp.route('/scan')
@bouncer_required
def scan_page():
    """Render the QR scanner page"""
    return render_template('bouncer_scan.html')

@bouncer_bp.route('/management')
@admin_required
def management_page():
    """Bouncer management page for admins"""
    return render_template('bouncer_management.html')

# ============================================================================
# BOUNCER API - For Bouncer Users
# ============================================================================

@bouncer_bp.route('/api/event', methods=['GET'])
@bouncer_required
def get_my_events():
    """Get events for current user. Admins/Super Admins see all active events."""
    try:
        # If user is admin/super_admin, they aren't "assigned" to events in the bouncers collection
        # We should return all active events for them to choose from
        if current_user.role in ['admin', 'super_admin']:
            active_events = list(db.events.find({"is_active": True}))
            events = []
            for ev in active_events:
                events.append({
                    "event_id": str(ev["_id"]),
                    "event_name": ev.get("name", "Unknown Event"),
                    "event_date": str(ev.get("date", "N/A")),
                    "gate_name": "Master Access"
                })
            return jsonify({
                "success": True,
                "events": events,
                "is_admin_view": True
            }), 200
            
        # Standard bouncer logic
        events = bouncer_service.get_bouncer_events(current_user.id)
        return jsonify({
            "success": True,
            "events": events,
            "is_admin_view": False
        }), 200
    except Exception as e:
        print(f"Get Events Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@bouncer_bp.route('/api/event-info/<event_id>', methods=['GET'])
@bouncer_required
def get_event_info(event_id):
    """Fetch event details for the scanner header"""
    try:
        if not ObjectId.is_valid(event_id):
            return jsonify({"success": False, "message": "Invalid event ID"}), 400
            
        event = db.events.find_one({"_id": ObjectId(event_id)})
        if not event:
            return jsonify({"success": False, "message": "Event not found"}), 404
            
        return jsonify({
            "success": True,
            "name": event.get('name'),
            "date": str(event.get('date', '')),
            "venue": event.get('venue')
        })
    except Exception as e:
        print(f"Event Info Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 400

@bouncer_bp.route('/api/scan', methods=['POST'])
@bouncer_required
def verify_scan():
    """Verify a scanned ticket using ScanService"""
    try:
        data = request.json
        serial_number = data.get('serial_number', '').strip().upper()
        event_id = data.get('event_id')
        
        if not serial_number or not event_id:
            return jsonify({"success": False, "message": "Missing serial number or event ID"}), 400

        if not ObjectId.is_valid(event_id):
            return jsonify({"success": False, "message": "Invalid event ID"}), 400

        # Find the specific bouncer assignment record for this event
        bouncer_assignment = db.bouncers.find_one({
            "user_id": ObjectId(current_user.id),
            "event_id": ObjectId(event_id),
            "status": "active"
        })
        
        bouncer_assignment_id = str(bouncer_assignment['_id']) if bouncer_assignment else None

        # Delegate validation and recording logic to the Service
        result = scan_service.scan_pass(
            serial_number=serial_number,
            event_id=event_id,
            bouncer_id=bouncer_assignment_id,
            scanned_by=current_user.id
        )

        return json.loads(json_util.dumps(result))

    except Exception as e:
        print(f"Scan Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Critical Error: {str(e)}"}), 500

@bouncer_bp.route('/api/stats', methods=['GET'])
@bouncer_required
def get_bouncer_stats():
    """Get scan statistics - Returns both bouncer-specific and event-wide stats"""
    try:
        event_id = request.args.get('event_id')
        if not event_id or not ObjectId.is_valid(event_id):
            return jsonify({"success": False, "message": "Valid event ID required"}), 400
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Event-wide stats (ALL scans at this event)
        event_query = {"event_id": ObjectId(event_id)}
        
        total_scans = db.scans.count_documents(event_query)
        valid_scans = db.scans.count_documents({**event_query, "status": "valid"})
        invalid_scans = total_scans - valid_scans
        today_scans_event = db.scans.count_documents({
            **event_query, 
            "scanned_at": {"$gte": today_start}
        })
        
        # Bouncer-specific stats (THIS bouncer's scans only)
        bouncer_query = {
            "event_id": ObjectId(event_id),
            "scanned_by": ObjectId(current_user.id)
        }
        
        my_total_scans = db.scans.count_documents(bouncer_query)
        my_today_scans = db.scans.count_documents({
            **bouncer_query,
            "scanned_at": {"$gte": today_start}
        })
        
        return jsonify({
            "success": True,
            "stats": {
                # Event-wide stats
                "total_scans": total_scans,
                "valid_scans": valid_scans,
                "invalid_scans": invalid_scans,
                "today_scans": today_scans_event,
                
                # Bouncer-specific stats
                "my_total_scans": my_total_scans,
                "my_today_scans": my_today_scans
            },
            "my_today_count": my_today_scans  # For backward compatibility
        }), 200
        
    except Exception as e:
        print(f"Stats Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

@bouncer_bp.route('/api/scan-history', methods=['GET'])
@bouncer_required
def get_scan_history():
    """Get scan history for bouncer"""
    try:
        event_id = request.args.get('event_id')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        query = {}
        
        # If event specified, filter by event
        if event_id and ObjectId.is_valid(event_id):
            query['event_id'] = ObjectId(event_id)
        
        # If user is bouncer, show only their scans
        if current_user.role == 'bouncer':
            query['scanned_by'] = ObjectId(current_user.id)
            
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
        print(f"Scan History Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# ADMIN API - Bouncer Management
# ============================================================================

@bouncer_bp.route('/api/list', methods=['GET'])
@admin_required
def list_bouncers():
    """List all bouncer assignments"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        event_id = request.args.get('event_id')
        
        if event_id in [None, '', 'null', 'undefined']:
            event_id = None

        skip = (page - 1) * per_page
        bouncers = bouncer_service.get_all_bouncers(event_id=event_id, skip=skip, limit=per_page)
        total = bouncer_service.get_total_bouncers(event_id=event_id)
        
        return json.loads(json_util.dumps({
            "success": True,
            "bouncers": bouncers,
            "total": total,
            "page": page,
            "per_page": per_page
        })), 200
    except Exception as e:
        print(f"List Bouncers Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@bouncer_bp.route('/api/users', methods=['GET'])
@admin_required
def get_bouncer_users():
    """Get all users with bouncer role with aggregated stats"""
    try:
        bouncer_users = list(db.users.find({"role": "bouncer"}, {"password": 0}))
        
        for user in bouncer_users:
            user_id_str = str(user['_id'])
            user['events_assigned'] = db.bouncers.count_documents({"user_id": user['_id']})
            user['total_scans'] = db.scans.count_documents({"scanned_by": user['_id']})
            user['id'] = user_id_str
        
        return json.loads(json_util.dumps({
            "success": True,
            "bouncers": bouncer_users
        })), 200
    except Exception as e:
        print(f"Get Bouncer Users Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@bouncer_bp.route('/api/create', methods=['POST'])
@admin_required
def create_bouncer():
    """Create new bouncer account and assign to event"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        result = bouncer_service.create_bouncer(
            name=data.get('name', '').strip(),
            email=data.get('email', '').strip(),
            password=data.get('password', '').strip(),
            phone=data.get('phone', '').strip(),
            event_id=data.get('event_id'),
            assigned_by=str(current_user.id)
        )
        
        if result.get('success'):
            # LOG BOUNCER CREATION
            audit_service.log(
                action_type="bouncer_created",
                performed_by=current_user.id,
                details=f"New bouncer account created: '{data.get('name')}' ({data.get('email')})",
                target_user=result.get('bouncer_id')
            )
        
        return jsonify(result), 201 if result['success'] else 400
    except Exception as e:
        print(f"Create Bouncer Error: {str(e)}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

@bouncer_bp.route('/api/assign', methods=['POST'])
@admin_required
def assign_bouncer():
    """Assign existing bouncer to event"""
    try:
        data = request.json
        user_id = data.get('user_id')
        event_id = data.get('event_id')
        
        result = bouncer_service.assign_bouncer_to_event(
            user_id=user_id,
            event_id=event_id,
            assigned_by=str(current_user.id)
        )
        
        if result.get('success'):
            # Get event name for logging
            event = db.events.find_one({"_id": ObjectId(event_id)})
            bouncer = db.users.find_one({"_id": ObjectId(user_id)})
            event_name = event.get('name') if event else event_id
            bouncer_name = bouncer.get('name') if bouncer else user_id
            
            # LOG ASSIGNMENT
            audit_service.log(
                action_type="bouncer_assigned",
                performed_by=current_user.id,
                details=f"Bouncer '{bouncer_name}' assigned to event '{event_name}'",
                target_user=user_id
            )
            
        return jsonify(result), 200 if result['success'] else 400
    except Exception as e:
        print(f"Assign Bouncer Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@bouncer_bp.route('/api/assignments/<assignment_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_assignment(assignment_id):
    """Deactivate a bouncer assignment"""
    try:
        assignment = db.bouncers.find_one({"_id": ObjectId(assignment_id)})
        if not assignment:
            return jsonify({"success": False, "message": "Assignment not found"}), 404
            
        result = db.bouncers.update_one(
            {"_id": ObjectId(assignment_id)},
            {"$set": {"status": "inactive"}}
        )
        
        if result.modified_count > 0:
            # LOG DEACTIVATION
            bouncer = db.users.find_one({"_id": assignment.get('user_id')})
            event = db.events.find_one({"_id": assignment.get('event_id')})
            bouncer_name = bouncer.get('name') if bouncer else "Unknown"
            event_name = event.get('name') if event else "Unknown Event"
            
            audit_service.log(
                action_type="bouncer_deactivated",
                performed_by=current_user.id,
                details=f"Bouncer '{bouncer_name}' assignment deactivated for event '{event_name}'",
                target_user=str(assignment.get('user_id'))
            )
            
            return jsonify({"success": True, "message": "Assignment deactivated"}), 200
        return jsonify({"success": False, "message": "No changes made"}), 404
    except Exception as e:
        print(f"Deactivate Assignment Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@bouncer_bp.route('/api/delete/<bouncer_id>', methods=['DELETE'])
@admin_required
def delete_bouncer(bouncer_id):
    """Delete bouncer assignment record"""
    try:
        # Get assignment details for log before removal
        assignment = db.bouncers.find_one({"_id": ObjectId(bouncer_id)})
        
        success = bouncer_service.remove_bouncer(bouncer_id)
        
        if success and assignment:
            # LOG REMOVAL
            audit_service.log(
                action_type="bouncer_removed",
                performed_by=current_user.id,
                details=f"Bouncer assignment record permanently removed (ID: {bouncer_id})",
                target_user=str(assignment.get('user_id'))
            )
            
        return jsonify({
            "success": success,
            "message": "Bouncer assignment removed" if success else "Failed to remove"
        }), 200 if success else 400
    except Exception as e:
        print(f"Delete Bouncer Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@bouncer_bp.route('/api/users-available', methods=['GET'])
@admin_required
def get_available_users():
    """Get list of users eligible for bouncer assignments"""
    try:
        bouncer_users = list(db.users.find({"role": "bouncer"}, {"password": 0}))
        users = [
            {
                'id': str(u['_id']),
                'name': u.get('name'),
                'email': u.get('email'),
                'phone': u.get('phone', '')
            }
            for u in bouncer_users
        ]
        return jsonify({"success": True, "users": users}), 200
    except Exception as e:
        print(f"Available Users Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500