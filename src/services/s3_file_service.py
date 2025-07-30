import boto3
import io
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

class S3FileService:
    """
    Service Class for S3 File Operations.
    """
    def __init__(
            self,
            bucket_name: str,
            aws_access_key_id: str | None = None,
            aws_secret_access_key: str | None = None,
            endpoint_url: str | None = None,
            region_name: str | None = None,
    ) -> None:
        client_kwargs = {}
        if aws_access_key_id:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if region_name:
            client_kwargs["region_name"] = region_name

        self.s3_client: S3Client = boto3.client("s3", **client_kwargs)
        self.bucket_name: str = bucket_name

    def upload_fileobj(self, file_obj: io.BytesIO, source_path: str) -> None:
        try:
            self.s3_client.upload_fileobj(file_obj, self.bucket_name, source_path)
        except ClientError as e:
            raise Exception(f"Failed to upload file to S3: {str(e)}")

    def download_fileobj(self, source_path: str) -> io.BytesIO:
        try:
            file_obj = io.BytesIO()
            self.s3_client.download_fileobj(self.bucket_name, source_path, file_obj)
            file_obj.seek(0)
            return file_obj
        except ClientError as e:
            raise Exception(f"Failed to download file from S3: {str(e)}")

    def delete_file(self, source_path: str) -> None:
        """
        Delete a file from S3
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=source_path)
        except ClientError as e:
            raise Exception(f"Failed to delete file from S3: {str(e)}")

    def create_bucket(self) -> None:
        """
        Create the bucket if it doesn't exist
        """
        try:
            # Get the region from the client configuration
            client_region = self.s3_client.meta.region_name or "us-east-1"
            
            # For us-east-1, don't specify CreateBucketConfiguration
            if client_region == "us-east-1":
                self.s3_client.create_bucket(Bucket=self.bucket_name)
            else:
                # For all other regions, specify the LocationConstraint
                self.s3_client.create_bucket(
                    Bucket=self.bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': client_region}
                )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if (
                    error_code != "BucketAlreadyOwnedByYou"
                    and error_code != "BucketAlreadyExists"
            ):
                raise Exception(f"Failed to create bucket: {str(e)}")

    def delete_bucket(self) -> None:
        """Delete the bucket and all its contents"""
        try:
            # First delete all objects in the bucket
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            if "Contents" in response:
                objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name, Delete={"Objects": objects}
                )

            # Then delete the bucket itself
            self.s3_client.delete_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            raise Exception(f"Failed to delete bucket: {str(e)}")