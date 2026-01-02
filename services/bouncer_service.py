from datetime import datetime
from services.database import db
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash

class BouncerService:
    """Service for managing bouncers/security staff"""
    
    def create_bouncer(self, name, email, password, phone='', event_id=None, assigned_by=None):
        """
        Create a new bouncer user account and optionally assign to event
        """
        try:
            # 1. Check if email already exists (case-insensitive)
            normalized_email = email.strip().lower()
            existing_user = db.users.find_one({"email": normalized_email})
            if existing_user:
                return {"success": False, "message": "Email already registered"}
            
            # 2. Create the user account with scrypt:32768:8:1
            # generate_password_hash returns a string including algorithm, salt, and hash
            hashed_password = generate_password_hash(
                password, 
                method='scrypt:32768:8:1'
            )
            
            user_doc = {
                "name": name.strip(),
                "email": normalized_email,
                "password": hashed_password,
                "phone": phone.strip() if phone else '',
                "role": "bouncer",
                "is_active": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            user_result = db.users.insert_one(user_doc)
            user_id = user_result.inserted_id
            
            # 3. If event_id provided, create the assignment
            if event_id and event_id != "None" and event_id != "":
                try:
                    event_oid = ObjectId(event_id)
                    event = db.events.find_one({"_id": event_oid})
                    
                    if not event:
                        return {
                            "success": True,
                            "message": "Bouncer created but event not found for assignment",
                            "bouncer_id": str(user_id)
                        }
                    
                    # Check if already assigned
                    existing_assignment = db.bouncers.find_one({
                        "user_id": user_id,
                        "event_id": event_oid
                    })
                    
                    if not existing_assignment:
                        bouncer_doc = {
                            "user_id": user_id,
                            "event_id": event_oid,
                            "assigned_by": ObjectId(assigned_by) if assigned_by else None,
                            "assigned_at": datetime.now(),
                            "status": "active",
                            "scans_count": 0,
                            "gate_name": "Main Gate"
                        }
                        db.bouncers.insert_one(bouncer_doc)
                        
                        return {
                            "success": True,
                            "message": "Bouncer account created and assigned to event",
                            "bouncer_id": str(user_id)
                        }
                except Exception as assign_err:
                    return {
                        "success": True,
                        "message": f"User created, but assignment failed: {str(assign_err)}",
                        "bouncer_id": str(user_id)
                    }
            
            return {
                "success": True,
                "message": "Bouncer account created successfully",
                "bouncer_id": str(user_id)
            }
            
        except Exception as e:
            print(f"Error creating bouncer: {e}")
            return {"success": False, "message": str(e)}

    def assign_bouncer_to_event(self, user_id, event_id, assigned_by):
        """Assign existing bouncer to an event"""
        try:
            user = db.users.find_one({"_id": ObjectId(user_id), "role": "bouncer"})
            if not user:
                return {"success": False, "message": "User not found or is not a bouncer"}
            
            event = db.events.find_one({"_id": ObjectId(event_id)})
            if not event:
                return {"success": False, "message": "Event not found"}
            
            existing = db.bouncers.find_one({
                "user_id": ObjectId(user_id),
                "event_id": ObjectId(event_id)
            })
            if existing:
                return {"success": False, "message": "Bouncer already assigned to this event"}
            
            bouncer_doc = {
                "user_id": ObjectId(user_id),
                "event_id": ObjectId(event_id),
                "assigned_by": ObjectId(assigned_by),
                "assigned_at": datetime.now(),
                "status": "active",
                "scans_count": 0,
                "gate_name": "Main Gate"
            }
            
            result = db.bouncers.insert_one(bouncer_doc)
            return {
                "success": True,
                "message": "Bouncer assigned successfully",
                "bouncer_id": str(result.inserted_id)
            }
        except Exception as e:
            print(f"Error assigning bouncer: {e}")
            return {"success": False, "message": str(e)}

    def get_all_bouncers(self, event_id=None, skip=0, limit=50):
        try:
            query = {"event_id": ObjectId(event_id)} if event_id else {}
            bouncers = list(db.bouncers.find(query).sort("assigned_at", -1).skip(skip).limit(limit))
            for bouncer in bouncers:
                user = db.users.find_one({"_id": bouncer["user_id"]}, {"password": 0})
                if user:
                    bouncer["user_name"] = user.get("name", "Unknown")
                    bouncer["user_email"] = user.get("email", "")
                    bouncer["user_phone"] = user.get("phone", "")
                
                event = db.events.find_one({"_id": bouncer["event_id"]})
                if event:
                    bouncer["event_name"] = event.get("name", "Unknown")
                
                bouncer["_id"] = str(bouncer["_id"])
                bouncer["user_id"] = str(bouncer["user_id"])
                bouncer["event_id"] = str(bouncer["event_id"])
            return bouncers
        except Exception as e:
            print(f"Error fetching bouncers: {e}")
            return []

    def remove_bouncer(self, bouncer_id):
        """Remove a bouncer assignment from the bouncers collection"""
        try:
            print(f"🔍 Attempting to delete bouncer with ID: {bouncer_id}")
            print(f"🔍 ID type: {type(bouncer_id)}")
            
            # Validate ObjectId
            if not ObjectId.is_valid(bouncer_id):
                print(f"❌ Invalid ObjectId format: {bouncer_id}")
                return False
            
            # Check if record exists
            existing = db.bouncers.find_one({"_id": ObjectId(bouncer_id)})
            print(f"🔍 Existing record: {existing}")
            
            if not existing:
                print(f"❌ No bouncer assignment found with ID: {bouncer_id}")
                return False
            
            # Perform deletion
            result = db.bouncers.delete_one({"_id": ObjectId(bouncer_id)})
            print(f"✅ Deletion result - deleted_count: {result.deleted_count}")
            
            return result.deleted_count > 0
        except Exception as e:
            print(f"💥 Exception in remove_bouncer: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def get_total_bouncers(self, event_id=None):
        try:
            query = {"event_id": ObjectId(event_id)} if event_id else {}
            return db.bouncers.count_documents(query)
        except Exception:
            return 0

    def increment_scan_count(self, bouncer_id):
        """Increment the scan count for a bouncer"""
        try:
            db.bouncers.update_one(
                {"_id": ObjectId(bouncer_id)},
                {"$inc": {"scans_count": 1}}
            )
            return True
        except Exception:
            return False

    def get_bouncer_events(self, user_id):
        """Get all events assigned to a specific bouncer"""
        try:
            assignments = list(db.bouncers.find({
                "user_id": ObjectId(user_id),
                "status": "active"
            }))
            
            enriched_events = []
            for assignment in assignments:
                event = db.events.find_one({"_id": assignment["event_id"]})
                if event:
                    enriched_events.append({
                        "event_id": str(event["_id"]),
                        "event_name": event.get("name", "Unknown Event"),
                        "event_date": str(event.get("date", "N/A")),
                        "gate_name": assignment.get("gate_name", "Main Gate")
                    })
            return enriched_events
        except Exception as e:
            print(f"Error fetching bouncer events: {e}")
            return []

bouncer_service = BouncerService()