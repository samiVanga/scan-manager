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
    if request_json and 'name' in request_json:
        name = request_json['name'].lower()
    elif request_args and 'name' in request_args:
        name = request_args['name'].lower()
    else:
        return jsonify({"error": "firstname parameter is required"}), 400

    # Query Firestore for documents where the 'firstname' field matches the user's input
    try:
        users_ref = db.collection('users')  # Replace 'users' with your collection name
        query = users_ref.where('firstname', '>=', name).where('firstname', '<=', name + '~')
        results = query.stream()
        last= users_ref.where('lastname', '>=', name).where('lastname', '<=', name + '~')
        lresults=last.stream()
        

        # Extract data from query results
        user_data = []
        unique=set()
        for doc in results:
            user_data.append(doc.to_dict())
            unique.add(doc.id)
        
        for doc in lresults:
          if doc.id not in unique:
            user_data.append(doc.to_dict())
            unique.add(doc.id)

        return jsonify(user_data), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

