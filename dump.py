import os
import subprocess
import tarfile
import datetime
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import pytz
import logging
import time
import random

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

log_file_path = os.getenv('LOG_FILE_PATH', '/dev/stdout')
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Set the service account credentials file path
SERVICE_ACCOUNT_FILE = 'pg-devops-infra.json'

# ID of the target folder in Google Drive
FOLDER_ID = '1UQIThv0UwNWUnYHzj_2mkLFn-DAvcKj_'

# Authenticate using the service account credentials
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/drive']
)


# Function to delete a file and handle errors
def delete_file(file_path):
    try:
        os.remove(file_path)
        logger.info(f"Deleted file: {file_path}")
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")

# Function to upload file with retries
def upload_file_with_retries(file_path, file_metadata, retries=5):
    # Create a Drive API client
    drive_service = build('drive', 'v3', credentials=credentials)
    media = MediaFileUpload(file_path, resumable=True)
    request = drive_service.files().create(body=file_metadata, media_body=media, fields='id')
    response = None
    attempt = 0
    while response is None and attempt < retries:
        try:
            logger.info(f"Uploading file {os.path.basename(file_path)} (attempt {attempt + 1})")
            response = request.execute()
            logger.info(f"Upload successful: {response}")
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            if error.resp.status in [500, 502, 503, 504]:
                attempt += 1
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                raise
    if response is None:
        raise Exception("Failed to upload file after retries")
    return response

def take_dump(dump_type, namespace, pod_name):
    try:
        # Create a Drive API client
        drive_service = build('drive', 'v3', credentials=credentials)
        # Get a list of all files in the target folder
        results = drive_service.files().list(q=f"'{FOLDER_ID}' in parents",
                                             fields="files(id, name, createdTime)").execute()
        files = results.get('files', [])

        # Calculate the current time in IST (Indian Standard Time)
        ist_timezone = pytz.timezone('Asia/Kolkata')
        current_time = datetime.datetime.now(ist_timezone)
        two_days_ago = current_time - datetime.timedelta(minutes=2880)

        # Iterate over the files and delete those older than 2 days
        for file in files:
            file_name = file['name']
            file_id = file['id']
            created_time = file['createdTime']

            # Convert the ISO formatted timestamp to a datetime object in IST
            created_timestamp = datetime.datetime.strptime(created_time, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)
            created_timestamp = created_timestamp.astimezone(ist_timezone)

            if created_timestamp < two_days_ago:
                # Delete the file
                drive_service.files().delete(fileId=file_id).execute()
                logger.info(f"Deleted file from Google Drive: {file_name}")
            else:
                logger.info(f"File not eligible for deletion from Google Drive: {file_name}")

        # Set the output directory for dumps
        OUTPUT_DIR = '/tmp'

        # Create the output directory if it doesn't exist
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Set the timestamp for the dump file names
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M')

        if dump_type == "thread" and pod_name is not None and pod_name != "":
            try:
                # Take a thread dump using jstack command within the pod
                thread_dump_file = os.path.join(OUTPUT_DIR, f'{pod_name}_threaddump_{timestamp}.txt')
                proc = subprocess.run(['kubectl', 'exec', '-n', namespace, pod_name, '--', 'jstack', '1'],
                                      stdout=subprocess.PIPE, check=True, universal_newlines=True)
                with open(thread_dump_file, 'w') as file:
                    file.write(proc.stdout)
                logger.info('Thread dump done')
            except subprocess.CalledProcessError as e:
                logger.error(f"Error taking thread dump: {e}")
                return None

        elif dump_type == "heap" and pod_name is not None and pod_name != "":
            try:
                # Take a heap dump using jmap command within the pod
                heap_dump_file = os.path.join(OUTPUT_DIR, f'{pod_name}_heapdump_{timestamp}.hprof')
                subprocess.run(['kubectl', 'exec', '-n', namespace, pod_name, '--', 'jmap', '-dump:format=b,file=/tmp/heapdump', '1'], check=True)
                subprocess.run(['kubectl', 'cp', f'{namespace}/{pod_name}:/tmp/heapdump', heap_dump_file], check=True)
                # Delete the file from the pod
                delete_command = f'kubectl exec -n {namespace} {pod_name} -- rm /tmp/heapdump'
                subprocess.run(delete_command, shell=True, check=True)
                pod_terminate = f'kubectl -n {namespace} delete po {pod_name}'
                subprocess.run(pod_terminate, shell=True, check=True)
                logger.info('File deleted from pod')
                logger.info('Heap dump done')
            except subprocess.CalledProcessError as e:
                logger.error(f"Error taking heap dump: {e}")
                return None

        else:
            logger.error("Invalid dump type. Use 'heap' or 'thread'.")
            return None

        # Create a tar.gz file for the dumps
        compressed_file = os.path.join(OUTPUT_DIR, f'{pod_name}_{dump_type}_dumps_{timestamp}.tar.gz')
        with tarfile.open(compressed_file, 'w:gz') as tar:
            if dump_type == "heap":
                tar.add(heap_dump_file, arcname=f'{pod_name}_heapdump_{timestamp}.hprof')
            elif dump_type == "thread":
                tar.add(thread_dump_file, arcname=f'{pod_name}_threaddump_{timestamp}.txt')
        logger.info('Compression completed.')

        # Upload the compressed file to Google Drive with retries
        file_metadata = {'name': os.path.basename(compressed_file), 'parents': [FOLDER_ID]}
        file = upload_file_with_retries(compressed_file, file_metadata)

        # Print the link to the uploaded file
        file_id = file.get('id')
        file_link = f"https://drive.google.com/uc?export=download&id={file_id}"
        logger.info(f"File uploaded successfully to Google Drive. Link: {file_link}")
        logger.info("File will be deleted after 48 hours")

        # Clean up the temporary dump files and compressed file
        if dump_type == "heap":
            delete_file(heap_dump_file)
        elif dump_type == "thread":
            delete_file(thread_dump_file)
        delete_file(compressed_file)
        return file_link

    except Exception as e:
        logger.error(f"Error in take_dump: {e}")
        return None