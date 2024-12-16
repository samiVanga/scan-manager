import json
from PIL import Image
import nibabel as nib
import numpy as np
import requests

# Define URLs for cloud functions
def load_urls(path):
    with open(path) as f:
        return json.load(f)
urls = load_urls("url_config.json")

def determine_file_type(filename):
    """
    Determines the file type based on the file extension.

    Parameters:
    filename (str): The name of the file whose type is to be determined.

    Returns:
    filename (str): One of "text", "nifti" or "dicom"
    """
    if filename.lower().endswith(".txt"):
        return "text"
    if filename.lower().endswith(".nii.gz"):
        return "nifti"
    if filename.lower().endswith(".zip"):
        return "dicom"
        

def convert_nii_slice_to_png(scan, slice_number):
    """
    Convert a slice from a NIfTI format to a PNG image.

    Parameters:
    scan (numpy.ndarray): the 3D NIfTI image data as a NumPy array.
    slice_number (int): the index of the slice to extract and convert to PNG.

    Returns:
    PIL.Image: A PIL Image object containing the converted PNG image

    Raises:
    ValueError: If 'slice_number' is out of bounds for the depth dimension of 'scan'.

    Example:
    >>> img = nib.load('brain_scan.nii.gz').get_fdata()
    >>> png_image = convert_nii_slice_to_png(img, 30)

    Note: This function does not incorporate scaling (https://ianmcatee.com/converting-a-nifti-file-to-an-image-sequence-using-python/)
    """
    if slice_number < 0 or slice_number >= scan.shape[2]:
        raise ValueError(f"slice_number {slice_number} is out of bounds for scan with shape {scan.shape}")
    slice_data = scan[:, :, slice_number]
    img_uint8 = slice_data.astype(np.uint8)
    img = Image.fromarray(img_uint8)
    return img

def get_patient_scans(patient_id):
    """
    Query datastore via a Cloud Function endpoint for all scans linked to a patient_id.

    Parameters:
    patient_id (int or str): The unique identifier of the patient whose scans are to be retrieved. Should match datastore field.

    Returns:
    list: A list of scan data retrieved from the Cloud Function endpoint, or an empty list if retrieval fails.
    """

    data = {'patient_id': str(patient_id)}
    response = requests.post(urls["PID_TO_SCANS"], json=data)

    if response.status_code == 200:
        print("Patient's files retrieved successfully:")
        return response.json()
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        print(response.text)
        return []
    
def get_patient_details(patient_id):
    """
    Query datastore via a Cloud Function endpoint to get patient data associated with a patient_id.

    Parameters:
    patient_id (int or str): The unique identifier of the patient whose details are to be retrieved. Should match datastore field.

    Returns:
    dict or None: A dictionary containing patient data retrieved from the Cloud Function endpoint,
                  or None if retrieval fails or no patient data is found.
    """
    data = {'patient_id': str(patient_id)}
    response = requests.post(urls["PID_TO_PATIENT_DETAILS"], json=data)
    if response.status_code == 200:
        print("Patient details retrieved successfully:")
        return response.json()[0]  # Take the first entry since there should only ever be one.
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        print(response.text)
        return None

def get_total_slices():
    """
    Retrieve the total number of slices in a NIfTI format file.

    Returns:
    int: The total number of slices in the NIfTI image file.

    Notes:
    - This function assumes the NIfTI image file is located at 'temp_scan_file.nii.gz'.
    """
    file_path = f"temp_scan_file.nii.gz"
    scan_array = nib.load(file_path).get_fdata()
    return scan_array.shape[2] # TODO: MAKE COMPATIBLE WITH MORE THAN 3 DIMENSIONS

def get_scan_details(file_type, scan_id):
    """
    Retrieve details of an MRI scan from a Cloud Function endpoint based on the provided scan_id.

    Parameters:
    scan_id (int or str): The identifier of the MRI scan whose details are to be retrieved. Must match datastore entry.

    Returns:
    dict or None: A dictionary containing details of the MRI scan retrieved from the Cloud Function endpoint,
                 or None if retrieval fails.
    """
    return_file = 'N'
    payload = {'scan_id': str(scan_id), 'return_file':return_file, 'file_type': file_type}
    response = requests.post(urls["DOWNLOAD_SCAN_DATA"], json=payload)
    # Check if response was successful
    if response.status_code == 200:
        # Return scan details as dictionary object)
        return eval(response.text)
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        return None


def download_file_locally(file_type, scan_id):
    """
    Downloads a file associated with a given scan ID and saves it locally.

    Parameters:
    file_type (str): The type of the file to be downloaded. Possible values are 'nifti' and 'text'.
    scan_id (str): The unique identifier of the scan whose file is to be downloaded.

    Depending on the file type, saves the returned file content to a local file:
       - For 'nifti' files, saves content to "temp_scan_file.nii.gz".
       - For 'text' files, saves content to "temp_text_file.txt".
    The local file is saved in the same directory as the python files.
    """
    return_file = 'Y'
    payload = {'scan_id': str(scan_id), 'return_file':return_file, 'file_type': file_type}
    response = requests.post(urls["DOWNLOAD_SCAN_DATA"], json=payload)
    # Check if the request was successful
    if response.status_code == 200:
        # Save the returned file content to a file
        if file_type == "nifti":
            with open(f"temp_scan_file.nii.gz", 'wb') as f:
                f.write(response.content)
            print('Nifti file downloaded successfully')
        elif file_type == "text":
            with open(f"temp_text_file.txt", 'w') as f:
                f.write(response.text)
            print('Text file downloaded successfully')
    else:
        print(f"Failed to retrieve file: {response.status_code}")


def upload_scan_to_storage(file, patient_id, timestamp, file_type):
    """
    Upload an MRI scan file and associated patient data to a storage service via a Cloud Function endpoint.

    Parameters:
    file (FileStorage): The MRI scan file to upload, typically obtained from a Flask request object.
    patient_id (int or str): The identifier of the patient associated with the MRI scan.
    timestamp (str): The timestamp indicating when the scan was performed.
    file_type (str): The type of scan being uploaded. Normally one of three options: "nifti", "text" or "dicom"

    Returns:
    requests.Response: The response object returned by the Cloud Function endpoint after upload.
    """
    data = {'patient_id':patient_id, 'timestamp':timestamp, 'file_type': file_type, 'report': 'No report generated'}
    files = {'file_data': json.dumps(data), 'file': (file.filename, file)}
    response = requests.post(urls["UPLOAD_SCAN_AND_PATIENT"], files=files)
    return response


def upload_patient_to_datastore(patient):
    """
    Uploads patient data to the datastore.

    Parameters:
    patient (dict): A dictionary containing patient information to be uploaded.
        Required fields are 'firstname', 'lastname', 'dob', 'sex'.
    """
    files = {'patient_data': json.dumps(patient)}
    response = requests.post(urls["UPLOAD_SCAN_AND_PATIENT"], files=files)
    return response

# stops a patient accessing the file of another patient via url injection
def permit_access(current_user, scan_id, firestore_db):
    if not is_doctor(current_user):
        for scan in firestore_db.collection('scans').get():
            dictionary = scan.to_dict()
            current_scan_id = dictionary['scan_id'] 
            if current_scan_id == scan_id:
                if dictionary['patient_id'] != current_user.patient_id:
                    return False
                break
    return True

def is_admin(current_user):
    return current_user.admin == 'Y'

def is_doctor(current_user):
    return current_user.user_type == 'doctor'

def is_patient(current_user):
    return current_user.user_type == 'patient'