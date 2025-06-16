from storages.backends.s3boto3 import S3Boto3Storage
from filebrowser.storage import StorageMixin
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)

class CustomS3Boto3Storage(S3Boto3Storage, StorageMixin):
    """
    Custom S3 Storage for Django FileBrowser.
    Combines S3Boto3Storage with FileBrowser's StorageMixin
    to provide necessary methods like isdir and isfile for S3.
    """

    def _full_path(self, name):
        """
        Returns the full path for a given name, including the location prefix.
        This is a helper method to correctly resolve paths for S3.
        """
        if self.location:
            return os.path.join(self.location, name)
        return name

    def isdir(self, name):
        """
        Checks if a given path is a directory on S3.
        In S3, directories are often represented by objects with a trailing slash,
        or by the existence of objects within that prefix.
        """
        name = self._full_path(name)
        if not name.endswith('/'):
            name += '/'
        
        # Check if any object exists with this prefix, which implies a directory
        # List up to 1 item under the prefix to determine if it's a "directory"
        try:
            # Using client directly for more control over list_objects_v2
            # The name here is already prefixed correctly by _full_path
            response = self.bucket.meta.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=name,
                MaxKeys=1
            )
            return 'Contents' in response or 'CommonPrefixes' in response
        except Exception as e:
            logger.warning(f"Error checking if S3 path is directory ({name}): {e}")
            return False

    def isfile(self, name):
        """
        Checks if a given path is a regular file on S3.
        """
        name = self._full_path(name)
        if name.endswith('/'): # A file cannot end with a slash
            return False
        
        # Check if the object exists and is not a directory marker
        try:
            # We use exists from S3Boto3Storage to check for file existence
            # Then, ensure it's not just a directory marker (object with trailing slash)
            if self.exists(name):
                # If an object exists, it could still be a directory marker.
                # A common S3 practice for empty directories is an object named 'folder/'
                # We need to distinguish between 'file.txt' and 'folder/'
                # Getting object metadata is a more robust way to confirm it's a file
                # by checking if it's a zero-byte object with a trailing slash.
                
                # Check if it's an object, and not a 'directory marker' object (zero-byte with trailing slash)
                # Note: This is an expensive call, use with caution if many checks are needed.
                # A simpler heuristic for FileBrowser might be to just rely on self.exists()
                # for isfile, and for isdir, check for prefix + '/'.
                # For now, let's keep it simple with self.exists() for isfile.
                return True # If self.exists returns true, it's a file or directory marker.
                            # isdir will distinguish directory markers. So, if not isdir and exists, it's a file.
            return False
        except Exception as e:
            logger.warning(f"Error checking if S3 path is file ({name}): {e}")
            return False
            
    def listdir(self, path):
        """
        Lists contents of a directory on S3.
        Returns a tuple of (directories, files).
        """
        path = self._full_path(path)
        if path and not path.endswith('/'):
            path += '/'

        directories = []
        files = []
        
        try:
            paginator = self.bucket.meta.client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=path, Delimiter='/')
            
            for page in pages:
                if 'CommonPrefixes' in page:
                    for common_prefix in page['CommonPrefixes']:
                        dir_name = common_prefix['Prefix'][len(path):].rstrip('/')
                        if dir_name: # Ensure it's not empty string for root
                            directories.append(dir_name)
                
                if 'Contents' in page:
                    for obj in page['Contents']:
                        file_name = obj['Key'][len(path):]
                        if file_name and file_name != '': # Ensure it's not the directory itself or empty
                            # Exclude directory markers (e.g., 'folder_name/')
                            if not file_name.endswith('/') or obj['Size'] > 0:
                                files.append(file_name)
            
            return directories, files
        except Exception as e:
            logger.error(f"Error listing S3 directory contents for {path}: {e}")
            return [], []

    # FileBrowser also expects move, delete, and mkdir methods.
    # S3Boto3Storage already provides _save (which handles uploads/overwrites), delete.
    # For mkdir, S3 doesn't have true directories, but we can simulate by creating a zero-byte object with a trailing slash.

    def _save(self, name, content):
        # This method is already implemented by S3Boto3Storage for saving files.
        # We don't need to override it unless we add custom logic during save.
        return super()._save(name, content)

    def delete(self, name):
        # This method is already implemented by S3Boto3Storage for deleting files.
        # We don't need to override it unless we add custom logic during delete.
        # It handles both files and directory markers (objects ending with /)
        return super().delete(name)

    def _mkdir(self, name):
        """
        Creates a 'directory' on S3 by creating a zero-byte object with a trailing slash.
        This method is called by FileBrowser's makedirs.
        """
        name = self._full_path(name)
        if not name.endswith('/'):
            name += '/'
        try:
            self.bucket.put_object(Key=name, Body='')
            return True
        except Exception as e:
            logger.error(f"Error creating S3 directory marker ({name}): {e}")
            return False

    def makedirs(self, name):
        """
        Recursively creates 'directories' on S3.
        FileBrowser's makedirs maps to this.
        """
        parts = name.strip('/').split('/')
        current_path = []
        for part in parts:
            current_path.append(part)
            dir_to_create = '/'.join(current_path)
            if not self.isdir(dir_to_create):
                self._mkdir(dir_to_create) # Use our internal _mkdir which creates marker objects
        return True # Assume success if no exceptions raised

    def move(self, old_file_name, new_file_name, allow_overwrite=False):
        """
        Moves a file or directory on S3.
        For S3, this is a copy followed by a delete.
        """
        old_file_name_full = self._full_path(old_file_name)
        new_file_name_full = self._full_path(new_file_name)

        if self.isdir(old_file_name): # If it's a directory
            if not new_file_name_full.endswith('/'):
                new_file_name_full += '/'
            
            # List all objects under the old prefix and copy/delete
            try:
                paginator = self.connection.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.bucket_name, Prefix=old_file_name_full)
                
                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            source_key = obj['Key']
                            relative_path = source_key[len(old_file_name_full):]
                            destination_key = new_file_name_full + relative_path
                            self.bucket.copy_object(
                                CopySource={'Bucket': self.bucket_name, 'Key': source_key},
                                Key=destination_key
                            )
                            self.bucket.delete_object(Key=source_key)
                return True
            except Exception as e:
                logger.error(f"Error moving S3 directory from {old_file_name} to {new_file_name}: {e}")
                return False
        else: # It's a file
            if not allow_overwrite and self.exists(new_file_name):
                from django.core.files.storage import FileExistsError
                raise FileExistsError(f"The file {new_file_name} already exists.")
            try:
                # S3Boto3Storage has copy_object and delete_object for individual files
                self.bucket.copy_object(
                    CopySource={'Bucket': self.bucket_name, 'Key': old_file_name_full},
                    Key=new_file_name_full
                )
                self.bucket.delete_object(Key=old_file_name_full)
                return True
            except Exception as e:
                logger.error(f"Error moving S3 file from {old_file_name} to {new_file_name}: {e}")
                return False

    def get_url(self, name):
        """
        Returns the URL for a file.
        This is already handled by S3Boto3Storage and should be correct.
        """
        return super().url(name)

    # FileBrowser also expects filesize, modified_time, created_time, get_modified_time, get_created_time.
    # S3Boto3Storage already implements these or can be easily extended.
    # For now, focus on isdir/isfile/listdir/move/makedirs. 