from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from services.event_service import event_service
from services.pass_service import pass_service
from services.database import db
from bson import json_util
from bson.objectid import ObjectId
import json
from datetime import datetime

user_bp = Blueprint('user', __name__)

@user_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard page"""
    if current_user.role != 'user':
        return "Access Denied - User access only", 403
    return render_template('user_dashboard.html')

@user_bp.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    """Get user profile with statistics"""
    if current_user.role != 'user':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        # Get user data
        user_data = db.users.find_one({"_id": ObjectId(current_user.id)}, {"password": 0})
        
        # Get statistics
        total_orders = db.orders.count_documents({
            "user_id": ObjectId(current_user.id)
        })
        
        total_passes = db.passes.count_documents({
            "user_id": ObjectId(current_user.id)
        })
        
        total_spent = list(db.orders.aggregate([
            {"$match": {
                "user_id": ObjectId(current_user.id),
                "status": "paid"
            }},
            {"$group": {
                "_id": None,
                "total": {"$sum": "$total_amount"}
            }}
        ]))
        
        user_json = json.loads(json_util.dumps(user_data))
        user_json['statistics'] = {
            "total_orders": total_orders,
            "total_passes": total_passes,
            "total_spent": total_spent[0]['total'] if total_spent else 0
        }
        
        return jsonify({
            "success": True,
            "user": user_json
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@user_bp.route('/api/events', methods=['GET'])
@login_required
def get_available_events():
    """Get available events for purchase"""
    if current_user.role != 'user':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        events = event_service.get_all_events(active_only=True)
        events_json = json.loads(json_util.dumps(events))
        
        return jsonify({
            "success": True,
            "events": events_json
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@user_bp.route('/api/orders', methods=['GET'])
@login_required
def get_my_orders():
    """Get user's orders with passes using direct DB queries"""
    if current_user.role != 'user':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        skip = (page - 1) * per_page
        
        # Query orders directly from database
        orders_cursor = db.orders.find({"user_id": ObjectId(current_user.id)}) \
                                 .sort("created_at", -1) \
                                 .skip(skip) \
                                 .limit(per_page)
        
        orders = list(orders_cursor)
        
        # Enrich orders with pass details
        for order in orders:
            if order.get('passes_generated') and order.get('pass_serial_numbers'):
                passes = []
                for serial in order['pass_serial_numbers']:
                    pass_doc = pass_service.get_pass(serial)
                    if pass_doc:
                        passes.append(pass_doc)
                order['passes'] = passes
        
        orders_json = json.loads(json_util.dumps(orders))
        total = db.orders.count_documents({"user_id": ObjectId(current_user.id)})
        
        return jsonify({
            "success": True,
            "orders": orders_json,
            "total": total,
            "page": page,
            "per_page": per_page
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@user_bp.route('/api/passes', methods=['GET'])
@login_required
def get_my_passes():
    """Get all passes for current user"""
    if current_user.role != 'user':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        passes = list(db.passes.find({
            "user_id": ObjectId(current_user.id)
        }).sort("issued_at", -1))
        
        # Generate fresh presigned URLs
        from services.s3_service import s3_service
        for pass_doc in passes:
            if 's3_key' in pass_doc:
                pass_doc['pass_url'] = s3_service.generate_presigned_url(pass_doc['s3_key'])
        
        passes_json = json.loads(json_util.dumps(passes))
        
        return jsonify({
            "success": True,
            "passes": passes_json
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500