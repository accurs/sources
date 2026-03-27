import asyncio

from logging import getLogger
from pathlib import Path
from io import BytesIO
from typing import (
    TYPE_CHECKING, 
    BinaryIO, 
    Optional, 
    Union
)

from minio import Minio as SyncMinio
from minio.error import S3Error

if TYPE_CHECKING:
    from heist.framework import heist

logger = getLogger("heist/minio")

from heist.shared.config import Configuration
from heist.framework.tools import human_size


class MinIO:
    def __init__(self, bot: "heist"):
        self.bot = bot
        self.config = Configuration.authentication.minio

        self.client = SyncMinio(
            endpoint=self.config.endpoint.replace(
                "https://", ""
            ).replace("http://", ""),
            access_key=self.config.access_key,
            secret_key=self.config.secret_key,
            secure=self.config.endpoint.startswith(
                "https://"
            ),
        )
        self.bucket_name = self.config.bucket_name
        self.connected = False

    @property
    def credentials(self) -> dict[str, str]:
        return {
            "endpoint_url": self.config.endpoint,
            "aws_access_key_id": self.config.access_key,
            "aws_secret_access_key": self.config.secret_key,
        }

    @property
    def public_url(self) -> str:
        return self.config.public_url

    async def connect(self) -> bool:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.bucket_exists(
                    self.bucket_name
                ),
            )
            self.connected = True
            logger.info(
                f"Connected to MinIO bucket: {self.bucket_name}"
            )
            return True

        except S3Error as e:
            logger.error(f"Connection failed: {str(e)}")
            self.connected = False
            return False

    async def check_bucket_exists(
        self, bucket_name: str
    ) -> bool:
        """Check if a specific bucket exists.

        Args:
            bucket_name: The name of the bucket to check

        Returns:
            bool: True if the bucket exists, False otherwise
        """
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.bucket_exists(
                    bucket_name
                ),
            )
            if result:
                logger.info(f"Bucket exists: {bucket_name}")
            else:
                logger.info(
                    f"Bucket does not exist: {bucket_name}"
                )
            return result
        except S3Error as e:
            logger.error(
                f"Failed to check bucket {bucket_name}: {str(e)}"
            )
            return False

    async def create_bucket(self, bucket_name: str) -> bool:
        """Create a new bucket if it doesn't exist.

        Args:
            bucket_name: The name of the bucket to create

        Returns:
            bool: True if the bucket was created or already exists, False otherwise
        """
        try:
            bucket_exists = await self.check_bucket_exists(
                bucket_name
            )
            if not bucket_exists:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.make_bucket(
                        bucket_name
                    ),
                )
                logger.info(
                    f"Created new bucket: {bucket_name}"
                )
            return True
        except S3Error as e:
            logger.error(
                f"Failed to create bucket {bucket_name}: {str(e)}"
            )
            return False

    async def close(self):
        self.connected = False
        logger.info("Closed MinIO connection")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def upload(
        self,
        path: str,
        buffer: BinaryIO,
        bucket_name: Optional[str] = None,
    ) -> str:
        """Upload a file to MinIO bucket and return the path.

        Args:
            path: The key (path) where the file will be stored in the bucket
            buffer: File-like object to upload
            bucket_name: Optional bucket name to use (defaults to self.bucket_name)

        Returns:
            str: The path of the file in the bucket (not the full URL)
        """
        size = human_size(buffer.getbuffer().nbytes)
        bucket = bucket_name or self.bucket_name
        success = await self.upload_(
            buffer, path, bucket_name=bucket
        )

        if not success:
            raise ValueError(
                f"Failed to upload {path} to MinIO bucket {bucket}"
            )

        logger.info(
            f"Uploaded {path} ({size}) to MinIO bucket {bucket}"
        )
        return path

    async def upload_(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        content_length: Optional[int] = None,
        bucket_name: Optional[str] = None,
    ) -> bool:
        """Upload using native MinIO client"""
        max_retries = 3
        retry_delay = 1
        bucket = bucket_name or self.bucket_name

        file_obj.seek(0)
        content = file_obj.read()
        content_length = len(content)
        buffer = BytesIO(content)
        buffer.seek(0)

        for attempt in range(max_retries):
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.put_object(
                        bucket_name=bucket,
                        object_name=key,
                        data=buffer,
                        length=content_length,
                        content_type=content_type
                        or "application/octet-stream",
                    ),
                )
                logger.info(
                    f"Uploaded {key} ({content_length} bytes) to bucket {bucket}"
                )
                return True
            except S3Error as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Upload failed (attempt {attempt + 1}), retrying: {str(e)}"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(
                        f"Final upload failure after {max_retries} attempts: {str(e)}"
                    )
                    return False
            finally:
                buffer.seek(0)

    async def download_file(
        self,
        key: str,
        file_path: Union[str, Path],
        bucket_name: Optional[str] = None,
    ) -> bool:
        """
        Download a file from MinIO bucket.

        Args:
            key: The key (path) of the file in the bucket
            file_path: Path where the file will be saved
            bucket_name: Optional bucket name to use (defaults to self.bucket_name)

        Returns:
            bool: True if download was successful, False otherwise
        """
        bucket = bucket_name or self.bucket_name
        try:
            file_path = (
                Path(file_path)
                if isinstance(file_path, str)
                else file_path
            )
            file_path.parent.mkdir(
                parents=True, exist_ok=True
            )

            with open(file_path, "wb") as file_data:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.get_object(
                        bucket_name=bucket,
                        object_name=key,
                    ),
                )
                async with response:
                    async for chunk in response.stream(
                        32 * 1024
                    ):
                        file_data.write(chunk)
            logger.info(
                f"Downloaded {key} from bucket {bucket} to {file_path}"
            )
            return True
        except S3Error as e:
            logger.error(
                f"Failed to download {key} from bucket {bucket}: {str(e)}"
            )
            return False

    async def get_object(
        self, key: str, bucket_name: Optional[str] = None
    ) -> Optional[bytes]:
        """Retrieve object using MinIO client

        Args:
            key: The key (path) of the object in the bucket
            bucket_name: Optional bucket name to use (defaults to self.bucket_name)

        Returns:
            Optional[bytes]: The object data or None if not found
        """
        bucket = bucket_name or self.bucket_name
        response = None
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.get_object(
                    bucket_name=bucket,
                    object_name=key,
                ),
            )
            return response.read()
        except S3Error as e:
            logger.error(
                f"Failed to get object {key} from bucket {bucket}: {str(e)}"
            )
            return None
        finally:
            if response:
                response.close()
                response.release_conn()

    async def delete(
        self, key: str, bucket_name: Optional[str] = None
    ) -> bool:
        """
        Delete a file from MinIO bucket.

        Args:
            key: The key (path) of the file to delete in the bucket
            bucket_name: Optional bucket name to use (defaults to self.bucket_name)

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        bucket = bucket_name or self.bucket_name
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.remove_object(
                    bucket_name=bucket,
                    object_name=key,
                ),
            )
            logger.info(
                f"Successfully deleted file {key} from MinIO bucket {bucket}"
            )
            return True
        except S3Error as e:
            logger.error(
                f"Failed to delete file {key} from MinIO bucket {bucket}: {str(e)}"
            )
            return False

    async def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 1000,
        bucket_name: Optional[str] = None,
    ) -> list[dict]:
        """
        List objects in MinIO bucket.

        Args:
            prefix: Prefix to filter objects
            max_keys: Maximum number of keys to return
            bucket_name: Optional bucket name to use (defaults to self.bucket_name)

        Returns:
            list[dict]: List of objects with their metadata
        """
        bucket = bucket_name or self.bucket_name
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.list_objects(
                    bucket_name=bucket,
                    prefix=prefix,
                    recursive=False,
                    max_keys=max_keys,
                ),
            )

            if "Contents" not in response:
                return []

            return response["Contents"]
        except S3Error as e:
            logger.error(
                f"Failed to list objects with prefix {prefix} in bucket {bucket}: {str(e)}"
            )
            return []
