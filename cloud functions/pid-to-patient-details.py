import functions_framework
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from flask import jsonify

# Initialize Firebase Admin SDK (only required once per function instance)
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'apt-vine-428509-d2',
})

db = firestore.client()

@functions_framework.http
def get_user_data(request):
    request_json = request.get_json(silent=True)
    request_args = request.args

    # Check if the request contains a 'firstname' parameter
    if request_json and 'patient_id' in request_json:
        patient_id = request_json['patient_id']
    elif request_args and 'patient_id' in request_args:
        patient_id = request_args['patient_id']
    else:
        return jsonify({"error": "patient_id parameter is required"}), 400

    # Query Firestore for scans where the 'patient_id' field matches exactly
    try:
        users_ref = db.collection('users')  # Replace 'users' with your collection name
        query = users_ref.where('patient_id', '==', patient_id)
        results = query.stream()

        # Extract data from query results
        user_data = []
        for doc in results:
            user_data.append(doc.to_dict())

        return jsonify(user_data), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500