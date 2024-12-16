import functions_framework
from google.cloud import storage
from flask import jsonify, send_file
import tempfile
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

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

'''
input: json of the form:
    {scan_id: <string>,
    return_file: 'Y' or 'N',
    file_type: 'text', 'nifti' or 'dicom'}

If return_file = 'Y', return the file contents (only applicable for nifti and text files)
If return_file = 'N', it returns a json containing the file data (scan_id, time_stamp, scan_type, patient_id, report)

Note: Cloud function had to be initialised to a memory allocation of 512 MiB - 256MiB was insufficient 
'''
@functions_framework.http
def download(request):
    request_json = request.get_json(silent=True)
    scan_id = request_json.get('scan_id')
    return_file = request_json.get('return_file')
    file_type = request_json.get('file_type')

    if not scan_id or not return_file or not file_type:
      return "scan_id/file/file_type not provided", 400


    # retrieve scan information
    scans_ref = db.collection("scans")
    query = scans_ref.where('scan_id', '==', scan_id)
    results = query.stream()    #[{'timestamp': '2024-07-09T13:28', 'scan_type': ' MRI', 'patient_id': 1, 'report': 'a beautiful scan', 'scan_id': 69}]

    # scan_id should be unique, so this is ASSUMED to only have one item in it
    scan_data = []
    for doc in results:
        scan_data.append(doc.to_dict())

    # return scan_data
    if return_file == 'N':
        return jsonify(scan_data[0]), 200

    elif return_file == 'Y':
        if file_type == 'nifti':
            bucket_name = NIFTI_BUCKET_NAME
            file_name = scan_data[0]['scan_id'] + '.nii.gz'
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)

            # Create a temporary file to download the blob content
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            blob.download_to_filename(temp_file.name)

            # Return the file in the response
            return send_file(temp_file.name, as_attachment=True, download_name=file_name)

        elif file_type == 'text':
            bucket_name = TEXT_BUCKET_NAME
            file_name = scan_data[0]['scan_id'] + '.txt'
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)

            # Create a temporary file to download the blob content
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            blob.download_to_filename(temp_file.name)

            # Return the file in the response
            return send_file(temp_file.name, as_attachment=True, download_name=file_name)
        
        else:
            return 'invalid file type: ' + file_type, 400

        

