import functions_framework
from google.cloud import storage
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import json
import random
import time
import zipfile
import os
import pydicom
from googleapiclient.discovery import build
import google.auth
import time
import uuid


# Initialize Firebase Admin SDK (only required once per function instance)
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'apt-vine-428509-d2',
})

db = firestore.client()

# TODO: update these with your bucket names
TEXT_BUCKET_NAME = 'text_file_store'
NIFTI_BUCKET_NAME = 'text_file_store'
DICOM_BUCKET_NAME = 'dicom_bucket_store'

# TODO: update this value
DICOM_STORE_PATH = 'projects/apt-vine-428509-d2/locations/europe-west2/datasets/dicom-dataset/dicomStores/dicom-datastore'

'''
Note: file types currently supported = .txt, .nii.gz, .zip of .dcm files
input: data is passed in the 'files' section of the POST - this better allows us to send multiple things
the files section is one of the following 2 formats:
    {patient_data: <json>}
    {file_data: <json>, file: (<the file name>, <the file itself>)}

If patient data gets passed in, it must be added to the firestore database table 'users'
If file data gets passed in:
    the data must get added to the firestore database table 'scans'
    if the file is a .txt or a .nii.gz, then the file must then get put into the correct bucket (we provide it with a UID and save this label in the database as a reference)
    if the file is a .zip of .dcm files:
        the .dcm files are temporarily put into a bucket and then that bucket is loaded into a specialised DICOM store via the Google Health API
        the DICOM store takes care of sorting them and storing them correctly
        the bucket is then emptied - we must poll the previous step to make sure it is complete to avoid a race condition
        Each file is given a unique prefix - unique to the user's upload. We then make sure that the DICOM store only uploads files with that prefix for a user, and then only
        deletes files from the bucket with that prefix to avoid race conditions
'''

@functions_framework.http
def upload(request):
    response_text = ""
    if request.method != 'POST':
        return 'Please send a POST request', 405
    
    # data passed in corresponds to a patient entry
    if 'patient_data' in request.files:
        patient_data = json.loads(request.files['patient_data'].read())
        if not all(key in patient_data for key in ('firstname', 'lastname', 'dob', 'sex')):
            return "Incomplete patient data", 400

        # Create new unique patient_id
        patient_id = str(int(time.time() * 1000)) + str(random.randint(1, 1_000_000))

        # Write data to Firestore
        # ensure that the patient id is the same as the document id - this assumption must be true for use elsewhere
        doc_ref = db.collection('users').document(patient_id)
        doc_ref.set({
            'patient_id':patient_id,
            'firstname': patient_data['firstname'].lower(),
            'lastname': patient_data['lastname'].lower(),
            'dob': patient_data['dob'],
            'sex': patient_data['sex'],
            'user_type': 'patient',
            'email': '',
            'admin': 'N'
        })
        response_text += "Patent data written."


    if ('file' in request.files and not('file_data' in request.files) or ('file_data' in request.files and not('file' in request.files))):
        return 'one of scan and its data missing', 400
    
    elif 'file' in request.files and 'file_data' in request.files:
        scan = request.files['file']
        file_data = json.loads(request.files['file_data'].read())

        if not all(key in file_data for key in ('patient_id', 'timestamp', 'file_type', 'report')):
            response_text += "Incomplete scan data"
            return response_text, 400

        file_type = file_data['file_type']

        if file_type == 'nifti' or file_type == 'text':        
            scan_id = str(int(time.time() * 1000)) + str(random.randint(1, 1_000_000))
            # Write data to Firestore
            doc_ref = db.collection('scans').document()
            doc_ref.set({
                'scan_id': scan_id, 
                'patient_id': file_data['patient_id'],
                'timestamp': file_data['timestamp'],
                'file_type': file_data['file_type'],
                'report': file_data['report']
            })

            # Upload file to correct bucket

            if file_type == 'nifti':
                # Create a client
                storage_client = storage.Client()

                # Get the bucket that the file will be uploaded to
                bucket = storage_client.bucket(NIFTI_BUCKET_NAME)

                # Create a new blob and upload the file's content
                blob = bucket.blob(str(scan_id) + ".nii.gz")
                blob.upload_from_string(
                    scan.read(),
                    content_type=scan.content_type
                )

            elif file_type == 'text':
                # Create a client
                storage_client = storage.Client()

                # Get the bucket that the file will be uploaded to
                bucket = storage_client.bucket(TEXT_BUCKET_NAME)

                # Create a new blob and upload the file's content
                blob = bucket.blob(str(scan_id) + ".txt")
                blob.upload_from_string(
                    scan.read(),
                    content_type=scan.content_type
                )

            response_text += " Scan data saved to database and bucket."

        elif file_type == 'dicom':
            zippedFile = request.files['file']
            extractionPath = 'tmp'  # temporary directory for file extraction

            # unzip file
            os.makedirs(extractionPath, exist_ok=True)
            with zipfile.ZipFile(zippedFile, 'r') as zip_ref:
                zip_ref.extractall(extractionPath)

            # create a client
            storage_client = storage.Client()

            # Get the bucket that the file will be uploaded to
            bucket = storage_client.bucket(DICOM_BUCKET_NAME)

            # the prefix unique to the user - this is to allow concurrent uploads to happen safely without race conditions
            prefix = str(uuid.uuid4())

            # upload all the files in the zip folder to a temporary bucket
            for entry in os.listdir(extractionPath):
                try:
                    # generate UID for file to be stored into bucket
                    id = str(int(time.time() * 1000)) + str(random.randint(1, 1_000_000))
                    # Create a new blob and upload the file's content
                    blob = bucket.blob(prefix + "/" + str(id) + ".dcm")
                    file_path = os.path.join(extractionPath, entry)
                    with open(file_path,'rb') as file:
                        blob.upload_from_file(
                            file,
                            content_type='application/dicom'
                        )

                    # update firestore if the series ID is new
                    if file_path != 'tmp/__MACOSX':
                        # Only add a new entry to the firestore if that series ID is new (each one is GLOBALLY unique)
                        currentSeries = pydicom.dcmread(file_path).SeriesInstanceUID
                        currentStudy = pydicom.dcmread(file_path).StudyInstanceUID
                        scans_ref = db.collection('scans')
                        query_result = list(scans_ref.where('series_id', '==', currentSeries).stream())

                        # if result is empty it means that the series ID is new, so we need to add a row to the firestore collection 'scans'
                        if not query_result:
                            doc_ref = db.collection('scans').document()
                            doc_ref.set({
                                'scan_id': str(int(time.time() * 1000)) + str(random.randint(1, 1_000_000)),
                                'series_id': currentSeries,
                                'study_id': currentStudy,
                                'patient_id': file_data['patient_id'],
                                'timestamp': file_data['timestamp'],
                                'file_type': file_data['file_type'],
                                'report': file_data['report']
                            })
                    
                    # stop the temporary files from persisting - this avoids duplication in the bucket
                    os.remove(file_path)

                # sometimes the extraction process creates arbitrary directories 
                except IsADirectoryError:
                    pass
    
            # load the bucket contents into the DICOM store
            bucket_name = DICOM_BUCKET_NAME
            target_bucket_files = bucket_name + '/' + prefix + '/*.dcm'    # wildcard '*' matches all .dcm files
            gcs_uri = f'gs://{target_bucket_files}'

            dicom_store_path = DICOM_STORE_PATH
            request_body = {'gcsSource': {'uri':gcs_uri}}

            credentials,project = google.auth.default()
            healthcare_service = build('healthcare', 'v1', credentials=credentials)
            request = healthcare_service.projects().locations().datasets().dicomStores().import_(name=dicom_store_path, body=request_body)
            response = request.execute()
            operation_name = response['name']

            # NOTE:it is vital that the DICOM store imports the whole bucket before we start deleting from the bucket - the DICOM store takes longer to import everything but relinquishes the lock, leading to race conditons if we do not poll it
            while True:
                result = healthcare_service.projects().locations().datasets().operations().get(name=operation_name).execute()
                if 'done' in result and result['done']:
                    break
                else:
                    time.sleep(1)

            # empty bucket - this stops future uploads duplicating work by re-adding old DICOMs to the store
            # even though the API discards the duplicates, this eats into the quota and is inefficient
            bucket = storage_client.bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=prefix)
            for blob in blobs:
                blob.delete()

        else:
            return "invalid file type:" + file_type, 400


    return response_text, 200