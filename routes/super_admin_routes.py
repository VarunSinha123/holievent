from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from services.auth_service import auth_service
from services.event_service import event_service
from services.bouncer_service import bouncer_service
from services.audit_service import audit_service
from services.database import db
from bson import json_util
from bson.objectid import ObjectId
import json
from datetime import datetime, timedelta

super_admin_bp = Blueprint('super_admin', __name__)

def super_admin_required(f):
    """Decorator for super admin only routes"""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'super_admin':
            return "Access Denied - Super Admin access required", 403
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# DASHBOARD & MAIN PAGES
# ============================================================================

@super_admin_bp.route('/dashboard')
@super_admin_required
def dashboard():
    """Super Admin dashboard"""
    return render_template('super_admin_dashboard.html')

@super_admin_bp.route('/admins')
@super_admin_required
def admins_page():
    """Admin management page"""
    try:
        return render_template('admin_management.html')
    except Exception as e:
        return f"Template not found: admin_management.html - {str(e)}", 404

@super_admin_bp.route('/create-admin')
@super_admin_required
def create_admin_page():
    """Create admin page"""
    try:
        return render_template('create_admin.html')
    except Exception as e:
        return redirect(url_for('super_admin.admins_page'))


@super_admin_bp.route('/bouncer')
@super_admin_required
def bouncers_page():
    """Bouncer management page"""
    try:
        return render_template('bouncer_management.html')
    except Exception as e:
        return f"Template not found: bouncer_management.html - {str(e)}", 404

@super_admin_bp.route('/create-bouncer')
@super_admin_required
def create_bouncer_page():
    """Create bouncer page"""
    try:
        return render_template('create_bouncer.html')
    except Exception as e:
        return redirect(url_for('super_admin.bouncers_page'))


@super_admin_bp.route('/audit-logs')
@super_admin_required
def audit_logs_page():
    """Audit logs page"""
    return render_template('audit_logs.html')

@super_admin_bp.route('/bulk-qr')
@super_admin_required
def bulk_qr_page():
    """Bulk QR generation page"""
    try:
        return render_template('bulk_qr.html')
    except Exception as e:
        return f"Template not found: bulk_qr.html - {str(e)}", 404

# ============================================================================
# API ENDPOINTS - STATISTICS
# ============================================================================

@super_admin_bp.route('/api/system-stats', methods=['GET'])
@super_admin_required
def get_system_stats():
    """Get core system-wide statistics (User, Event, Pass, and Bouncer stats)"""
    try:
        # User statistics by role
        user_stats = {
            "users": db.users.count_documents({"role": "user"}),
            "admins": db.users.count_documents({"role": "admin"}),
            "bouncers": db.users.count_documents({"role": "bouncer"}),
            "super_admins": db.users.count_documents({"role": "super_admin"}),
            "total": db.users.count_documents({})
        }
        
        # Event statistics
        event_stats = {
            "total": db.events.count_documents({}),
            "active": db.events.count_documents({"is_active": True}),
            "inactive": db.events.count_documents({"is_active": False})
        }
        
        # Pass statistics  
        pass_stats = {
            "total": db.passes.count_documents({}),
            "valid": db.passes.count_documents({"status": "valid"}),
            "cancelled": db.passes.count_documents({"status": "cancelled"}),
            "scanned": db.scans.count_documents({})
        }
        
        # Activity statistics (last 7 days)
        seven_days_ago = datetime.now() - timedelta(days=7)
        today_start = datetime.combine(datetime.today(), datetime.min.time())
        
        activity_stats = {
            "new_users": db.users.count_documents({
                "created_at": {"$gte": today_start}
            }),
            "new_passes": db.passes.count_documents({
                "issued_at": {"$gte": seven_days_ago}
            })
        }
        
        # Bouncer activity
        bouncer_stats = {
            "total_bouncers": db.users.count_documents({"role": "bouncer"}),
            "active_assignments": db.bouncers.count_documents({"status": "active"}),
            "total_scans": db.scans.count_documents({}),
            "scans_today": db.scans.count_documents({
                "scanned_at": {"$gte": today_start}
            })
        }
        
        stats = {
            "users": user_stats,
            "events": event_stats,
            "passes": pass_stats,
            "activity": activity_stats,
            "bouncers": bouncer_stats,
            "timestamp": datetime.now()
        }
        
        stats_json = json.loads(json_util.dumps(stats))
        
        return jsonify({
            "success": True,
            "stats": stats_json
        })
        
    except Exception as e:
        print(f"Error getting system stats: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# ============================================================================
# API ENDPOINTS - USER MANAGEMENT (OPTIMIZED)
# ============================================================================

@super_admin_bp.route('/api/users/all', methods=['GET'])
@super_admin_required
def get_all_users():
    """Get all users (admins, bouncers, regular users) with pagination - OPTIMIZED"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        search = request.args.get('search', '')
        role_filter = request.args.get('role', '')
        
        skip = (page - 1) * per_page
        
        # Build match stage
        match_stage = {}
        if role_filter:
            match_stage['role'] = role_filter
        
        if search:
            match_stage['$or'] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}}
            ]
        
        # Use aggregation pipeline for better performance
        pipeline = [
            {"$match": match_stage},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": per_page},
            {
                "$lookup": {
                    "from": "orders",
                    "localField": "_id",
                    "foreignField": "user_id",
                    "as": "orders_data"
                }
            },
            {
                "$lookup": {
                    "from": "passes",
                    "localField": "_id",
                    "foreignField": "user_id",
                    "as": "passes_data"
                }
            },
            {
                "$addFields": {
                    "order_count": {"$size": "$orders_data"},
                    "pass_count": {"$size": "$passes_data"}
                }
            },
            {
                "$project": {
                    "password": 0,
                    "orders_data": 0,
                    "passes_data": 0
                }
            }
        ]
        
        users = list(db.users.aggregate(pipeline))
        total = db.users.count_documents(match_stage)
        users_json = json.loads(json_util.dumps(users))
        
        return jsonify({
            "success": True,
            "users": users_json,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/user', methods=['GET'])
@super_admin_required
def get_users():
    """Get all regular users with pagination"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        search = request.args.get('search', '')
        
        skip = (page - 1) * per_page
        
        query = {"role": "user"}
        if search:
            query['$or'] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}}
            ]
        
        users = list(db.users.find(query, {"password": 0})
                    .sort("created_at", -1)
                    .skip(skip)
                    .limit(per_page))
        
        for user in users:
            user['order_count'] = db.orders.count_documents({"user_id": user['_id']})
            user['pass_count'] = db.passes.count_documents({"user_id": user['_id']})
        
        total = db.users.count_documents(query)
        users_json = json.loads(json_util.dumps(users))
        
        return jsonify({
            "success": True,
            "users": users_json,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/user/<user_id>/toggle', methods=['POST'])
@super_admin_required
def toggle_user_status(user_id):
    """Enable/disable user account (works for all roles except super_admin)"""
    try:
        data = request.json
        is_active = data.get('is_active', True)
        
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        if user.get('role') == 'super_admin':
            return jsonify({"success": False, "message": "Cannot modify super admin accounts"}), 403
        
        result = db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": is_active}}
        )
        
        if result.modified_count > 0:
            audit_service.log(
                action_type="user_status_changed",
                performed_by=current_user.id,
                details=f"{user.get('role', 'User')} '{user.get('name')}' {'activated' if is_active else 'deactivated'}",
                target_user=user_id
            )
            return jsonify({"success": True, "message": f"User {'activated' if is_active else 'deactivated'}"})
        
        return jsonify({"success": False, "message": "No changes made"}), 404
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/user/<user_id>/delete', methods=['DELETE'])
@super_admin_required
def delete_user(user_id):
    """Delete user account (works for all roles except super_admin)"""
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        if user.get('role') == 'super_admin':
            return jsonify({"success": False, "message": "Cannot delete super admin accounts"}), 403
        
        if str(user['_id']) == current_user.id:
            return jsonify({"success": False, "message": "Cannot delete your own account"}), 403
        
        if user.get('role') == 'bouncer':
            db.bouncers.delete_many({"user_id": user['_id']})
        
        db.users.delete_one({"_id": ObjectId(user_id)})
        
        audit_service.log(
            action_type="user_deleted",
            performed_by=current_user.id,
            details=f"{user.get('role', 'User')} '{user.get('name')}' deleted",
            target_user=user_id
        )
        
        return jsonify({"success": True, "message": "User deleted successfully"})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# API ENDPOINTS - ADMIN MANAGEMENT
# ============================================================================

@super_admin_bp.route('/api/admins', methods=['GET'])
@super_admin_required
def get_admins():
    """Get all admin users"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        skip = (page - 1) * per_page
        
        admins = list(db.users.find({"role": "admin"}, {"password": 0})
                     .sort("created_at", -1)
                     .skip(skip)
                     .limit(per_page))
        
        for admin in admins:
            admin['events_created'] = db.events.count_documents({"created_by": str(admin['_id'])})
            admin['last_login'] = admin.get('last_login', admin.get('created_at'))
        
        total = db.users.count_documents({"role": "admin"})
        admins_json = json.loads(json_util.dumps(admins))
        
        return jsonify({
            "success": True,
            "admins": admins_json,
            "total": total,
            "page": page,
            "per_page": per_page
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/admins/create', methods=['POST'])
@super_admin_required
def create_admin():
    """Create new admin user"""
    try:
        data = request.json
        result = auth_service.register_user(
            email=data.get('email'),
            password=data.get('password'),
            name=data.get('name'),
            phone=data.get('phone', ''),
            role='admin'
        )
        
        if result.get('success'):
            audit_service.log(
                action_type="admin_created",
                performed_by=current_user.id,
                details=f"Admin '{data.get('name')}' created with email {data.get('email')}",
                target_user=result.get('user_id')
            )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/admins/<admin_id>/remove', methods=['DELETE'])
@super_admin_required
def remove_admin(admin_id):
    """Remove admin user (change role to user)"""
    try:
        if admin_id == current_user.id:
            return jsonify({"success": False, "message": "Cannot remove yourself"}), 400
        
        admin = db.users.find_one({"_id": ObjectId(admin_id), "role": "admin"})
        if not admin:
            return jsonify({"success": False, "message": "Admin not found"}), 404
        
        result = db.users.update_one(
            {"_id": ObjectId(admin_id), "role": "admin"},
            {"$set": {"role": "user"}}
        )
        
        if result.modified_count > 0:
            audit_service.log(
                action_type="admin_removed",
                performed_by=current_user.id,
                details=f"Admin privileges revoked for '{admin.get('name')}' ({admin.get('email')})",
                target_user=admin_id
            )
            return jsonify({"success": True, "message": "Admin removed successfully"})
        
        return jsonify({"success": False, "message": "Admin not found"}), 404
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# API ENDPOINTS - BOUNCER MANAGEMENT
# ============================================================================

@super_admin_bp.route('/api/bouncer', methods=['GET'])
@super_admin_required
def get_all_bouncers():
    """Get all bouncer assignments with pagination"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        event_id = request.args.get('event_id')
        
        if event_id in [None, '', 'null', 'undefined']:
            event_id = None
        
        skip = (page - 1) * per_page
        bouncers = bouncer_service.get_all_bouncers(event_id=event_id, skip=skip, limit=per_page)
        total = bouncer_service.get_total_bouncers(event_id=event_id)
        
        bouncers_json = json.loads(json_util.dumps(bouncers))
        
        return jsonify({
            "success": True,
            "bouncers": bouncers_json,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/bouncer/user', methods=['GET'])
@super_admin_required
def get_bouncer_users():
    """Get all users with bouncer role"""
    try:
        bouncers = list(db.users.find({"role": "bouncer"}, {"password": 0}).sort("created_at", -1))
        
        for bouncer in bouncers:
            bouncer['assignment_count'] = db.bouncers.count_documents({"user_id": bouncer['_id']})
            bouncer['total_scans'] = db.scans.count_documents({"bouncer_id": str(bouncer['_id'])})
        
        bouncers_json = json.loads(json_util.dumps(bouncers))
        
        return jsonify({
            "success": True,
            "bouncers": bouncers_json,
            "total": len(bouncers)
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/bouncer/create', methods=['POST'])
@super_admin_required
def create_bouncer():
    """Create new bouncer account"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        password = data.get('password', '').strip()
        event_id = data.get('event_id')
        
        if not name or not email or not password or not phone:
            return jsonify({"success": False, "message": "Required fields: name, email, phone, password"}), 400
        
        result = bouncer_service.create_bouncer(
            name=name, email=email, password=password, phone=phone,
            event_id=event_id, assigned_by=str(current_user.id)
        )
        
        if result.get('success'):
            audit_service.log(
                action_type="bouncer_created",
                performed_by=current_user.id,
                details=f"Bouncer '{name}' created with email {email}",
                target_user=result.get('bouncer_id')
            )
        
        return jsonify(result), 201 if result['success'] else 400
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@super_admin_bp.route('/api/bouncer/<bouncer_id>/delete', methods=['DELETE'])
@super_admin_required
def delete_bouncer_assignment(bouncer_id):
    """Delete bouncer assignment"""
    try:
        success = bouncer_service.remove_bouncer(bouncer_id)
        if success:
            audit_service.log(
                action_type="bouncer_assignment_deleted",
                performed_by=current_user.id,
                details=f"Bouncer assignment {bouncer_id} removed"
            )
        return jsonify({"success": success, "message": "Bouncer assignment removed"}), 200 if success else 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# API ENDPOINTS - EVENT CONTROL
# ============================================================================

@super_admin_bp.route('/api/event/global-control', methods=['POST'])
@super_admin_required
def global_event_control():
    """Activate/deactivate all events"""
    try:
        data = request.json
        action = data.get('action')
        
        if action == 'activate_all':
            result = db.events.update_many({}, {"$set": {"is_active": True}})
            message = f"Activated {result.modified_count} events"
            action_type = "events_activated_all"
        elif action == 'deactivate_all':
            result = db.events.update_many({}, {"$set": {"is_active": False}})
            message = f"Deactivated {result.modified_count} events"
            action_type = "events_deactivated_all"
        else:
            return jsonify({"success": False, "message": "Invalid action"}), 400
        
        audit_service.log(action_type=action_type, performed_by=current_user.id, details=message)
        return jsonify({"success": True, "message": message})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# API ENDPOINTS - AUDIT LOGS
# ============================================================================

@super_admin_bp.route('/api/audit-logs', methods=['GET'])
@super_admin_required
def get_audit_logs():
    """Get system audit logs"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        action_type = request.args.get('action_type')
        
        skip = (page - 1) * per_page
        query = {}
        if action_type:
            query['action_type'] = action_type
        
        logs = list(db.audit_logs.find(query).sort("timestamp", -1).skip(skip).limit(per_page))
        
        for log in logs:
            if 'performed_by' in log:
                try:
                    p_id = ObjectId(log['performed_by']) if isinstance(log['performed_by'], str) else log['performed_by']
                    user = db.users.find_one({"_id": p_id}, {"password": 0})
                    if user:
                        log['performed_by_name'] = user['name']
                        log['performed_by_email'] = user['email']
                except:
                    pass
        
        total = db.audit_logs.count_documents(query)
        logs_json = json.loads(json_util.dumps(logs))
        
        return jsonify({
            "success": True,
            "logs": logs_json,
            "total": total,
            "page": page,
            "per_page": per_page
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# PASSWORD MANAGEMENT
# ============================================================================
    
@super_admin_bp.route('/api/change-password', methods=['POST'])
@super_admin_required
def change_password():
    """Change super admin password"""
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
                details=f"Super Admin {current_user.name} changed their password"
            )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
