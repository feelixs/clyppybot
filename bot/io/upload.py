from bot.classes import UploadFailed
from typing import Dict
from math import ceil
from bot.io import get_aiohttp_session
import base64
import os
import uuid


MAX_CLYPPYIO_UPLOAD_SIZE = 70_000_000


async def upload_video_in_chunks(file_path, logger, chunk_size, total_size=None, file_data=None, delete_soon=False):
    file_id = str(uuid.uuid4())
    if total_size is None:
        # Read the file and get total size
        with open(file_path, 'rb') as f:
            file_data = f.read()
        total_size = len(file_data)
        logger.info(f"Uploading {os.path.basename(file_path)} ({total_size / 1024 / 1024:.1f}MB)")

    total_chunks = ceil(total_size / chunk_size)
    logger.info(f"Will upload in {total_chunks} chunks")

    async with get_aiohttp_session() as session:
        for chunk_number in range(total_chunks):
            start = chunk_number * chunk_size
            end = min(start + chunk_size, total_size)
            chunk = file_data[start:end]

            chunk_b64 = base64.b64encode(chunk).decode('utf-8')

            headers = {
                'X-API-Key': os.getenv('clyppy_post_key'),
                'X-Chunk-Number': str(chunk_number),
                'X-Total-Chunks': str(total_chunks),
                'X-File-ID': file_id
            }

            data = {
                'chunked': True,
                'file': chunk_b64,
                'filename': os.path.basename(file_path),
                'delete_soon': delete_soon
            }

            logger.info(f"Uploading chunk {chunk_number + 1}/{total_chunks} ({len(chunk) / 1024 / 1024:.1f}MB)")

            async with session.post(
                    'https://clyppy.io/api/addclip/',
                    json=data,
                    headers=headers
            ) as response:
                if response.status != 200:
                    logger.info(f"Failed to upload chunk {chunk_number + 1}: {response.status}")
                    logger.info(await response.text())
                    return None

                r = await response.json()
                if chunk_number == total_chunks - 1:
                    if r['success']:
                        return r
                    else:
                        logger.info(f"Server reported error on chunk {chunk_number + 1}: {r.get('error')}")
                        raise UploadFailed
                elif not r['success']:
                    logger.info(f"Server reported error on chunk {chunk_number + 1}: {r.get('error')}")
                    raise UploadFailed

                logger.info(f"Chunk {chunk_number + 1} uploaded successfully")

    logger.info("An unknown error occurred while uploading the video.")
    raise UploadFailed


async def upload_video(video_file_path, logger, delete_soon=False) -> Dict:
    with open(video_file_path, 'rb') as f:
        file_data = f.read()
    total_size = len(file_data)

    logger.info(f"Uploading {os.path.basename(video_file_path)} ({total_size / 1024 / 1024:.1f}MB)")
    if os.path.getsize(video_file_path) > MAX_CLYPPYIO_UPLOAD_SIZE:
        return await upload_video_in_chunks(
            file_path=video_file_path,
            logger=logger,
            chunk_size=MAX_CLYPPYIO_UPLOAD_SIZE,
            total_size=total_size,
            file_data=file_data,
            delete_soon=delete_soon
        )

    with open(video_file_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode()

    data = {
        'chunked': False,
        'file': file_data,
        'filename': os.path.basename(video_file_path),
        'delete_soon': delete_soon
    }

    async with get_aiohttp_session() as session:
        try:
            headers = {
                'X-API-Key': os.getenv('clyppy_post_key'),
                'Content-Type': 'application/json'
            }
            async with session.post(
                    url='https://clyppy.io/api/addclip/',
                    json=data,
                    headers=headers
            ) as response:
                logger.info(await response.text())
                r = await response.json()
                if r['success']:
                    return r
                else:
                    raise UploadFailed
        except Exception as e:
            raise e

