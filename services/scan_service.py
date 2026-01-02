from datetime import datetime
from services.database import db
from bson.objectid import ObjectId

class ScanService:
    """Service for managing pass scans - simplified to use serial_number only"""
    
    def scan_pass(self, serial_number, event_id, bouncer_id=None, scanned_by=None):
        """
        Scan and verify a pass for a specific event based on serial_number only
        Updates BOTH passes and qr_codes collections for bulk-generated passes
        No order validation required - pass validity is determined by the pass document itself
        """
        try:
            # Normalize serial number
            sn_upper = serial_number.strip().upper()
            
            # 1. Find the pass document by serial number and event
            pass_doc = db.passes.find_one({
                "serial_number": sn_upper,
                "event_id": ObjectId(event_id)
            })
            
            if not pass_doc:
                return {
                    "success": False,
                    "status": "not_found",
                    "message": "Invalid Pass: Ticket not found for this event",
                    "serial_number": serial_number
                }
            
            # 2. Check pass validity status
            pass_status = pass_doc.get('status', 'valid')
            if pass_status not in ['valid', 'active']:
                return {
                    "success": False,
                    "status": "invalid",
                    "message": f"Pass status is '{pass_status}' - Entry Denied",
                    "pass_info": {
                        "serial_number": sn_upper,
                        "holder_name": pass_doc.get('attendee_name') or pass_doc.get('user_name', 'Unknown'),
                        "ticket_type": pass_doc.get('ticket_type', 'Regular')
                    }
                }
            
            # 3. Double-Scan Protection
            is_scanned = pass_doc.get('scanned') is True or pass_status == 'scanned'
            if is_scanned:
                return {
                    "success": False,
                    "status": "already_scanned",
                    "message": "Already Scanned",
                    "pass_info": {
                        "serial_number": sn_upper,
                        "holder_name": pass_doc.get('attendee_name') or pass_doc.get('user_name', 'Unknown'),
                        "ticket_type": pass_doc.get('ticket_type', 'Regular'),
                        "scanned_at": pass_doc.get('scanned_at'),
                        "scanned_by": pass_doc.get('scanned_by_name', 'Unknown')
                    }
                }
            
            # 4. Success - Commit Scan to BOTH collections
            scanned_at = datetime.now()
            scanned_by_name = "System"

            if scanned_by:
                user = db.users.find_one({"_id": ObjectId(scanned_by)})
                if user:
                    scanned_by_name = user.get('name', 'Bouncer')

            # UPDATE PASSES COLLECTION (Primary)
            db.passes.update_one(
                {"_id": pass_doc['_id']},
                {"$set": {
                    "scanned": True, 
                    "status": "scanned",
                    "scanned_at": scanned_at,
                    "scanned_by": ObjectId(scanned_by) if scanned_by else None,
                    "scanned_by_name": scanned_by_name
                }}
            )
            
            # UPDATE QR_CODES COLLECTION (if this was a bulk-generated pass)
            is_bulk_generated = pass_doc.get('is_bulk_generated', False)
            if is_bulk_generated:
                try:
                    db.qr_codes.update_one(
                        {"serial_number": sn_upper},
                        {"$set": {
                            "used": True,
                            "used_at": scanned_at,
                            "scanned_by": ObjectId(scanned_by) if scanned_by else None,
                            "scanned_by_name": scanned_by_name
                        }}
                    )
                except Exception as qr_update_error:
                    print(f"Warning: Failed to update qr_codes collection: {qr_update_error}")
                    # Continue - pass was scanned successfully, qr_codes is secondary
            
            # Log scan event in scans collection
            scan_doc = {
                "pass_id": pass_doc['_id'],
                "serial_number": sn_upper,
                "event_id": ObjectId(event_id),
                "bouncer_id": ObjectId(bouncer_id) if bouncer_id else None,
                "scanned_by": ObjectId(scanned_by) if scanned_by else None,
                "scanned_at": scanned_at,
                "status": "valid",
                "attendee_name": pass_doc.get('attendee_name') or pass_doc.get('user_name', 'Unknown'),
                "ticket_type": pass_doc.get('ticket_type', 'Regular'),
                "is_bulk_generated": is_bulk_generated
            }
            
            # Add order_id to scan log if it exists (for reference only, not validation)
            if pass_doc.get('order_id'):
                scan_doc['order_id'] = pass_doc['order_id']
            
            db.scans.insert_one(scan_doc)
            
            # Update bouncer stats
            if bouncer_id:
                try:
                    db.bouncers.update_one(
                        {"_id": ObjectId(bouncer_id)},
                        {"$inc": {"scans_count": 1}}
                    )
                except Exception as bouncer_update_error:
                    print(f"Warning: Failed to update bouncer stats: {bouncer_update_error}")
            
            return {
                "success": True,
                "status": "valid",
                "message": "Valid Entry",
                "details": {
                    "attendee_name": pass_doc.get('attendee_name') or pass_doc.get('user_name', 'Unknown'),
                    "ticket_type": pass_doc.get('ticket_type', 'Regular'),
                    "serial_number": sn_upper,
                    "scanned_at": scanned_at,
                    "is_bulk_generated": is_bulk_generated
                }
            }
            
        except Exception as e:
            print(f"DEBUG Error in ScanService: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "status": "error",
                "message": f"Service Error: {str(e)}"
            }
    
    def get_event_scan_stats(self, event_id):
        """Get scan statistics for a specific event"""
        try:
            query = {"event_id": ObjectId(event_id)}
            
            total_scans = db.scans.count_documents(query)
            valid_scans = db.scans.count_documents({**query, "status": "valid"})
            
            # Today's scans
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_scans = db.scans.count_documents({
                **query,
                "scanned_at": {"$gte": today_start}
            })
            
            # Bulk vs Regular breakdown
            bulk_scans = db.scans.count_documents({**query, "is_bulk_generated": True})
            regular_scans = total_scans - bulk_scans
            
            return {
                "total_scans": total_scans,
                "valid_scans": valid_scans,
                "invalid_scans": total_scans - valid_scans,
                "today_scans": today_scans,
                "bulk_scans": bulk_scans,
                "regular_scans": regular_scans
            }
        except Exception as e:
            print(f"Error fetching scan stats: {e}")
            return {
                "total_scans": 0,
                "valid_scans": 0,
                "invalid_scans": 0,
                "today_scans": 0,
                "bulk_scans": 0,
                "regular_scans": 0
            }
    
    def get_recent_scans(self, event_id=None, limit=50):
        """Get recent scan activity"""
        try:
            query = {}
            if event_id:
                query["event_id"] = ObjectId(event_id)
            
            scans = list(db.scans.find(query)
                        .sort("scanned_at", -1)
                        .limit(limit))
            
            return {
                "success": True,
                "scans": scans,
                "count": len(scans)
            }
        except Exception as e:
            print(f"Error fetching recent scans: {e}")
            return {
                "success": False,
                "scans": [],
                "count": 0,
                "error": str(e)
            }
    
    def get_pass_scan_history(self, serial_number):
        """Get scan history for a specific pass"""
        try:
            sn_upper = serial_number.strip().upper()
            
            scans = list(db.scans.find({"serial_number": sn_upper})
                        .sort("scanned_at", -1))
            
            return {
                "success": True,
                "serial_number": sn_upper,
                "scans": scans,
                "total_scans": len(scans)
            }
        except Exception as e:
            print(f"Error fetching pass scan history: {e}")
            return {
                "success": False,
                "serial_number": serial_number,
                "scans": [],
                "total_scans": 0,
                "error": str(e)
            }
    
    def verify_pass_without_scan(self, serial_number, event_id):
        """
        Verify pass validity without actually scanning it
        Useful for preview/check before actual scan
        """
        try:
            sn_upper = serial_number.strip().upper()
            
            pass_doc = db.passes.find_one({
                "serial_number": sn_upper,
                "event_id": ObjectId(event_id)
            })
            
            if not pass_doc:
                return {
                    "success": False,
                    "status": "not_found",
                    "message": "Pass not found for this event"
                }
            
            # Check status
            pass_status = pass_doc.get('status', 'valid')
            is_scanned = pass_doc.get('scanned', False)
            
            if pass_status not in ['valid', 'active']:
                status = "invalid"
                message = f"Pass status: {pass_status}"
            elif is_scanned:
                status = "already_scanned"
                message = "This pass has already been scanned"
            else:
                status = "valid"
                message = "Pass is valid and ready to scan"
            
            return {
                "success": True,
                "status": status,
                "message": message,
                "pass_info": {
                    "serial_number": sn_upper,
                    "attendee_name": pass_doc.get('attendee_name') or pass_doc.get('user_name'),
                    "ticket_type": pass_doc.get('ticket_type'),
                    "event_name": pass_doc.get('event_name'),
                    "scanned": is_scanned,
                    "scanned_at": pass_doc.get('scanned_at'),
                    "is_bulk_generated": pass_doc.get('is_bulk_generated', False)
                }
            }
            
        except Exception as e:
            print(f"Error verifying pass: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }
    
    def get_bouncer_scan_stats(self, bouncer_id):
        """Get scan statistics for a specific bouncer"""
        try:
            query = {"bouncer_id": ObjectId(bouncer_id)}
            
            total_scans = db.scans.count_documents(query)
            
            # Today's scans
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_scans = db.scans.count_documents({
                **query,
                "scanned_at": {"$gte": today_start}
            })
            
            # Recent scans
            recent_scans = list(db.scans.find(query)
                              .sort("scanned_at", -1)
                              .limit(10))
            
            return {
                "success": True,
                "total_scans": total_scans,
                "today_scans": today_scans,
                "recent_scans": recent_scans
            }
        except Exception as e:
            print(f"Error fetching bouncer stats: {e}")
            return {
                "success": False,
                "total_scans": 0,
                "today_scans": 0,
                "recent_scans": [],
                "error": str(e)
            }

scan_service = ScanService()