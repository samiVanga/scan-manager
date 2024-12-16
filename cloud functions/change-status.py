import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Initialize Firebase Admin SDK (only required once per function instance)
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'apt-vine-428509-d2',
})

db = firestore.client()

'''
input: json of the form {'patient_id': <string>, 'new_status': <one of 'doctor', 'admin', 'patient'>}

IMPORTANT: pateint < doctor < admin. If someone is an admin they are also a doctor. But if someone is just a doctor, then they are NOT an admin
'''
def change_status(request):
    request_json = request.get_json(silent=True)
    patient_id = request_json.get('patient_id')
    new_status = request_json.get('new_status')

    if not patient_id:
        return 'no patient_id provided', 400
    
    if not new_status:
        return 'new status is missing', 400
    
    users_ref = db.collection('users')
    users_doc_ref = users_ref.document(patient_id)

    if new_status == 'patient' or new_status == 'doctor':
        users_doc_ref.update({'user_type': new_status, 'admin': 'N'})
    
    elif new_status == 'admin':
        users_doc_ref.update({'admin': 'Y', 'user_type': 'doctor'})

    else:
        return 'new status is invalid', 400
    
    return f'user {patient_id} had status changed to {new_status}', 200