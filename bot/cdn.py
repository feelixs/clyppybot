import boto3
from botocore.client import Config
from os import getenv


class CdnSpacesClient:
    def __init__(self):
        session = boto3.session.Session()
        self.client = session.client('s3',
                                region_name='nyc3',
                                endpoint_url='https://nyc3.digitaloceanspaces.com',
                                aws_access_key_id=getenv("SPACES_CDN_KEY"),
                                aws_secret_access_key=getenv("SPACES_CDN_SECRET"),
                                config=Config(signature_version='s3v4')
                                )

    def put_video(self, video_data, platform, video_id, filename, storage_type="temp"):
        object_key = f"{storage_type}/{platform}/{video_id}/{filename}"

        # Upload the file
        try:
            self.client.put_object(
                Bucket='clyppy',
                Key=object_key,
                Body=video_data,
                ACL='public-read',
                ContentType='video/mp4'
            )
            return True, f"https://clyppy.nyc3.cdn.digitaloceanspaces.com/{object_key}"
        except Exception as e:
            return False, str(e)
