from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required, current_user
from services.event_service import event_service
from services.bouncer_service import bouncer_service
from services.auth_service import auth_service
from services.pass_service import pass_service
from services.database import db
from bson import json_util
from bson.objectid import ObjectId
from datetime import datetime
import json
import io
import csv
import traceback

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard page"""
    if current_user.role not in ['admin', 'super_admin']:
        return "Access Denied - Admin access required", 403
    return render_template('admin_dashboard.html')

@admin_bp.route('/events')
@login_required
def events_page():
    """Event management page"""
    if current_user.role not in ['admin', 'super_admin']:
        return "Access Denied", 403
    return render_template('event_management.html')

@admin_bp.route('/api/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    """Get comprehensive dashboard statistics"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        # User statistics
        total_users = db.users.count_documents({"role": "user"})
        new_users_today = db.users.count_documents({
            "role": "user",
            "created_at": {"$gte": datetime.combine(datetime.today(), datetime.min.time())}
        })
        
        # Event statistics
        total_events = db.events.count_documents({})
        active_events = db.events.count_documents({"is_active": True})
        
        # Pass statistics
        total_passes = db.passes.count_documents({})
        total_scans = db.scans.count_documents({})
        scan_rate = round((total_scans / total_passes * 100), 1) if total_passes > 0 else 0
        
        # Bouncer statistics
        total_bouncers = db.users.count_documents({"role": "bouncer"})
        active_assignments = db.bouncers.count_documents({"status": "active"})
        
        
        stats = {
            "users": {
                "total": total_users,
                "new_today": new_users_today
            },
            "events": {
                "total": total_events,
                "active": active_events
            },
            "passes": {
                "total": total_passes,
                "scanned": total_scans,
                "scan_rate": scan_rate
            },
            "bouncers": {
                "total": total_bouncers,
                "active_assignments": active_assignments
            },
        }
        
        return jsonify({
            "success": True,
            "stats": stats
        })
        
    except Exception as e:
        print(f"Error getting stats: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@admin_bp.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    """Change admin's own password"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({
                "success": False,
                "message": "Current password and new password are required"
            }), 400
        
        if len(new_password) < 6:
            return jsonify({
                "success": False,
                "message": "New password must be at least 6 characters"
            }), 400
        
        # Verify current password
        user = db.users.find_one({"_id": ObjectId(current_user.id)})
        if not user:
            return jsonify({
                "success": False,
                "message": "User not found"
            }), 404
        
        from werkzeug.security import check_password_hash, generate_password_hash
        
        if not check_password_hash(user['password'], current_password):
            return jsonify({
                "success": False,
                "message": "Current password is incorrect"
            }), 401
        
        # Update password
        hashed_password = generate_password_hash(new_password)
        result = db.users.update_one(
            {"_id": ObjectId(current_user.id)},
            {
                "$set": {
                    "password": hashed_password,
                    "updated_at": datetime.now()
                }
            }
        )
        
        if result.modified_count > 0:
            # Log the password change
            db.audit_logs.insert_one({
                "action_type": "password_changed",
                "performed_by": ObjectId(current_user.id),
                "details": f"Password changed for {user.get('name')}",
                "timestamp": datetime.now()
            })
            
            return jsonify({
                "success": True,
                "message": "Password changed successfully"
            })
        
        return jsonify({
            "success": False,
            "message": "Failed to update password"
        }), 500
        
    except Exception as e:
        print(f"Error changing password: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        }), 500

@admin_bp.route('/api/users/<user_id>/toggle', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    """Enable/disable user account"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        data = request.json
        is_active = data.get('is_active', True)
        
        try:
            user_oid = ObjectId(user_id)
        except Exception:
            return jsonify({
                "success": False,
                "message": "Invalid user ID format"
            }), 400
        
        user = db.users.find_one({"_id": user_oid})
        if not user:
            return jsonify({
                "success": False,
                "message": "User not found"
            }), 404
        
        if user.get('role') == 'super_admin' and not is_active:
            return jsonify({
                "success": False,
                "message": "Cannot deactivate super admin accounts"
            }), 403
        
        if str(user_oid) == str(current_user.id):
            return jsonify({
                "success": False,
                "message": "Cannot deactivate your own account"
            }), 403
        
        result = db.users.update_one(
            {"_id": user_oid},
            {"$set": {"is_active": is_active, "updated_at": datetime.now()}}
        )
        
        if result.matched_count > 0:
            db.audit_logs.insert_one({
                "action_type": "user_status_changed",
                "performed_by": ObjectId(current_user.id),
                "target_user": user_oid,
                "details": f"User '{user.get('name')}' {'activated' if is_active else 'deactivated'}",
                "timestamp": datetime.now()
            })
            
            return jsonify({
                "success": True,
                "message": f"User {'activated' if is_active else 'deactivated'} successfully"
            })
        
        return jsonify({
            "success": False,
            "message": "No changes made"
        }), 400
        
    except Exception as e:
        print(f"Error toggling user status: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        }), 500

@admin_bp.route('/api/user', methods=['GET'])
@login_required
def get_users():
    """Get all users with pagination - FIXED VERSION"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        search = request.args.get('search', '')
        
        skip = (page - 1) * per_page
        
        # Build query
        query = {"role": "user"}
        if search:
            query['$or'] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]
        
        # Get users from database
        users = list(db.users.find(query, {"password": 0})
                    .sort("created_at", -1)
                    .skip(skip)
                    .limit(per_page))
        
        # Add order count for each user (if orders collection exists)
        for user in users:
            try:
                # Check if orders collection exists
                if 'orders' in db.list_collection_names():
                    order_count = db.orders.count_documents({"user_id": user['_id']})
                else:
                    # If orders collection doesn't exist, count passes instead
                    order_count = db.passes.count_documents({"user_id": user['_id']})
                user['order_count'] = order_count
            except Exception as e:
                print(f"Error counting orders for user {user.get('email')}: {e}")
                user['order_count'] = 0
        
        # Get total count
        total = db.users.count_documents(query)
        
        # Convert to JSON
        users_json = json.loads(json_util.dumps(users))
        
        return jsonify({
            "success": True,
            "users": users_json,
            "total": total,
            "page": page,
            "per_page": per_page
        })
        
    except Exception as e:
        print(f"❌ Error in get_users endpoint: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        }), 500

@admin_bp.route('/api/bouncers', methods=['GET'])
@login_required
def get_bouncers():
    """Get all bouncers"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        bouncers = bouncer_service.get_all_bouncers()
        bouncers_json = json.loads(json_util.dumps(bouncers))
        
        return jsonify({
            "success": True,
            "bouncers": bouncers_json
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@admin_bp.route('/api/bouncers/create', methods=['POST'])
@login_required
def create_bouncer():
    """Create new bouncer account"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        data = request.json
        result = auth_service.register_user(
            email=data.get('email'),
            password=data.get('password'),
            name=data.get('name'),
            phone=data.get('phone', ''),
            role='bouncer'
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@admin_bp.route('/api/bouncers/assign', methods=['POST'])
@login_required
def assign_bouncer():
    """Assign bouncer to event"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        data = request.json
        result = bouncer_service.assign_bouncer_to_event(
            data.get('user_id'), 
            data.get('event_id'), 
            data.get('gate_name', 'Main Gate')
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@admin_bp.route('/api/bouncers/remove-assignment', methods=['POST'])
@login_required
def remove_bouncer_assignment():
    """Remove bouncer from event"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        data = request.json
        success = bouncer_service.remove_bouncer_assignment(data.get('user_id'), data.get('event_id'))
        if success:
            return jsonify({"success": True, "message": "Bouncer removed from event"})
        return jsonify({"success": False, "message": "Failed to remove assignment"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@admin_bp.route('/api/passes/bulk-generate', methods=['POST'])
@login_required
def bulk_generate_passes():
    """Generate multiple passes at once"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        data = request.json
        count = int(data.get('count', 1))
        
        if count < 1 or count > 100:
            return jsonify({"success": False, "message": "Count must be between 1 and 100"}), 400
        
        generated = []
        for i in range(count):
            result = pass_service.create_pass(
                attendee_name=data.get('attendee_name', f'Guest {i+1}'),
                ticket_type=data.get('ticket_type'),
                event_name=data.get('event_name'),
                event_date=data.get('event_date'),
                venue=data.get('venue')
            )
            if result.get('success'):
                generated.append(result['serial_number'])
        
        return jsonify({"success": True, "message": f"Generated {len(generated)} passes", "serial_numbers": generated})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@admin_bp.route('/api/passes/<serial_number>/deactivate', methods=['POST'])
@login_required
def deactivate_pass(serial_number):
    """Deactivate/cancel a pass"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        result = db.passes.update_one(
            {"serial_number": serial_number},
            {"$set": {"status": "cancelled"}}
        )
        if result.modified_count > 0:
            return jsonify({"success": True, "message": "Pass deactivated"})
        return jsonify({"success": False, "message": "Pass not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500