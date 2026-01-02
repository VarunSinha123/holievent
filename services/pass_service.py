import hashlib
import json
import os
from datetime import datetime
import qrcode
from io import BytesIO
from services.database import db
from services.s3_service import s3_service
from utils.pass_designer import pass_designer
from bson.objectid import ObjectId

class PassService:
    def __init__(self):
        # No longer need local storage directory
        pass
    
    def generate_serial_number(self, attendee_name, ticket_type):
        """Generate unique serial number"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        base = f"{attendee_name}{ticket_type}{timestamp}"
        hash_obj = hashlib.md5(base.encode())
        return f"HOLI2026-{hash_obj.hexdigest()[:8].upper()}"
    
    def _parse_date(self, date_val):
        """Helper to ensure date is a datetime object or a valid descriptive string"""
        if isinstance(date_val, datetime):
            return date_val
        
        if not date_val:
            return datetime.now()

        if isinstance(date_val, str):
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(date_val, fmt)
                except ValueError:
                    continue
            return date_val
            
        return datetime.now()

    def create_pass(self, attendee_name, ticket_type, event_name, event_date, venue, event_id=None):
        """Create a new event pass with QR code and store in S3"""
        try:
            # Ensure name isn't empty to prevent branding/lookup issues
            attendee_name = attendee_name.strip() if attendee_name else "Guest"
            
            event_date_val = self._parse_date(event_date)
            serial_num = self.generate_serial_number(attendee_name, ticket_type)
            sequence_num = db.get_next_sequence()
            
            pass_data = {
                "serial_number": serial_num,
                "sequence_number": sequence_num,
                "attendee_name": attendee_name,
                "user_name": attendee_name, # Redundant but kept for scan_service compatibility
                "ticket_type": ticket_type,
                "event_name": event_name,
                "event_date": event_date_val,
                "venue": venue,
                "issued_at": datetime.now(),
                "status": "valid",
                "scanned": False,
                "scanned_at": None,
                "is_admin_generated": True, # Added to help scan logic skip order check
                "is_bulk_generated": False  # This is a regular pass, not bulk
            }
            
            if event_id:
                try:
                    pass_data["event_id"] = ObjectId(event_id)
                except:
                    pass_data["event_id"] = event_id
            
            qr_data = json.dumps({
                "serial": serial_num,
                "event": event_name,
                "name": attendee_name,
                "sequence": sequence_num
            })
            
            qr = qrcode.QRCode(version=1, box_size=8, border=2)
            qr.add_data(qr_data)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Generate pass image without sponsor or powered-by branding
            pass_image_bytes = pass_designer.create_pass_image(
                pass_data,
                qr_img
            )
            
            # Upload to S3
            filename = f"{serial_num}.png"
            data_to_write = pass_image_bytes if isinstance(pass_image_bytes, bytes) else pass_image_bytes.getvalue()
            
            success, s3_url = s3_service.upload_file(
                data_to_write,
                filename,
                folder='passes',
                content_type='image/png'
            )
            
            if not success:
                print(f"Failed to upload pass to S3: {serial_num}, Error: {s3_url}")
                return {"success": False, "error": "Failed to upload pass image", "message": "Failed to upload pass image"}
            
            # Store S3 key for generating fresh presigned URLs later
            s3_key = f"passes/{filename}"
            pass_data['s3_key'] = s3_key
            pass_data['pass_url'] = s3_url  # Store initial presigned URL
            
            db.passes.insert_one(pass_data)
            
            return {
                "success": True,
                "serial_number": serial_num,
                "sequence_number": sequence_num,
                "pass_url": s3_url,
                "s3_key": s3_key,
                "pass_data": pass_data
            }
            
        except Exception as e:
            print(f"Error creating pass: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e), "message": str(e)}

    def get_pass(self, serial_number):
        """Retrieve a single pass by serial number and generate fresh presigned URL"""
        if not serial_number:
            return None
        pass_doc = db.passes.find_one({"serial_number": serial_number.strip().upper()})
        
        # Generate fresh presigned URL if we have S3 key
        if pass_doc and 's3_key' in pass_doc:
            fresh_url = s3_service.generate_presigned_url(pass_doc['s3_key'], expiration=3600)
            if fresh_url:
                pass_doc['pass_url'] = fresh_url
        
        return pass_doc

    def get_pass_download_url(self, serial_number):
        """Get a presigned URL for downloading the pass"""
        pass_doc = db.passes.find_one({"serial_number": serial_number.strip().upper()})
        
        if not pass_doc or 's3_key' not in pass_doc:
            return None
        
        # Generate presigned URL with download disposition (forces download)
        download_url = s3_service.generate_presigned_url(
            pass_doc['s3_key'], 
            expiration=300,  # 5 minutes for download
            download=True
        )
        
        return download_url

    def scan_pass(self, serial_number, event_id, bouncer_id=None, scanned_by=None):
        """
        Scan and verify a pass based on serial_number only
        Updates BOTH passes and qr_codes collections for bulk-generated passes
        """
        try:
            sn_upper = serial_number.strip().upper()
            
            # 1. Find Pass
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

            # 2. Check pass validity
            pass_status = pass_doc.get('status', 'valid')
            if pass_status not in ['valid', 'active']:
                return {
                    "success": False,
                    "status": "invalid",
                    "message": f"Pass status: {pass_status}"
                }

            # 3. Check for double scan
            if pass_doc.get('scanned') is True:
                return {
                    "success": False, 
                    "status": "already_scanned", 
                    "message": "Already Scanned",
                    "details": {
                        "attendee": pass_doc.get('attendee_name') or pass_doc.get('user_name'),
                        "scanned_at": pass_doc.get('scanned_at')
                    }
                }

            # 4. Success - Update Records in BOTH collections
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
                    "scanned_at": scanned_at,
                    "scanned_by": ObjectId(scanned_by) if scanned_by else None,
                    "scanned_by_name": scanned_by_name,
                    "status": "scanned"
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
                except Exception as qr_error:
                    print(f"Warning: Failed to update qr_codes collection: {qr_error}")

            # Log scan event in scans collection
            db.scans.insert_one({
                "pass_id": pass_doc['_id'],
                "serial_number": sn_upper,
                "event_id": ObjectId(event_id),
                "bouncer_id": ObjectId(bouncer_id) if bouncer_id else None,
                "scanned_by": ObjectId(scanned_by) if scanned_by else None,
                "scanned_at": scanned_at,
                "attendee_name": pass_doc.get('attendee_name') or pass_doc.get('user_name', 'Guest'),
                "ticket_type": pass_doc.get('ticket_type', 'Regular'),
                "status": "valid",
                "is_bulk_generated": is_bulk_generated
            })

            return {
                "success": True,
                "status": "valid",
                "message": "Valid Entry",
                "details": {
                    "attendee_name": pass_doc.get('attendee_name') or pass_doc.get('user_name', 'Guest'),
                    "ticket_type": pass_doc.get('ticket_type', 'Regular'),
                    "serial_number": sn_upper,
                    "is_bulk_generated": is_bulk_generated
                }
            }

        except Exception as e:
            print(f"Scan error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False, 
                "status": "error", 
                "message": str(e)
            }

    def get_all_passes(self, skip=0, limit=50):
        """Get all passes with fresh presigned URLs"""
        passes = list(db.passes.find().sort("issued_at", -1).skip(skip).limit(limit))
        
        # Generate fresh presigned URLs for all passes
        s3_keys = [p['s3_key'] for p in passes if 's3_key' in p]
        
        if s3_keys:
            fresh_urls = s3_service.generate_batch_presigned_urls(s3_keys, expiration=3600)
            
            for pass_doc in passes:
                if 's3_key' in pass_doc and pass_doc['s3_key'] in fresh_urls:
                    pass_doc['pass_url'] = fresh_urls[pass_doc['s3_key']]
        
        return passes

    def get_total_passes(self):
        return db.passes.count_documents({})

    def get_stats(self):
        try:
            total = db.passes.count_documents({})
            scanned = db.passes.count_documents({"scanned": True})
            bulk = db.passes.count_documents({"is_bulk_generated": True})
            regular = db.passes.count_documents({"is_bulk_generated": {"$ne": True}})
            
            ticket_type_stats = list(db.passes.aggregate([
                {"$group": {"_id": "$ticket_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]))
            ticket_breakdown = {stat['_id']: stat['count'] for stat in ticket_type_stats}
            
            return {
                "total": total,
                "scanned": scanned,
                "pending": max(0, total - scanned),
                "bulk": bulk,
                "regular": regular,
                "attendance_rate": round((scanned/total*100), 1) if total > 0 else 0,
                "ticket_breakdown": ticket_breakdown
            }
        except Exception as e:
            return {
                "total": 0, 
                "scanned": 0, 
                "pending": 0, 
                "bulk": 0,
                "regular": 0,
                "attendance_rate": 0, 
                "ticket_breakdown": {}
            }

pass_service = PassService()