import boto3
from botocore.client import Config
from os import getenv, path
import logging
import asyncio


class CdnSpacesClient:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        session = boto3.session.Session()
        self.client = session.client('s3',
                                region_name='nyc3',
                                endpoint_url='https://nyc3.digitaloceanspaces.com',
                                aws_access_key_id=getenv("cdn_id"),
                                aws_secret_access_key=getenv("cdn_sec"),
                                config=Config(signature_version='s3v4')
                                )

    async def cdn_upload_video(self, file_path, storage_type="temp") -> tuple[bool, str]:
        filename = path.basename(file_path)
        self.logger.info(f"Uploading video {file_path} to CDN...")
        try:
            # Read file in a non-blocking way
            with open(file_path, 'rb') as file:
                video_data = file.read()

            # Call put_video in a thread pool to avoid blocking the event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self.put_video,
                video_data,
                filename,
                storage_type
            )
            return result
        except Exception as e:
            self.logger.error(f"Error uploading video {file_path}: {str(e)}")
            return False, str(e)

    async def upload_webp(self, file_path: str):
        filename = file_path.split("/")[-1]
        cdn_patj = f"img/{filename}"
        self.logger.info(f"Uploading {filename} to {cdn_patj}")
        with open(file_path, 'rb') as file:
            img_data = file.read()
        try:
            self.client.put_object(
                Bucket='clyppy',
                Key=cdn_patj,
                Body=img_data,
                ACL='public-read',
                ContentType='image/webp'
            )
            return True, f"https://cdn.clyppy.io/{cdn_patj}"
        except Exception as e:
            self.logger.info(f"Error uploading {filename}: {str(e)}")
            return False, str(e)

    def put_video(self, video_data, filename, storage_type="temp") -> tuple[bool, str]:
        object_key = f"{storage_type}/{filename}"
        cdn_file_url = f"https://cdn.clyppy.io/{object_key}"
        self.logger.info(f"Uploading {filename} to {cdn_file_url}")

        # Upload the file
        try:
            self.client.put_object(
                Bucket='clyppy',
                Key=object_key,
                Body=video_data,
                ACL='public-read',
                ContentType='video/mp4'
            )
            self.logger.info(f"Uploaded {filename} to {cdn_file_url}")
            return True, cdn_file_url
        except Exception as e:
            self.logger.error(f"Error uploading {filename}: {str(e)}")
            return False, str(e)
