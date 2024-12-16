import functions_framework
from google.cloud import storage
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import google.auth
from google.auth.transport import requests

# Initialize Firebase Admin SDK (only required once per function instance)
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'apt-vine-428509-d2',
})

db = firestore.client()

# Initialize the Cloud Storage client
storage_client = storage.Client()

# TODO: update these with your bucket names
TEXT_BUCKET_NAME = 'text_file_store'
NIFTI_BUCKET_NAME = 'text_file_store'
DICOM_BUCKET_NAME = 'dicom_bucket_store'

# TODO: update varaible 'dicomeweb_path' to reflect your project


'''
input: json of the form {scan_id: <string>}
This deletes files from the system
if a given file is .txt or .nii.gz, it must be removed from both the firestore collection 'scans' and the corresponding bucket
if it is .dcm, it must be removed from the firestore collection 'scans' and from the DICOM store (its bucket was emptied in the upload phase already):
    i.e. we delete all the scans from the DICOM store with the same series UID as the selected scan - it makes no sense to partially delete a series
'''
@functions_framework.http
def delete(request):
    request_json = request.get_json(silent=True)
    scan_id = request_json.get('scan_id')

    if not scan_id:
        return 'scan_id not provided', 418  #teapot
    
    scans_ref = db.collection('scans')
    query_result = scans_ref.where('scan_id', '==', scan_id)
    result = query_result.stream() #the scan_id is assumed to be unique hence why we can just pull out the first result
    
    scan_data = []
    for doc in result: # IT IS CRUCIAL THERE IS ONLY ONE DOC IN RESULT
        document_id = doc.id
        scan_data.append(doc.to_dict())


    scan_data = scan_data[0]

    file_type = scan_data['file_type']

    if file_type == 'text':
        # delete from bucket
        bucket_name = TEXT_BUCKET_NAME
        blob_name = scan_id + '.txt'
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()

        #delete firestore entry
        doc_ref = scans_ref.document(document_id)
        doc_ref.delete()

        return f'text file {blob_name} deleted', 200
    
    elif file_type == 'nifti':
        # delete from bucket
        bucket_name = NIFTI_BUCKET_NAME
        blob_name = scan_id + '.nii.gz'
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()

        #delete firestore entry
        doc_ref = scans_ref.document(document_id)
        doc_ref.delete()

        return f'nifti file {blob_name} deleted', 200

    elif file_type == 'dicom':
        bucket_name = DICOM_BUCKET_NAME

        credentials,project = google.auth.default()
        scoped_credentials = credentials.with_scopes(["https://www.googleapis.com/auth/cloud-platform"])
        # Creates a requests Session object with the credentials.
        session = requests.AuthorizedSession(scoped_credentials)

        study_id = scan_data['study_id']
        series_id = scan_data['series_id']
        # location of the series to delete
        dicomweb_path = f'https://healthcare.googleapis.com/v1/projects/apt-vine-428509-d2/locations/europe-west2/datasets/dicom-dataset/dicomStores/dicom-datastore/dicomWeb/studies/{study_id}/series/{series_id}'

        # Sets the required application/dicom+json; charset=utf-8 header on the request
        headers = {"Content-Type": "application/dicom+json; charset=utf-8"}

        response = session.delete(dicomweb_path, headers=headers)
        response.raise_for_status()

        #delete firestore entry
        doc_ref = scans_ref.document(document_id)
        doc_ref.delete()

        return f'dicom file {scan_id}.dcm deleted', 200
    
    else:
        return 'unsupported file type: ' + file_type, 400