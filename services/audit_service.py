from datetime import datetime
from services.database import db
from bson.objectid import ObjectId

class AuditService:
    """Centralized service for logging all system activities"""
    
    @staticmethod
    def log(action_type, performed_by, details, target_user=None, metadata=None):
        """
        Create an audit log entry
        
        Args:
            action_type (str): Type of action (e.g., 'user_created', 'pass_scanned')
            performed_by (str): User ID who performed the action
            details (str): Human-readable description of the action
            target_user (str, optional): User ID affected by the action
            metadata (dict, optional): Additional context data
        
        Returns:
            bool: True if log was created successfully
        """
        try:
            log_entry = {
                "action_type": action_type,
                "performed_by": ObjectId(performed_by) if performed_by else None,
                "details": details,
                "timestamp": datetime.now(),
                "metadata": metadata or {}
            }
            
            # Add target user if provided
            if target_user:
                log_entry["target_user"] = ObjectId(target_user)
            
            # Enrich with user details
            if performed_by:
                user = db.users.find_one({"_id": ObjectId(performed_by)}, {"name": 1, "email": 1})
                if user:
                    log_entry["performed_by_name"] = user.get("name", "Unknown")
                    log_entry["performed_by_email"] = user.get("email", "")
            
            db.audit_logs.insert_one(log_entry)
            return True
            
        except Exception as e:
            print(f"Failed to create audit log: {e}")
            return False
    
    @staticmethod
    def log_user_action(action_type, user_id, details, target_user=None):
        """Convenience method for user-related actions"""
        return AuditService.log(action_type, user_id, details, target_user)
    
    @staticmethod
    def log_system_action(action_type, details, metadata=None):
        """Convenience method for system actions"""
        return AuditService.log(action_type, None, details, metadata=metadata)
    
    @staticmethod
    def get_logs(action_type=None, user_id=None, start_date=None, end_date=None, limit=50):
        """
        Retrieve audit logs with filters
        
        Returns:
            list: List of audit log documents
        """
        query = {}
        
        if action_type:
            query["action_type"] = action_type
        
        if user_id:
            query["performed_by"] = ObjectId(user_id)
        
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        logs = list(db.audit_logs.find(query)
                   .sort("timestamp", -1)
                   .limit(limit))
        
        return logs

# Create singleton instance
audit_service = AuditService()