import boto3
from botocore.exceptions import ClientError
from config import Config
import io
from datetime import datetime

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.bucket_name = Config.S3_BUCKET_NAME
    
    def upload_file(self, file_data, filename, folder='passes', content_type='image/png'):
        """
        Upload file to S3
        
        Args:
            file_data: File bytes or file object
            filename: Name for the file in S3
            folder: Folder path in S3 (passes, sponsors, etc.)
            content_type: MIME type
        
        Returns:
            tuple: (success: bool, url: str or error_message: str)
        """
        try:
            key = f"{folder}/{filename}"
            
            # If file_data is bytes, create a BytesIO object
            if isinstance(file_data, bytes):
                file_obj = io.BytesIO(file_data)
            else:
                file_obj = file_data
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                key,
                ExtraArgs={
                    'ContentType': content_type,
                    'ACL': 'private'  # Keep files private for security
                }
            )
            
            # Generate presigned URL (valid for 1 hour)
            url = self.generate_presigned_url(key)
            return True, url
            
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            return False, str(e)
    
    def generate_presigned_url(self, key, expiration=3600, download=False):
        """
        Generate presigned URL for private S3 object
        
        Args:
            key: S3 object key
            expiration: URL expiration time in seconds (default 1 hour)
            download: If True, forces download instead of displaying in browser
        
        Returns:
            str: Presigned URL or None
        """
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': key
            }
            
            # Add download headers if requested
            if download:
                filename = key.split('/')[-1]
                params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            return None
    
    def generate_batch_presigned_urls(self, keys, expiration=3600, download=False):
        """
        Generate presigned URLs for multiple S3 objects efficiently
        
        Args:
            keys: List of S3 object keys
            expiration: URL expiration time in seconds (default 1 hour)
            download: If True, forces download instead of displaying in browser
        
        Returns:
            dict: Dictionary mapping keys to presigned URLs
        """
        urls = {}
        for key in keys:
            url = self.generate_presigned_url(key, expiration, download)
            if url:
                urls[key] = url
        return urls
    
    def delete_file(self, key):
        """Delete file from S3"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
        except ClientError as e:
            print(f"Error deleting from S3: {e}")
            return False
    
    def get_file(self, key):
        """Retrieve file from S3"""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return response['Body'].read()
        except ClientError as e:
            print(f"Error retrieving from S3: {e}")
            return None

s3_service = S3Service()