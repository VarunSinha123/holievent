from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from services.event_service import event_service
from services.audit_service import audit_service
from services.database import db
from bson import json_util
from bson.objectid import ObjectId
import json
import traceback
from functools import wraps

event_bp = Blueprint('event', __name__)

# ============================================================================
# ROLE-BASED ACCESS CONTROL DECORATOR
# ============================================================================

def admin_required(f):
    """Decorator to require admin or superadmin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                "success": False,
                "message": "Authentication required"
            }), 401
        
        # Debug: Print user role
        print(f"[DEBUG] User role: '{current_user.role}' (type: {type(current_user.role)})")
        
        # Check role - case insensitive and handle variations
        user_role = str(current_user.role).lower().strip()
        allowed_roles = ['admin', 'superadmin', 'super-admin', 'super_admin']
        
        if user_role not in allowed_roles:
            print(f"[DEBUG] Access denied for role: {user_role}")
            return jsonify({
                "success": False,
                "message": "Access denied. Admin privileges required."
            }), 403
        
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# PAGE ROUTES
# ============================================================================

@event_bp.route('/')
@login_required
def events_page():
    """Events management page - Only admin/superadmin can access"""
    # Debug: Print user role
    print(f"[DEBUG] events_page - User role: '{current_user.role}' (type: {type(current_user.role)})")
    
    user_role = str(current_user.role).lower().strip()
    allowed_roles = ['admin', 'superadmin', 'super-admin', 'super_admin']
    
    if user_role not in allowed_roles:
        flash('Access denied. Admin privileges required.', 'error')
        abort(403)
    return render_template('event_management.html')

# ============================================================================
# EVENT API ENDPOINTS (ADMIN ONLY)
# ============================================================================

@event_bp.route('/api/create', methods=['POST'])
@login_required
@admin_required
def create_event():
    """Create new event - Admin only"""
    try:
        data = request.json
        print(f"[DEBUG] Received data: {data}")
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({
                "success": False,
                "message": "Event name is required"
            }), 400
        
        if not data.get('date'):
            return jsonify({
                "success": False,
                "message": "Event date is required"
            }), 400
            
        if not data.get('venue'):
            return jsonify({
                "success": False,
                "message": "Event venue is required"
            }), 400
        
        if not data.get('startTime'):
            return jsonify({
                "success": False,
                "message": "Start time is required"
            }), 400
            
        if not data.get('endTime'):
            return jsonify({
                "success": False,
                "message": "End time is required"
            }), 400
        
        print(f"[DEBUG] Creating event with data: {data}")
        
        result = event_service.create_event(
            name=data.get('name'),
            description=data.get('description', ''),
            date=data.get('date'),
            venue=data.get('venue'),
            start_time=data.get('startTime'),
            end_time=data.get('endTime'),
            organizer=data.get('organizer', ''),
            ticket_types=data.get('ticketTypes', []),
            created_by=str(current_user.id)
        )
        
        print(f"[DEBUG] Service result: {result}")
        
        if result.get('success'):
            # LOG EVENT CREATION
            audit_service.log(
                action_type="event_created",
                performed_by=current_user.id,
                details=f"Event '{data.get('name')}' created for {data.get('date')}",
                metadata={"event_id": result.get('event_id')}
            )
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in create_event: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": f"Error creating event: {error_msg}"
        }), 500

@event_bp.route('/api/list', methods=['GET'])
@login_required
@admin_required
def list_events():
    """Get all events with pagination - Admin only"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        skip = (page - 1) * per_page
        events = event_service.get_all_events(skip=skip, limit=per_page)
        total = event_service.get_total_events()
        
        print(f"[DEBUG] Found {len(events)} events, total: {total}")
        
        events_json = json.loads(json_util.dumps(events))
        
        return jsonify({
            "success": True,
            "events": events_json,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in list_events: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": f"Error listing events: {error_msg}"
        }), 500

@event_bp.route('/api/get/<event_id>', methods=['GET'])
@login_required
@admin_required
def get_event(event_id):
    """Get specific event by ID - Admin only"""
    try:
        print(f"[DEBUG] Getting event: {event_id}")
        event = event_service.get_event(event_id)
        
        if event:
            event_json = json.loads(json_util.dumps(event))
            return jsonify({
                "success": True,
                "event": event_json
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Event not found"
            }), 404
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in get_event: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": f"Error getting event: {error_msg}"
        }), 500

@event_bp.route('/api/update/<event_id>', methods=['PUT'])
@login_required
@admin_required
def update_event(event_id):
    """Update event - Admin only"""
    try:
        data = request.json
        print(f"[DEBUG] Updating event {event_id} with data: {data}")
        
        result = event_service.update_event(
            event_id=event_id,
            name=data.get('name'),
            description=data.get('description'),
            date=data.get('date'),
            venue=data.get('venue'),
            start_time=data.get('startTime'),
            end_time=data.get('endTime'),
            organizer=data.get('organizer'),
            ticket_types=data.get('ticketTypes')
        )
        
        print(f"[DEBUG] Update result: {result}")
        
        if result.get('success'):
            # LOG EVENT UPDATE
            audit_service.log(
                action_type="event_updated",
                performed_by=current_user.id,
                details=f"Event details updated for '{data.get('name')}'",
                metadata={"event_id": event_id}
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in update_event: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": f"Error updating event: {error_msg}"
        }), 500

@event_bp.route('/api/delete/<event_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_event(event_id):
    """Delete event - Admin only"""
    try:
        print(f"[DEBUG] Deleting event: {event_id}")
        
        # Get event details before deletion for audit log
        event = event_service.get_event(event_id)
        if not event:
            return jsonify({
                "success": False,
                "message": "Event not found"
            }), 404
        
        result = event_service.delete_event(event_id)
        
        if result.get('success'):
            # LOG EVENT DELETION
            audit_service.log(
                action_type="event_deleted",
                performed_by=current_user.id,
                details=f"Event '{event.get('name')}' deleted"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in delete_event: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": f"Error deleting event: {error_msg}"
        }), 500

@event_bp.route('/api/toggle/<event_id>', methods=['POST'])
@login_required
@admin_required
def toggle_event_status(event_id):
    """Toggle event active status - Admin only"""
    try:
        data = request.json
        active = data.get('active', True)
        
        print(f"[DEBUG] Toggling event {event_id} to active={active}")
        
        # Get event details for audit log
        event = event_service.get_event(event_id)
        if not event:
            return jsonify({
                "success": False,
                "message": "Event not found"
            }), 404
        
        success = event_service.toggle_event_status(event_id, active)
        
        if success:
            action = "activated" if active else "deactivated"
            # LOG STATUS CHANGE
            audit_service.log(
                action_type=f"event_{action}",
                performed_by=current_user.id,
                details=f"Event '{event.get('name')}' {action}",
                metadata={"event_id": event_id}
            )
            return jsonify({
                "success": True,
                "message": f"Event {action} successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Failed to update event status"
            }), 400
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in toggle_event_status: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": f"Error toggling status: {error_msg}"
        }), 500

# ============================================================================
# TICKET TYPE API ENDPOINTS (ADMIN ONLY)
# ============================================================================

@event_bp.route('/api/ticket-type/<event_id>', methods=['POST'])
@login_required
@admin_required
def add_ticket_type(event_id):
    """Add ticket type to event - Admin only"""
    try:
        data = request.json
        
        result = event_service.add_ticket_type(
            event_id=event_id,
            ticket_name=data.get('name'),
            price=data.get('price'),
            description=data.get('description', ''),
            total_available=data.get('total_available', 100),
            features=data.get('features', [])
        )
        
        if result.get('success'):
            # LOG TICKET TYPE ADDITION
            audit_service.log(
                action_type="event_ticket_added",
                performed_by=current_user.id,
                details=f"Ticket type '{data.get('name')}' added to event ID {event_id}",
                metadata={"event_id": event_id, "ticket_id": result.get('ticket_id')}
            )
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in add_ticket_type: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@event_bp.route('/api/ticket-type/<event_id>/<ticket_id>', methods=['PUT'])
@login_required
@admin_required
def update_ticket_type(event_id, ticket_id):
    """Update ticket type - Admin only"""
    try:
        data = request.json
        
        result = event_service.update_ticket_type(event_id, ticket_id, data)
        
        if result.get('success'):
            # LOG TICKET TYPE UPDATE
            audit_service.log(
                action_type="event_ticket_updated",
                performed_by=current_user.id,
                details=f"Ticket type updated for event ID {event_id}",
                metadata={"event_id": event_id, "ticket_id": ticket_id}
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in update_ticket_type: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@event_bp.route('/api/ticket-type/<event_id>/<ticket_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_ticket_type(event_id, ticket_id):
    """Delete ticket type - Admin only"""
    try:
        result = event_service.delete_ticket_type(event_id, ticket_id)
        
        if result.get('success'):
            # LOG TICKET TYPE DELETION
            audit_service.log(
                action_type="event_ticket_deleted",
                performed_by=current_user.id,
                details=f"Ticket type deleted from event ID {event_id}",
                metadata={"event_id": event_id, "ticket_id": ticket_id}
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in delete_ticket_type: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@event_bp.route('/api/statistics/<event_id>', methods=['GET'])
@login_required
@admin_required
def get_event_statistics(event_id):
    """Get event statistics - Admin only"""
    try:
        stats = event_service.get_event_statistics(event_id)
        
        if stats:
            return jsonify({
                "success": True,
                "statistics": stats
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Event not found"
            }), 404
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in get_event_statistics: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": f"Error getting statistics: {error_msg}"
        }), 500

# ============================================================================
# PUBLIC-FACING API ENDPOINTS (NO AUTH REQUIRED)
# ============================================================================

@event_bp.route('/api/active', methods=['GET'])
def get_active_event():
    """Get currently active event - Public endpoint for all users"""
    try:
        event = event_service.get_active_event()
        
        if event:
            event_json = json.loads(json_util.dumps(event))
            
            # Filter to only show public information
            public_event = {
                "_id": event_json.get("_id"),
                "name": event_json.get("name"),
                "description": event_json.get("description"),
                "date": event_json.get("date"),
                "venue": event_json.get("venue"),
                "start_time": event_json.get("start_time"),
                "end_time": event_json.get("end_time"),
                "organizer": event_json.get("organizer"),
                "ticket_types": []
            }
            
            # Include only ticket name, price, and availability
            for ticket in event_json.get("ticket_types", []):
                public_event["ticket_types"].append({
                    "id": ticket.get("id"),
                    "name": ticket.get("name"),
                    "price": ticket.get("price"),
                    "description": ticket.get("description"),
                    "available": ticket.get("available", 0),
                    "features": ticket.get("features", [])
                })
            
            return jsonify({
                "success": True,
                "event": public_event
            }), 200
        else:
            return jsonify({
                "success": True,
                "event": None,
                "message": "No active event at this time"
            }), 200
            
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in get_active_event: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@event_bp.route('/api/public/events', methods=['GET'])
def get_public_events():
    """Get all active events - Public endpoint for normal users"""
    try:
        # Get all events
        all_events = event_service.get_all_events(skip=0, limit=100)
        
        print(f"[DEBUG] Total events in database: {len(all_events)}")
        
        # Filter only active events and show only public info
        public_events = []
        for event in all_events:
            is_active = event.get('active', True)  # Default to True if not set
            print(f"[DEBUG] Event '{event.get('name')}' - Active: {is_active}")
            
            if is_active:
                event_json = json.loads(json_util.dumps(event))
                public_event = {
                    "_id": event_json.get("_id"),
                    "name": event_json.get("name"),
                    "description": event_json.get("description"),
                    "date": event_json.get("date"),
                    "venue": event_json.get("venue"),
                    "start_time": event_json.get("start_time"),
                    "end_time": event_json.get("end_time"),
                    "organizer": event_json.get("organizer"),
                    "active": event_json.get("active", True),
                    "ticket_types": []
                }
                
                # Include ticket info with correct field names for frontend
                for ticket in event_json.get("ticket_types", []):
                    # Check if ticket is active (if that field exists)
                    ticket_active = ticket.get("is_active", True)
                    
                    # Calculate available tickets
                    total_available = ticket.get("total_available", ticket.get("available", 100))
                    tickets_sold = ticket.get("tickets_sold", 0)
                    
                    public_event["ticket_types"].append({
                        "ticket_id": ticket.get("id"),  # Changed from "id" to "ticket_id"
                        "name": ticket.get("name"),
                        "price": ticket.get("price"),
                        "description": ticket.get("description"),
                        "total_available": total_available,  # Changed from "available"
                        "tickets_sold": tickets_sold,  # Added tickets_sold
                        "is_active": ticket_active,  # Added is_active flag
                        "features": ticket.get("features", [])
                    })
                
                public_events.append(public_event)
        
        print(f"[DEBUG] Active events found: {len(public_events)}")
        
        return jsonify({
            "success": True,
            "events": public_events,
            "total": len(public_events)
        }), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Exception in get_public_events: {error_msg}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
        
