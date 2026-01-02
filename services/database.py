from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from config import Config
import certifi
import ssl
import os

class Database:
    """
    Singleton class to manage MongoDB connections and collection access.
    Handles automatic collection creation and index setup.
    """
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once even if __init__ is called multiple times
        if self._client is None:
            try:
                mongodb_uri = Config.MONGODB_URI
                
                # Check if using MongoDB Atlas (cloud) or local MongoDB
                is_atlas = 'mongodb.net' in mongodb_uri or 'mongodb+srv' in mongodb_uri
                
                if is_atlas:
                    print("Connecting to MongoDB Atlas...")
                    # MongoDB Atlas connection with proper SSL/TLS configuration
                    self._client = MongoClient(
                        mongodb_uri,
                        tlsCAFile=certifi.where(),  # Use certifi certificates for secure connection
                        serverSelectionTimeoutMS=5000,
                        connectTimeoutMS=5000,
                        socketTimeoutMS=5000
                    )
                else:
                    print("Connecting to local MongoDB...")
                    # Local MongoDB connection (no SSL needed typically)
                    self._client = MongoClient(
                        mongodb_uri,
                        serverSelectionTimeoutMS=5000
                    )
                
                # Test the connection via a ping command
                self._client.admin.command('ping')
                print("✓ MongoDB connection successful")
                
                # Set database from config
                self._db = self._client[Config.DATABASE_NAME]
                
                # Setup core collections and indexes
                self._setup_collections()
                
            except ServerSelectionTimeoutError as e:
                print(f"✗ MongoDB connection timeout: {e}")
                print("\nTroubleshooting steps:")
                print("1. Check if MongoDB URI is correct in your .env file")
                print("2. Verify your IP is whitelisted in MongoDB Atlas Network Access")
                print("3. Ensure your username/password are correct")
                print("4. Check if you need to install/update: pip install certifi pymongo[srv]")
                raise
            except ConnectionFailure as e:
                print(f"✗ MongoDB connection failed: {e}")
                raise
            except Exception as e:
                print(f"✗ Unexpected error connecting to MongoDB: {e}")
                raise
    
    def _setup_collections(self):
        """Setup internal collections and optimize with indexes"""
        try:
            collections = [
                'users', 'events', 'passes', 'scans', 
                'counters', 'bouncers', 'audit_logs', 'qr_codes'  # ADDED qr_codes
            ]
            
            existing_collections = self._db.list_collection_names()
            
            for collection in collections:
                if collection not in existing_collections:
                    self._db.create_collection(collection)
                    print(f"✓ Created collection: {collection}")
            
            # Create indexes for performance and uniqueness
            print("Setting up indexes...")
            
            # Users indexes
            self._db.users.create_index([('email', ASCENDING)], unique=True)
            self._db.users.create_index([('role', ASCENDING)])
            
            # Passes indexes
            self._db.passes.create_index([('serial_number', ASCENDING)], unique=True)
            self._db.passes.create_index([('sequence_number', ASCENDING)])
            self._db.passes.create_index([('user_id', ASCENDING)])
            self._db.passes.create_index([('event_id', ASCENDING)])
            self._db.passes.create_index([('status', ASCENDING)])
            
            # QR Codes indexes (ADDED)
            self._db.qr_codes.create_index([('serial_number', ASCENDING)], unique=True)
            self._db.qr_codes.create_index([('event_id', ASCENDING)])
            self._db.qr_codes.create_index([('used', ASCENDING)])
            self._db.qr_codes.create_index([('ticket_type', ASCENDING)])
            self._db.qr_codes.create_index([('is_bulk', ASCENDING)])
            
            # Scans indexes
            self._db.scans.create_index([('serial_number', ASCENDING)])
            self._db.scans.create_index([('event_id', ASCENDING)])
            self._db.scans.create_index([('bouncer_id', ASCENDING)])
            self._db.scans.create_index([('scanned_at', DESCENDING)])
            
            # Events indexes
            self._db.events.create_index([('is_active', ASCENDING)])
            self._db.events.create_index([('created_at', DESCENDING)])
            
            # Bouncers indexes
            self._db.bouncers.create_index([('user_id', ASCENDING)])
            self._db.bouncers.create_index([('event_id', ASCENDING)])
            
            # Audit logs indexes
            self._db.audit_logs.create_index([('timestamp', DESCENDING)])
            self._db.audit_logs.create_index([('user_id', ASCENDING)])
            self._db.audit_logs.create_index([('action_type', ASCENDING)])
            
            print("✓ Indexes created successfully")
            
            # Initialize counter for sequence numbers if not exists
            if self._db.counters.count_documents({'_id': 'pass_sequence'}) == 0:
                self._db.counters.insert_one({'_id': 'pass_sequence', 'seq': 0})
                print("✓ Pass sequence counter initialized")
            
        except Exception as e:
            print(f"✗ Error setting up collections: {e}")
            raise
    
    def get_next_sequence(self):
        """Atomic operation to get the next sequence number for a pass"""
        result = self._db.counters.find_one_and_update(
            {'_id': 'pass_sequence'},
            {'$inc': {'seq': 1}},
            return_document=True
        )
        return result['seq']
    
    # --- Collection Properties ---
    
    @property
    def users(self):
        return self._db.users
    
    @property
    def events(self):
        return self._db.events
    
    @property
    def passes(self):
        return self._db.passes
    
    @property
    def scans(self):
        return self._db.scans
    
    @property
    def counters(self):
        return self._db.counters
    
    @property
    def bouncers(self):
        return self._db.bouncers
    
    @property
    def audit_logs(self):
        return self._db.audit_logs
    
    @property
    def qr_codes(self):  # ADDED
        return self._db.qr_codes
    
    def close(self):
        if self._client:
            self._client.close()
            print("✓ MongoDB connection closed")

# Initialize shared database instance
db = Database()