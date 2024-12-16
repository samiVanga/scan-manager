import datetime
from io import BytesIO
import os
from flask import Flask, Response, flash, g, redirect, render_template, request, url_for, session, jsonify
import nibabel as nib
import numpy as np
from PIL import Image
import requests 
import json
from app_helper_functions import *
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
import firebase_admin
from firebase_admin import credentials, auth, firestore


ALLOWED_FILE_TYPES = {"nifti", "text", "dicom"}

# Define URLs for cloud functions
def load_urls(path):
    with open(path) as f:
        return json.load(f)
urls = load_urls("url_config.json")

# Create flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'LIT$)M8vQtqX9J4' # Secret key for encrypting client-side communications

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = ''

# TODO: update with path to your key
cred = credentials.Certificate(os.path.join(app.root_path, 'static/keys/apt-vine-428509-d2-firebase-adminsdk-ma4e3-c19e22a4e6.json'))
firebase_admin.initialize_app(cred)

firestore_db = firestore.client()

# user class that persists while a suer is logged in - can be referenced at any point by 'current_user'
class User(UserMixin):
    def __init__(self, patient_id, email, firstname, lastname, user_type, dob, sex, admin):
        self.id = patient_id
        self.patient_id = patient_id
        self.email = email
        self.firstname = firstname
        self.lastname = lastname
        self.user_type = user_type
        self.dob = dob
        self.sex = sex
        self.admin = admin

@login_manager.user_loader
def load_user(patient_id):
    user_doc = firestore_db.collection('users').document(patient_id).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return User(patient_id=user_data['patient_id'], email=user_data['email'], firstname=user_data['firstname'], lastname=user_data['lastname'], user_type=user_data['user_type'], dob=user_data['dob'], sex=user_data['sex'], admin=user_data['admin'])
    return None

@app.route('/login', methods=['POST'])
def login_post():
    id_token = request.json['idToken']
    decoded_token = auth.verify_id_token(id_token)
    patient_id = decoded_token['uid']
    email = decoded_token['email']
    name = decoded_token['name']
    names = name.split(' ',1)
    if len(names) == 1:                         # if no lastname is asscoatied with account give the empty string as the lastname 
        names.append('')
    first_name = names[0].lower()
    last_name = names[1].lower()

    user_doc = firestore_db.collection('users').document(patient_id).get()
    if not user_doc.exists:
        user_type = 'patient'   # default to patient
        dob = ''
        sex = ''
        admin= 'N'              # default to non-admin
        firestore_db.collection('users').document(patient_id).set({
            'patient_id': patient_id,
            'email': email,
            'firstname': first_name,
            'lastname': last_name,
            'user_type': user_type,
            'dob': dob,
            'sex': sex,
            'admin': 'N'
        })
    else:
        user_type = user_doc.to_dict().get('user_type', '')
        dob = user_doc.to_dict().get('dob', '')
        sex= user_doc.to_dict().get('sex', '')
        admin = user_doc.to_dict().get('admin', '')

    user = User(patient_id=patient_id, email=email, firstname=first_name, lastname=last_name, user_type=user_type, dob=dob, sex=sex, admin=admin)
    login_user(user)

    return jsonify({'success': True})

@app.route('/profile_settings_redirect')
@login_required
def profile_settings_redirect():
    user = current_user
    if user.dob == '': #first time logging in so this needs to be set
        return redirect(url_for('select_user_type'))
    else:
        return redirect(url_for('index'))


@app.route('/profile_settings', methods=['GET', 'POST'])
@login_required
def profile_settings():
    user = current_user
    if request.method == 'POST':
        if user.user_type == '':
            user_type = 'patient'
        else:
            user_type = user.user_type

        dob = request.form.get('dob')
        user.dob = dob

        sex = request.form.get('sexInput')
        user.sex = sex

        # Update Firestore
        firestore_db.collection('users').document(user.patient_id).update({
            'user_type': user_type,
            'dob': dob,
            'sex': sex
        })

        return redirect(url_for('index'))
    else:
        return "seriously bad error", 500

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    return render_template('index.html')

# Make current user a global variable
@app.context_processor
def inject_user():
    return dict(current_user=g.get('current_user'))

# Make current user a global variable
@app.before_request
def load_user_to_context_processor():
    g.current_user = current_user


@app.route('/slice-to-png/<scan_id>/<slice_no>')
@login_required
def slice_to_PNG(scan_id, slice_no):
    """
    Extract a PNG image of a specified slice of a NIfTI scan file

    Parameters:
    scan_id (str): Identifier for the NIfTI scan file. This must match file entry in datastore.
    slice_no (str): The index of the slice to convert to PNG.

    Returns:
    Response: A Flask Response object containing the PNG image data as bytes with
              mimetype "image/png".

    Notes:
    - This route assumes the NIfTI scan file is stored in the same directory, under the name
      "temp_scan_file.nii.gz". Adjust `file_path` accordingly if the file location
      or naming convention changes.
    """
    file_path = f"temp_scan_file.nii.gz"

    scan = nib.load(file_path).get_fdata()
    # total_slices = scan.shape[2] # TODO: ADD COMPATIBILITY WITH SCANS OF MORE THAN 3 DIMENSIONS
    img = convert_nii_slice_to_png(scan, int(slice_no))

    # Convert PIL image to byte array
    img_io = BytesIO()
    img.save(img_io, "PNG")
    img_data = img_io.getvalue()

    return Response(img_data, mimetype="image/png")

@app.route('/patient-search', methods=['GET', 'POST'])
@login_required
def patient_search():
    """
    Perform a search for patient data based on a name query using a Cloud Function endpoint.

    Methods:
    - GET: Renders the patient search form.
    - POST: Sends a POST request to a Cloud Function endpoint with the provided
      patient name query, retrieves the results, and renders them on the patient
      search template

    Returns:
    flask.Response: A rendered HTML template 'patient-search.html' displaying
                    the search results retrieved from the Cloud Function endpoint.
    """
    if not (is_admin(current_user) or is_doctor(current_user)):
        return "Access Denied", 403

    results = []
    if request.method == 'POST':
        # Make POST request to datastore via cloud function
        data = {
            'name': request.form.get('patient-search-query', ''),
            'sort_by': request.form.get('sort-by-dropdown', 'lastname'),
            'sort_order': 'asc'
            }
        
        response = requests.post(urls["PATIENT_SEARCH"], json=data)

        # Verify if POST request was successful
        if response.status_code == 200:
            print("Patient search successful")
            results = response.json()
            print(results)
        else:
            print(f"Failed to retrieve data: {response.status_code}")
            print(response.text)
        return render_template('patient-search.html', results=results)

    data = {
        'name': '',
        'sort_by': 'lastname',
        'sort_order': 'asc'
    }
    response = requests.post(urls["PATIENT_SEARCH"], json=data)
    if response.status_code == 200:
        print("Patient search successful")
        results = response.json()
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        print(response.text)

    return render_template('patient-search.html', results=results)

@app.route('/patient-scans/<patient_id>')
@login_required
def patient_scans(patient_id):
    """
    Retrieve patient scans and details based on the provided patient ID.

    Parameters:
    patient_id (int): The unique identifier of the patient whose scans and details are to be retrieved. This should
        match the patient_id value in the linked datastore.

    Returns:
    flask.Response: If successful, renders the 'patient-scans.html' template with the retrieved patient details
                    and scans for display.
                    If patient details cannot be retrieved, returns a 404 error with message "Patient not found".
    """
    if not(current_user.user_type == 'doctor' or current_user.patient_id == patient_id):    #make sure a patient cannot access the scans of another patient
        return "Access Denied", 403

    scans = get_patient_scans(patient_id)
    
    # This is used for rendering patient details on HTML template
    patient = get_patient_details(patient_id)

    if patient:
        return render_template('patient-scans.html', patient=patient, scans=scans)
    else:
        return "Patient not found", 404
    
@app.route('/inspect-scan.html/<file_type>/<scan_id>')
@login_required
def inspect_scan(file_type, scan_id):
    """
    Route to inspect and display scan details based on the scan type and ID.

    Parameters:
    file_type (str): The type of the file to be inspected. Possible values are 'nifti', 'text', and 'dicom'.
    scan_id (str): The unique identifier of the scan to be inspected.

    Depending on the `file_type` parameter, the function behaves as follows:
    - If `file_type` is "dicom":
        - Redirects to an external OHIF viewer with the study and series IDs as query parameters.
    - If `file_type` is "nifti":
        - Downloads file on web server
        - Calculates the total number of slices in the scan using `get_total_slices`
        - Renders the 'inspect-file-nifti.html' template with the patient and scan details.
    - If `file_type` is "text":
        - Downloads file on web server
        - Renders the 'inspect-file-text.html' template with the patient and scan details.

    Returns:
    - HTML template rendered with patient and scan details for 'nifti' and 'text' file types.
    - HTTP redirect to an external viewer for 'dicom' file type.
    """
    # ensure that a patient cannot access the scan of another patient
    if not permit_access(current_user,scan_id,firestore_db): return "Access Denied", 403

    # If .dcm file, redirect to external OHIF viewer
    # Pull scan details from datastore
    scan = get_scan_details(file_type, scan_id)
    if file_type == "dicom":

        # open viewer in new tab - can't just use webbrower.open_new_tab as in a Docker continaer, the app doesn't have direct acccess to the client's browers, so this HTML response with embedded JavaScript does the same job successfully
        ohif_url = f"{urls['OHIF_VIEWER']}/viewer?StudyInstanceUIDs={scan['study_id']}&SeriesInstanceUIDs={scan['series_id']}"

        return f'''
        <html>
            <head>
                <script>
                    window.open("{ohif_url}", "_blank"); // Open in a new tab
                    window.history.back(); // Go back to the previous page
                </script>
            </head>
            <body>
                <p>If the viewer did not open, <a href="{ohif_url}" target="_blank">click here</a> to open it manually.</p>
            </body>
        </html>
        '''

    # If NIFTI or text, then download file to web server to be accessed easily
    download_file_locally(file_type, scan_id)
    # Store content of text file in scan object
    with open("temp_text_file.txt", 'r') as file:
        scan['text_content'] = file.read()
    # Pull patient details from datastore
    patient = get_patient_details(scan['patient_id'])
    if file_type == "nifti":
        # Calculate total number of slices in scan (used to initialise dynamic scroll bar)
        scan['totalSlices'] = get_total_slices()
        return render_template('inspect-file-nifti.html', patient=patient, scan=scan)
    if file_type == "text":
        return render_template('inspect-file-text.html', patient=patient, scan=scan)
    
    

@app.route('/upload-scan', methods=['POST']) # Only allow post methods, since this has to come from the form in patient-scans
@login_required
def upload_scan():
    """
    Handle the uploading of an MRI scan file for a specific patient.

    If the request comes from 'upload scan' button on 'patient-scans' page:
    - Retrieves patient details based on 'patient_id' from the form data.
    - Renders the 'upload-scan.html using patient_id to autofill this field

    If the request comes from 'submit file' on 'upload-scan' page (i.e. attempt to upload file):
    - Retrieves patient details based on 'patient_id' from the form data.
    - Validates the uploaded MRI scan file and timestamp.
    - Uploads the scan file to storage service
    - Renders again 'upload-scan.html'

    Returns:
    flask.Response: A rendered HTML template 'upload-scan.html' displaying the upload form and patient details.
    """
    # Get patient details from datastore
    patient = get_patient_details(request.form.get('patient_id', ''))
    if not patient:
        return "Patient not found", 404
    
    if patient['patient_id'] != current_user.patient_id and current_user.user_type != 'doctor':
        return 'Access Denied', 403

    # If page is being loaded from "upload scan" page on /patient-scans
    if not 'scanTimestamp' in request.form:
        return render_template('upload-scan.html', patient=patient) # this patient should in fact be extracted from firestore

    # Else if page has been loaded from 'submit file' button on /upload-scan
    file = request.files['file']
    if request.form['scanTimestamp'] == '':
        flash("No timestamp entered")
        return render_template('upload-scan.html', patient=patient)
    if file.filename == '':
        flash('No selected file')
        return render_template('upload-scan.html', patient=patient)
    
    file_type = determine_file_type(file.filename) # RETURNS "nifti" OR "dicom" OR "text"

    if not file_type in ALLOWED_FILE_TYPES:
        flash("Please upload one of the following file types: " + str(ALLOWED_FILE_TYPES))
        return render_template('upload-scan.html', patient=patient)

    # Upload the scan, and get back the cloud functions response
    response = upload_scan_to_storage(file, patient['patient_id'], request.form['scanTimestamp'], file_type)
    if response.status_code == 200:
        flash("File sent successfully!")
    else:
        flash("Failed to send file. Status code:", response.status_code)
    
    return render_template('upload-scan.html', patient=patient) # Maybe use redirect to stop form being resubmitted

@app.route('/add-patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    """
    Render a web page ('add-patient.html') to add a new patient to the system.

    If a POST request is received:
    - Validates and retrieves patient information from the form.
    - Checks for empty or invalid input fields (first name, last name, DOB).
    - Uploads the patient object to a datastore using a helper function ('upload_patient_to_datastore').
    - Displays flash messages based on the success or failure of the upload operation.

    Returns:
    flask.Response: A rendered HTML template 'add-patient.html' for both GET and POST requests.
    """
    if current_user.user_type != 'doctor':
        return 'Access Denied', 403
    patient = {}
    if request.method == 'POST':
        patient['firstname'] = request.form['firstname']
        if patient['firstname'] == '' or patient['firstname'].isspace():
            flash("Enter a first name")
            return render_template('add-patient.html')
        patient['lastname'] = request.form['lastname']
        if patient['lastname'] == '' or patient['lastname'].isspace():
            flash("Enter a last name")
            return render_template('add-patient.html')
        patient['dob'] = request.form['dob']
        if patient['dob'] == '':
            flash("Enter a DOB")
            return render_template('add-patient.html')
        patient['sex'] = request.form['sex']

        # Upload patient object to datastore
        response = upload_patient_to_datastore(patient)

        if response.status_code == 200:
            flash("Patient added successfully!")
        else:
            flash("Failed to add patient. Status code:", response.status_code)
        return redirect(url_for('add_patient'))

    return render_template('add-patient.html')
    
@app.route('/get-scan-report/<scan_id>/<slice_no>/<mode>')
@login_required
def get_scan_report(scan_id, slice_no, mode):
    """
    Fetches a scan report from a cloud function.

    This route sends a POST request to a specified cloud function URL with
    the provided `scan_id` and retrieves the generated report based on a
    specified technical level. The report is returned as a text response.

    Args:
        scan_id (str): The unique identifier of the scan for which the report is requested
        slice_no (str or int): The number of the slice which the report will examine
        mode (str): 'Y' -> technical. 'N' -> non-technical

    Returns:
        str: The generated scan report as a text response from the cloud function.

    Raises:
        requests.exceptions.RequestException: If there is an error during the HTTP request
    """
    permit_access(current_user, scan_id, firestore_db)
    response = requests.post(url=urls["GENERATE_REPORT"], json={'scan_id': str(scan_id), 'technical':str(mode), 'slice_number': int(slice_no)})
    return response.text

@app.route('/get-text-report/<scan_id>/<mode>')
@login_required
def get_text_report(scan_id, mode):
    """
    Route to get a summary of a text report file for a given scan ID and level of technical language.
    NB: To generate reports of scans, see 'get_scan_report'.

    Parameters:
    scan_id (str): The unique identifier of the scan (text file) for which the summary is to be generated.

    The function performs the following operations:
    1. Sends a POST request to the summarization service endpoint with the scan ID in the JSON payload, and a level
        of technical language specified as either Y (technical) or N (non-technical).
    2. Receives the response from the service and returns the text content of the response.

    Returns:
    str: The summarized text report returned by the summarization service.
    """
    permit_access(current_user, scan_id, firestore_db)
    response = requests.post(url=urls["SUMMARISE_DOCUMENT"], json={'scan_id': str(scan_id), 'technical': str(mode)})
    return response.text


@app.route('/delete-file/<scan_id>')
@login_required
def delete_file(scan_id):
    """
    Route to delete a file associated with a given scan ID.

    Parameters:
    scan_id (str): The unique identifier of the scan whose file is to be deleted.

    The function calls a cloud function which handles the deletion of the file.
    It then redirects the user back to the referring page to refresh the scan results displayed.
    """
    permit_access(current_user, scan_id, firestore_db)
    response = requests.post(url=urls["DELETE_FILES"], json={'scan_id': str(scan_id)})
    if response.status_code == 200:
        print("File deleted successfully")
    else:
        print("Failed to delete file. Status code:", response.status_code)
    return redirect(request.referrer)

@app.route('/delete-patient/<patient_id>')
@login_required
def delete_patient(patient_id):
    """
    Route to delete a file associated with a given scan ID.

    Parameters:
    scan_id (str): The unique identifier of the scan whose file is to be deleted.

    The function calls a cloud function which handles the deletion of the file.
    It then redirects the user back to the referring page to refresh the scan results displayed.
    """
    if not is_admin(current_user):
        return "Access denied", 403
    response = requests.post(url=urls["DELETE_PATIENT"], json={'patient_id': str(patient_id)})
    if response.status_code == 200:
        print("Patient deleted successfully")
    else:
        print("Failed to delete patient. Status code:", response.status_code)
    return redirect(request.referrer)


@app.route('/select-user-type')
@login_required
def select_user_type():
    return render_template('select-user-type.html')

@app.route('/change-user-status', methods=['POST'])
@login_required
def change_user_status():
    response = requests.post(url=urls["CHANGE_STATUS"], json={'patient_id': str(request.form.get('patient_id_select')), 'new_status': request.form.get('selectedOption')})
    if response.status_code == 200:
        print("Patient status changed successfully")
    else:
        print("Failed to change status of patient. Status code:", response.status_code)
    return redirect(request.referrer)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))