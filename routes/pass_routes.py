from flask import Blueprint, request, jsonify, render_template, redirect, abort
from flask_login import login_required, current_user
from services.database import db
from services.pass_service import pass_service
from bson.objectid import ObjectId
from bson import json_util
from datetime import datetime
import json
import os
from functools import wraps

# Blueprint definition
pass_bp = Blueprint('pass', __name__, url_prefix='/pass')

# ============================================================================
# ROLE-BASED ACCESS CONTROL DECORATOR
# ============================================================================

def admin_required(f):
    """Decorator to require admin or super_admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect('/login')
        
        # Get user from database to check role
        user = db.users.find_one({"_id": ObjectId(current_user.id)})
        
        if not user:
            abort(403)
        
        user_role = user.get('role', 'user')
        
        # Allow only admin and super_admin
        if user_role not in ['admin', 'super_admin']:
            abort(403)  # Forbidden
        
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# PAGE ROUTES (UI) - Protected with admin_required
# ============================================================================

@pass_bp.route('/manage')
@login_required
@admin_required
def manage_passes():
    """Main management dashboard for passes - Admin Only"""
    return render_template('pass_management.html')

@pass_bp.route('/view')
@login_required
@admin_required
def view_page():
    """Shortcut to view all passes on the management dashboard - Admin Only"""
    return render_template('pass_management.html', active_tab='view')

@pass_bp.route('/generate')
@login_required
@admin_required
def generate_page():
    """Pass generation page - Admin Only"""
    return render_template('generate.html', active_tab='generate')

@pass_bp.route('/bulk_qr')
@login_required
@admin_required
def bulk_page():
    """Bulk generation tool page - Admin Only"""
    return render_template('bulk_qr.html')

# ============================================================================
# API ROUTES (LOGIC) - Protected with admin_required
# ============================================================================

@pass_bp.route('/api/generate', methods=['POST'])
@login_required
@admin_required
def generate_pass_simple():
    """
    Generate pass - supports both old and new format - Admin Only
    """
    try:
        data = request.json
        
        # Check if this is new format (with event_id) or old format (direct fields)
        if 'event_id' in data and data.get('event_id'):
            # NEW FORMAT - with event selection
            event_id = data.get('event_id')
            ticket_type = data.get('ticket_type', 'General')
            quantity = int(data.get('quantity', 1))
            
            # Get event
            event = db.events.find_one({"_id": ObjectId(event_id)})
            if not event:
                return jsonify({"success": False, "message": "Event not found"}), 404
            
            # Get user info for attendee name if not provided
            user = db.users.find_one({"_id": ObjectId(current_user.id)})
            attendee_name = data.get('name') or (user.get('name') if user else 'Guest')
            event_name = event.get('name')
            
            # Safe Date Handling
            raw_date = event.get('date')
            if not raw_date:
                event_date = 'Date TBD'
            elif isinstance(raw_date, datetime):
                event_date = raw_date.strftime('%B %d, %Y')
            else:
                event_date = str(raw_date)
            
            venue = event.get('venue', event.get('location', 'Venue TBD'))
            
        else:
            # OLD FORMAT - direct fields (backward compatible)
            attendee_name = data.get('name')
            ticket_type = data.get('ticketType', data.get('ticket_type', 'General'))
            event_name = data.get('eventName', 'Event')
            event_date = data.get('eventDate', 'Date TBD')
            venue = data.get('venue', 'Venue TBD')
            event_id = None
            quantity = 1
        
        # Validate required fields
        if not attendee_name:
            return jsonify({"success": False, "message": "Attendee name is required"}), 400
        
        # Generate pass(es)
        passes = []
        for i in range(quantity):
            # If multiple, append index to name
            name_to_use = attendee_name if quantity == 1 else f"{attendee_name} ({i+1})"
            
            result = pass_service.create_pass(
                attendee_name=name_to_use,
                ticket_type=ticket_type,
                event_name=event_name,
                event_date=event_date,
                venue=venue,
                event_id=event_id
            )
            
            if result.get('success'):
                passes.append(result)
        
        if len(passes) > 0:
            first_pass = passes[0]
            
            # Convert all passes to JSON-serializable format
            passes_json = json.loads(json_util.dumps(passes))
            
            return jsonify({
                "success": True,
                "serial_number": first_pass['serial_number'],
                "pass_url": first_pass.get('pass_url'),
                "count": len(passes),
                "passes": passes_json,  # Now properly serialized
                "message": f"Generated {len(passes)} pass(es) successfully"
            })
        else:
            return jsonify({"success": False, "message": "Failed to generate pass"}), 500
            
    except Exception as e:
        print(f"Error generating pass: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

@pass_bp.route('/api/bulk_generate', methods=['POST'])
@login_required
@admin_required
def bulk_generate():
    """Specific API for generating a batch of generic passes for an event - Admin Only"""
    try:
        data = request.json
        event_id = data.get('event_id')
        quantity = int(data.get('quantity', 1))
        prefix = data.get('prefix', 'Guest')
        ticket_type = data.get('ticket_type', 'General')

        event = db.events.find_one({"_id": ObjectId(event_id)})
        if not event:
            return jsonify({"success": False, "message": "Event not found"}), 404

        raw_date = event.get('date')
        event_date = raw_date.strftime('%B %d, %Y') if isinstance(raw_date, datetime) else str(raw_date or "Date TBD")
        
        passes_created = []
        for i in range(quantity):
            res = pass_service.create_pass(
                attendee_name=f"{prefix} #{i+1}",
                ticket_type=ticket_type,
                event_name=event.get('name'),
                event_date=event_date,
                venue=event.get('venue', 'Venue TBD'),
                event_id=event_id
            )
            if res.get('success'):
                passes_created.append(res['serial_number'])

        return jsonify({
            "success": True, 
            "message": f"Successfully batch generated {len(passes_created)} passes.",
            "count": len(passes_created)
        })
    except Exception as e:
        print(f"Error in bulk_generate: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@pass_bp.route('/api/list', methods=['GET'])
@login_required
@admin_required
def list_passes():
    """Get all passes with pagination and sorting - Admin Only"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        skip = (page - 1) * per_page
        
        # Use the service method which generates fresh presigned URLs
        passes = pass_service.get_all_passes(skip=skip, limit=per_page)
        total = db.passes.count_documents({})
        
        passes_json = json.loads(json_util.dumps(passes))
        
        return jsonify({
            "success": True,
            "passes": passes_json,
            "total": total,
            "page": page,
            "total_pages": (total + per_page - 1) // per_page
        })
    except Exception as e:
        print(f"Error listing passes: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@pass_bp.route('/api/stats', methods=['GET'])
@login_required
@admin_required
def get_pass_stats():
    """Get summarized pass statistics for the dashboard - Admin Only"""
    try:
        total = db.passes.count_documents({})
        scanned = db.passes.count_documents({"scanned": True})
        return jsonify({
            "success": True, 
            "stats": {
                "total_issued": total,
                "total_scanned": scanned,
                "attendance_rate": round((scanned/total)*100, 1) if total > 0 else 0
            }
        })
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@pass_bp.route('/download/<serial_number>')
def download_pass(serial_number):
    """Generate a fresh presigned download URL and redirect - Public for pass holders"""
    try:
        # Get fresh presigned download URL (forces download, not display)
        download_url = pass_service.get_pass_download_url(serial_number)
        
        if not download_url:
            return jsonify({"success": False, "message": "Pass not found or unable to generate download URL"}), 404
        
        # Redirect to the presigned S3 URL with download disposition
        return redirect(download_url)
        
    except Exception as e:
        print(f"Error downloading pass: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@pass_bp.route('/api/get/<serial_number>')
@login_required
@admin_required
def get_pass_api(serial_number):
    """Get pass details with fresh presigned URL for display - Admin Only"""
    try:
        pass_doc = pass_service.get_pass(serial_number)
        
        if not pass_doc:
            return jsonify({"success": False, "message": "Pass not found"}), 404
        
        # Convert to JSON-serializable format
        pass_json = json.loads(json_util.dumps(pass_doc))
        
        return jsonify({
            "success": True,
            "pass": pass_json
        })
    except Exception as e:
        print(f"Error getting pass: {e}")
        return jsonify({"success": False, "message": str(e)}), 500