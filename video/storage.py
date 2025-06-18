from typing import Tuple
import uuid
import os
import requests


class MediaType:
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TMP = "tmp"


class Storage:
    def __init__(self, storage_path):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        # make all the subdirectories for the media types
        for media_type in [
            MediaType.IMAGE,
            MediaType.VIDEO,
            MediaType.AUDIO,
            MediaType.TMP,
        ]:
            os.makedirs(os.path.join(self.storage_path, media_type), exist_ok=True)

    def _validate_media_id(self, media_id: str) -> tuple[str, str]:
        """
        Validates and parses a media ID to prevent path traversal attacks.

        Args:
            media_id (str): Media ID to validate

        Returns:
            tuple[str, str]: (media_type, filename)

        Raises:
            ValueError: If media_id is invalid or contains path traversal attempts
        """
        if not media_id or "_" not in media_id:
            raise ValueError("Invalid media ID format")

        media_type, filename = media_id.split("_", 1)

        # Validate media type
        valid_types = [MediaType.IMAGE, MediaType.VIDEO, MediaType.AUDIO, MediaType.TMP]
        if media_type not in valid_types:
            raise ValueError(f"Invalid media type: {media_type}")

        # Prevent path traversal by checking for dangerous patterns
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError(
                "Filename contains invalid characters or path traversal attempt"
            )

        # Additional validation: filename should not be empty and should be reasonable
        if not filename or len(filename) > 255:
            raise ValueError("Invalid filename")

        return media_type, filename

    def _get_safe_file_path(self, media_id: str) -> str:
        """
        Gets a safe file path for the given media ID after validation.

        Args:
            media_id (str): Media ID to get path for

        Returns:
            str: Safe file path
        """
        media_type, filename = self._validate_media_id(media_id)
        file_path = os.path.join(self.storage_path, media_type, filename)

        # Double-check that the resolved path is within the storage directory
        resolved_path = os.path.abspath(file_path)
        storage_abs_path = os.path.abspath(self.storage_path)

        if not resolved_path.startswith(storage_abs_path):
            raise ValueError("Path traversal attempt detected")

        return file_path

    def upload_media(
        self, media_type: MediaType, media_data: bytes, file_extension: str = ""
    ) -> str:
        """
        Uploads media to the server.

        Args:
            media_type (str): Type of media, e.g., 'image' or 'video'.
            media_data (bytes): Binary data of the media file.
            file_extension (str): File extension, e.g., '.jpg', '.mp4', '.wav'.

        Returns:
            str: Media ID, e.g., 'image_12345.jpg' or 'video_67890.mp4'.
        """
        # Validate media type
        valid_types = [MediaType.IMAGE, MediaType.VIDEO, MediaType.AUDIO, MediaType.TMP]
        if media_type not in valid_types:
            raise ValueError(f"Invalid media type: {media_type}")

        # Validate file extension to prevent path traversal
        if file_extension and (
            ".." in file_extension or "/" in file_extension or "\\" in file_extension
        ):
            raise ValueError("File extension contains invalid characters")

        asset_id = str(uuid.uuid4())
        filename = f"{asset_id}{file_extension}" if file_extension else asset_id
        file_path = os.path.join(self.storage_path, media_type, filename)

        # Additional safety check
        resolved_path = os.path.abspath(file_path)
        storage_abs_path = os.path.abspath(self.storage_path)
        if not resolved_path.startswith(storage_abs_path):
            raise ValueError("Path traversal attempt detected")

        with open(file_path, "wb") as f:
            f.write(media_data)

        media_id = f"{media_type}_{filename}"
        return media_id

    def get_media(self, media_id: str) -> bytes:
        """
        Retrieves media by ID.

        Args:
            media_id (str): Media ID, e.g., 'image_12345.jpg' or 'video_67890.mp4'.

        Returns:
            bytes: Binary data of the media file.
        """
        file_path = self._get_safe_file_path(media_id)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Media file {media_id} not found.")

        with open(file_path, "rb") as f:
            return f.read()

    def delete_media(self, media_id: str) -> None:
        """
        Deletes media by ID.

        Args:
            media_id (str): Media ID, e.g., 'image_12345.jpg' or 'video_67890.mp4'.
        """
        file_path = self._get_safe_file_path(media_id)

        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            raise FileNotFoundError(f"Media file {media_id} not found.")

    def media_exists(self, media_id: str) -> bool:
        """
        Checks if media exists by ID.

        Args:
            media_id (str): Media ID, e.g., 'image_12345.jpg' or 'video_67890.mp4'.

        Returns:
            bool: True if media exists, False otherwise.
        """
        try:
            file_path = self._get_safe_file_path(media_id)
            return os.path.exists(file_path)
        except ValueError:
            return False

    def get_media_path(self, media_id: str) -> str:
        """
        Gets the file path of the media by ID.

        Args:
            media_id (str): Media ID, e.g., 'image_12345.jpg' or 'video_67890.mp4'.

        Returns:
            str: Full file path of the media.
        """
        return self._get_safe_file_path(media_id)

    ### untested
    def create_media_filename(
        self, media_type: MediaType, file_extension: str = ""
    ) -> str:
        # Validate media type
        valid_types = [MediaType.IMAGE, MediaType.VIDEO, MediaType.AUDIO, MediaType.TMP]
        if media_type not in valid_types:
            raise ValueError(f"Invalid media type: {media_type}")

        # Validate file extension to prevent path traversal
        if file_extension and (
            ".." in file_extension or "/" in file_extension or "\\" in file_extension
        ):
            raise ValueError("File extension contains invalid characters")

        asset_id = str(uuid.uuid4())
        filename = f"{asset_id}{file_extension}" if file_extension else asset_id
        return f"{media_type}_{filename}"

    def create_media_filename_with_id(
        self, media_type: MediaType, file_extension: str = ""
    ) -> Tuple[str, str]:
        file_id = self.create_media_filename(media_type, file_extension)
        return file_id, self.get_media_path(file_id)

    def create_tmp_file_id(self, media_id: str) -> str:
        """
        Creates a temporary filename for media upload.

        Args:
            media_id (str): Media ID to create a temporary filename for.

        Returns:
            str: Temporary media ID.
        """
        return f"{media_id}.tmp"
        
    def list_media(self, media_type: Optional[str] = None):
    """
    Lists all media files, optionally filtering by a specific media type.
    Returns a list of dictionaries, each with a 'file_id'.
    """
    logger.info(f"Listing media with filter: {media_type}")
    
    files_to_return = []
    
    # Determine which directories to search
    dirs_to_search = []
    if media_type:
        # If a specific type is requested, only search that directory
        search_dir = os.path.join(self.storage_path, media_type)
        if os.path.isdir(search_dir):
            dirs_to_search.append(search_dir)
    else:
        # If no type is specified, search all media type directories
        for m_type in ["image", "video", "audio"]:
            search_dir = os.path.join(self.storage_path, m_type)
            if os.path.isdir(search_dir):
                dirs_to_search.append(search_dir)

    # Walk through the selected directories
    for directory in dirs_to_search:
        for filename in os.listdir(directory):
            # We only want the file name without the extension as the ID
            file_id, _ = os.path.splitext(filename)
            files_to_return.append({"file_id": file_id})
    
    logger.info(f"Found {len(files_to_return)} files.")
    return files_to_return

    
    def create_tmp_file(self, media_id: str) -> str:
        """
        Creates a temporary file for media upload.

        Args:
            media_id (str): Media ID to create a temporary file for.

        Returns:
            str: Temporary media ID.
        """
        tmp_id = f"{media_id}.tmp"
        tmp_path = self.get_media_path(tmp_id)

        with open(tmp_path, "wb") as f:
            pass
        return tmp_id

    def get_media_type(self, media_id: str) -> MediaType:
        """
        Gets the media type of the given media ID.

        Args:
            media_id (str): Media ID to get the type for.

        Returns:
            MediaType: The type of the media.
        """
        media_type, _ = self._validate_media_id(media_id)
        return media_type

    def is_valid_url(self, url: str) -> bool:
        """
        Validates a URL to ensure it is well-formed.

        Args:
            url (str): The URL to validate.

        Returns:
            bool: True if the URL is valid, False otherwise.
        """
        from urllib.parse import urlparse

        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
        
    def upload_media_from_url(
        self, media_type: MediaType, url: str
    ) -> str:
        """
        Uploads media from a URL.

        Args:
            media_type (MediaType): Type of media, e.g., MediaType.IMAGE.
            url (str): URL of the media file.

        Returns:
            str: Media ID, e.g., 'image_12345.jpg'.
        """
        if not self.is_valid_url(url):
            raise ValueError("Invalid URL")

        response = requests.get(url)
        if response.status_code != 200:
            raise ValueError(f"Failed to download media from {url}")

        file_extension = os.path.splitext(url)[1]
        return self.upload_media(media_type, response.content, file_extension)
