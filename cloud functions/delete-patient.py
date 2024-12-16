import functions_framework
from google.cloud import storage
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import requests

# Initialize Firebase Admin SDK (only required once per function instance)
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'apt-vine-428509-d2',
})

db = firestore.client()

# TODO: Change URL to that of the delete-files cloud function
DELETE_FILES_URL = 'https://europe-west2-apt-vine-428509-d2.cloudfunctions.net/delete-files'

# Initialize the Cloud Storage client
storage_client = storage.Client()

'''
input: json of the form {'patient_id' : <string>}

enumerates the files assocaited with the provided patient - it then calls the delete-files cloud function on each of them
once all the files assocaited with a patient have been deleted, it then removes them from the users table in the firestore
'''

@functions_framework.http
def delete_patient(request):
    request_json = request.get_json(silent=True)
    patient_id = request_json.get('patient_id')

    if not patient_id:
        return "no patient_id provided", 403

    # find all the files assocaited with a given patient    
    scans_ref = db.collection('scans')
    query_result = scans_ref.where('patient_id', '==', patient_id)
    result = query_result.stream()

    scan_data = []
    for doc in result:
        scan_data.append(doc.to_dict())

    # call delete-files cloud function to delete all the files associated with a given patient
    for scan in scan_data:
        scan_id = scan['scan_id']
        response = requests.post(DELETE_FILES_URL, json={'scan_id': scan_id})

    # delete patient data from firestore
    users_ref = db.collection('users')
    users_doc_ref = users_ref.document(patient_id)
    users_doc_ref.delete()

    return f'patient {patient_id} and all their files have been deleted', 200