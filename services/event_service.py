from datetime import datetime
from typing import Dict, List, Optional, Any
from bson.objectid import ObjectId
from services.database import db


class EventService:
    """Service for managing events and ticket types"""
    
    def __init__(self):
        self.collection = db.events
    
    # ============================================================================
    # EVENT CRUD OPERATIONS
    # ============================================================================
    
    def create_event(
        self,
        name: str,
        description: str,
        date: datetime,
        venue: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        organizer: Optional[str] = None,
        image_url: Optional[str] = None,
        created_by: Optional[str] = None,
        ticket_types: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Create new event with optional ticket types"""
        try:
            event_data = self._build_event_data(
                name, description, date, venue, start_time,
                end_time, organizer, image_url, created_by
            )
            
            result = self.collection.insert_one(event_data)
            event_id = str(result.inserted_id)
            
            if ticket_types:
                self._add_ticket_types_batch(event_id, ticket_types)
            
            return self._success_response("Event created successfully", event_id=event_id)
            
        except Exception as e:
            return self._error_response(f"Failed to create event: {str(e)}")
    
    def get_event(self, event_id: str) -> Optional[Dict]:
        """Get single event by ID"""
        try:
            return self.collection.find_one({"_id": ObjectId(event_id)})
        except Exception as e:
            print(f"Error getting event: {e}")
            return None
    
    def get_all_events(
        self,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 50
    ) -> List[Dict]:
        """Get paginated list of events"""
        try:
            query = {"is_active": True} if active_only else {}
            
            return list(
                self.collection.find(query)
                .sort("date", -1)
                .skip(skip)
                .limit(limit)
            )
        except Exception as e:
            print(f"Error fetching events: {e}")
            return []
    
    def get_total_events(self) -> int:
        """Get total count of events"""
        try:
            return self.collection.count_documents({})
        except Exception as e:
            print(f"Error counting events: {e}")
            return 0
    
    def update_event(
        self,
        event_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        date: Optional[datetime] = None,
        venue: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        organizer: Optional[str] = None,
        ticket_types: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Update event details"""
        try:
            update_dict = self._build_update_dict(
                name, description, date, venue,
                start_time, end_time, organizer
            )
            
            result = self.collection.update_one(
                {"_id": ObjectId(event_id)},
                {"$set": update_dict}
            )
            
            if result.modified_count > 0:
                if ticket_types is not None:
                    self._replace_ticket_types(event_id, ticket_types)
                return self._success_response("Event updated")
            
            return self._error_response("No changes made")
            
        except Exception as e:
            return self._error_response(f"Failed to update event: {str(e)}")
    
    def toggle_event_status(self, event_id: str, is_active: bool) -> bool:
        """Activate or deactivate an event"""
        try:
            result = self.collection.update_one(
                {"_id": ObjectId(event_id)},
                {"$set": {"is_active": is_active, "updated_at": datetime.now()}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error toggling event status: {e}")
            return False
    
    def delete_event(self, event_id: str) -> Dict[str, Any]:
        """Delete event - no ticket sales check since tracking is removed"""
        try:
            result = self.collection.delete_one({"_id": ObjectId(event_id)})
            
            if result.deleted_count > 0:
                return self._success_response("Event deleted")
            
            return self._error_response("Event not found")
            
        except Exception as e:
            return self._error_response(f"Failed to delete event: {str(e)}")
    
    def get_active_event(self) -> Optional[Dict]:
        """Get first active event"""
        try:
            return self.collection.find_one({"is_active": True})
        except Exception as e:
            print(f"Error getting active event: {e}")
            return None
    
    # ============================================================================
    # TICKET TYPE OPERATIONS
    # ============================================================================
    
    def add_ticket_type(
        self,
        event_id: str,
        ticket_name: str,
        price: float,
        description: str = "",
        total_available: int = 500,
        features: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Add a ticket type to an event"""
        try:
            ticket_type = self._build_ticket_type(
                ticket_name, price, description,
                total_available, features
            )
            
            result = self.collection.update_one(
                {"_id": ObjectId(event_id)},
                {
                    "$push": {"ticket_types": ticket_type},
                    "$set": {"updated_at": datetime.now()}
                }
            )
            
            if result.modified_count > 0:
                return self._success_response(
                    "Ticket type added",
                    ticket_id=ticket_type["ticket_id"]
                )
            
            return self._error_response("Failed to add ticket type")
            
        except Exception as e:
            return self._error_response(f"Failed to add ticket type: {str(e)}")
    
    def update_ticket_type(
        self,
        event_id: str,
        ticket_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update ticket type details"""
        try:
            set_updates = {
                f"ticket_types.$.{key}": value
                for key, value in updates.items()
            }
            set_updates["updated_at"] = datetime.now()
            
            result = self.collection.update_one(
                {
                    "_id": ObjectId(event_id),
                    "ticket_types.ticket_id": ticket_id
                },
                {"$set": set_updates}
            )
            
            if result.modified_count > 0:
                return self._success_response("Ticket type updated")
            
            return self._error_response("No changes made")
            
        except Exception as e:
            return self._error_response(f"Failed to update ticket type: {str(e)}")
    
    def delete_ticket_type(self, event_id: str, ticket_id: str) -> Dict[str, Any]:
        """Delete ticket type - no sales check since tracking is removed"""
        try:
            result = self.collection.update_one(
                {"_id": ObjectId(event_id)},
                {"$pull": {"ticket_types": {"ticket_id": ticket_id}}}
            )
            
            if result.modified_count > 0:
                return self._success_response("Ticket type deleted")
            
            return self._error_response("Ticket type not found")
            
        except Exception as e:
            return self._error_response(f"Failed to delete ticket type: {str(e)}")
    
    # ============================================================================
    # TICKET AVAILABILITY (WITHOUT SALES TRACKING)
    # ============================================================================
    
    def get_available_tickets(self, event_id: str, ticket_id: str) -> Dict[str, Any]:
        """Check ticket availability for a specific ticket type"""
        try:
            event = self.get_event(event_id)
            
            if not event or not event.get('is_active'):
                return {"available": False, "message": "Event not active"}
            
            ticket_type = self._find_ticket_type(event, ticket_id)
            
            if not ticket_type:
                return {"available": False, "message": "Ticket type not found"}
            
            if not ticket_type.get('is_active', True):
                return {"available": False, "message": "Ticket type not available"}
            
            # Since we're not tracking sales, just return availability info
            return {
                "available": True,
                "total_available": ticket_type['total_available'],
                "price": ticket_type['price'],
                "name": ticket_type['name']
            }
            
        except Exception as e:
            print(f"Error checking availability: {e}")
            return {"available": False, "message": "Error checking availability"}
    
    # ============================================================================
    # STATISTICS & REPORTING (WITHOUT SALES DATA)
    # ============================================================================
    
    def get_event_statistics(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get basic statistics for an event"""
        try:
            event = self.get_event(event_id)
            
            if not event:
                return None
            
            ticket_info = self._get_ticket_info(event)
            
            return {
                "event_name": event['name'],
                "ticket_types": ticket_info,
                "is_active": event['is_active'],
                "created_at": event['created_at'],
                "event_date": event['date']
            }
            
        except Exception as e:
            print(f"Error getting event statistics: {e}")
            return None
    
    # ============================================================================
    # PRIVATE HELPER METHODS
    # ============================================================================
    
    def _build_event_data(
        self,
        name: str,
        description: str,
        date: datetime,
        venue: str,
        start_time: Optional[str],
        end_time: Optional[str],
        organizer: Optional[str],
        image_url: Optional[str],
        created_by: Optional[str]
    ) -> Dict[str, Any]:
        """Build event data dictionary"""
        return {
            "name": name.strip() if name else "",
            "description": description.strip() if description else "",
            "date": date,
            "venue": venue.strip() if venue else "",
            "start_time": start_time,
            "end_time": end_time,
            "organizer": organizer.strip() if organizer else "",
            "image_url": image_url,
            "created_by": created_by,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "is_active": True,
            "ticket_types": []
        }
    
    def _build_ticket_type(
        self,
        ticket_name: str,
        price: float,
        description: str,
        total_available: int,
        features: Optional[List[str]]
    ) -> Dict[str, Any]:
        """Build ticket type dictionary"""
        return {
            "ticket_id": str(ObjectId()),
            "name": ticket_name.strip() if ticket_name else "",
            "price": float(price) if price else 0.0,
            "description": description.strip() if description else "",
            "total_available": int(total_available) if total_available else 100,
            "features": features if features else [],
            "is_active": True,
            "created_at": datetime.now()
        }
    
    def _build_update_dict(
        self,
        name: Optional[str],
        description: Optional[str],
        date: Optional[datetime],
        venue: Optional[str],
        start_time: Optional[str],
        end_time: Optional[str],
        organizer: Optional[str]
    ) -> Dict[str, Any]:
        """Build update dictionary with only non-None values"""
        update_dict = {"updated_at": datetime.now()}
        
        if name is not None:
            update_dict['name'] = name.strip() if name else ""
        if description is not None:
            update_dict['description'] = description.strip() if description else ""
        if date is not None:
            update_dict['date'] = date
        if venue is not None:
            update_dict['venue'] = venue.strip() if venue else ""
        if start_time is not None:
            update_dict['start_time'] = start_time
        if end_time is not None:
            update_dict['end_time'] = end_time
        if organizer is not None:
            update_dict['organizer'] = organizer.strip() if organizer else ""
        
        return update_dict
    
    def _add_ticket_types_batch(self, event_id: str, ticket_types: List[Dict]) -> None:
        """Add multiple ticket types to an event"""
        for ticket in ticket_types:
            if ticket.get('name'):
                self.add_ticket_type(
                    event_id,
                    ticket.get('name'),
                    ticket.get('price', 0),
                    ticket.get('description', ''),
                    ticket.get('total_available', 500)
                )
    
    def _replace_ticket_types(self, event_id: str, ticket_types: List[Dict]) -> None:
        """Replace all ticket types for an event"""
        self.collection.update_one(
            {"_id": ObjectId(event_id)},
            {"$set": {"ticket_types": []}}
        )
        self._add_ticket_types_batch(event_id, ticket_types)
    
    def _find_ticket_type(self, event: Dict, ticket_id: str) -> Optional[Dict]:
        """Find a ticket type by ID within an event"""
        for ticket_type in event.get('ticket_types', []):
            if ticket_type['ticket_id'] == ticket_id:
                return ticket_type
        return None
    
    def _get_ticket_info(self, event: Dict) -> List[Dict[str, Any]]:
        """Get basic info for all ticket types"""
        ticket_info = []
        
        for ticket_type in event.get('ticket_types', []):
            ticket_info.append({
                "name": ticket_type['name'],
                "price": ticket_type['price'],
                "total_available": ticket_type['total_available'],
                "is_active": ticket_type.get('is_active', True)
            })
        
        return ticket_info
    
    def _success_response(self, message: str, **kwargs) -> Dict[str, Any]:
        """Create a success response dictionary"""
        response = {
            "success": True,
            "message": message
        }
        response.update(kwargs)
        return response
    
    def _error_response(self, message: str) -> Dict[str, Any]:
        """Create an error response dictionary"""
        print(f"Error: {message}")
        return {
            "success": False,
            "message": message
        }


# Create singleton instance
event_service = EventService()