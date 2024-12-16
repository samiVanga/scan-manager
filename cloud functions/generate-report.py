import functions_framework
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import vertexai.preview.generative_models as generative_models
from google.cloud import storage
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import nibabel as nib
from PIL import Image
import numpy as np
from io import BytesIO
import base64

# Initialize Firebase Admin SDK (only required once per function instance)
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'apt-vine-428509-d2',
})
db = firestore.client()

# TODO: update these with your bucket names
NIFTI_BUCKET_NAME = 'text_file_store'

# TODO: update these values
# set up the model
location = 'europe-west2'
project_id = 'apt-vine-428509-d2'
vertexai.init(project=project_id, location=location)
# Note: pro-vision was chosen (not just gemini pro) as it was the only gemini model that would create reports of MRI scans
model = GenerativeModel("gemini-1.0-pro-vision-001")

generation_config = {
    "max_output_tokens": 2048,
    "temperature": 0.4,
    "top_p": 0.4,
    "top_k": 32
}  

safety_settings = {
    generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
}

def download_nifti(bucket_name, source_blob_name, destination_file_name):
    """Downloads a NIfTI file from the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)


'''
input: json of the form 
    {scan_id: <string>,
    technical: 'Y' or 'N',
    slice_number: <int>}

This cloud function is given the id of a NIfTI file and a slice number.
It then converts the slice number to a PNG file and then passes this to Gemini.
The prompt that goes along with the image is aimed at a technical individual (technical = 'Y') or a non-technical individual (technical = 'N').
'''
@functions_framework.http
def prompt(request): 
    request_json = request.get_json(silent=True)
    scan_id = request_json.get('scan_id')
    technical = request_json.get('technical')
    slice_number = request_json.get('slice_number')

    # get file with scan_id stored in bucket
    bucket_name = NIFTI_BUCKET_NAME
    nifti_file = '/tmp/temp.nii.gz' #MUST BE .nii.gz - JUST .nii DOES NOT WORK - this will be the temporary file

    # download from bucket
    download_nifti(bucket_name, scan_id + '.nii.gz', nifti_file)

    # convert a slice to a PNG
    scan = nib.load(nifti_file).get_fdata()
    slice_data = scan[:, :, slice_number]   # NIfTI files are 3-dimensional objects, we want a 2-D slice
    # normalized_data = ((slice_data - np.min(slice_data)) / (np.max(slice_data) - np.min(slice_data))) * 255
    # img_uint8 = normalized_data.astype(np.uint8)
    img_uint8 = slice_data.astype(np.uint8)
    img = Image.fromarray(img_uint8)
    img_io = BytesIO()
    img.save(img_io, format="PNG")
    img_io.seek(0)
    img_data = img_io.getvalue()

    # build prompt
    if technical == 'Y':
        prompt_text = '''
        You are a highly skilled radiologist that is analysing a brain scan. 
        Please provide a detailed radiological analysis based on the provided brain MRI image.
        Describe any abnormalities present, including their location, size, shape, and signal intensity and characteristics. 
        Offer a possible diagnosis and suggest any further investigations that might be necessary. 
        If the scan is healthy please say that the scan shows a healthy person. 
        Please use clear and concise language, suitable for a medical professional.
        Please format your response using markdown.
        '''
    else:
        prompt_text = """
        You are a highly skilled radiologist that is analysing a brain scan. 
        Please provide an analysis based on the provided brain MRI image, explaining any medical terms so that your report is easily understood by a person with no medical knowledge.
        Use simple english.
        Offer a possible diagnosis and suggest any further investigations that might be necessary. 
        If the scan is healthy please say that the scan shows a healthy person. 
        Please use clear and concise language.
        Please format your response using markdown.
        """
    
    # add image to prompt by putting it in its own 'part' and encoding it in a way Gemini can understand it (base64)
    image = Part.from_data(
        mime_type='image/png',
        data=base64.b64encode(img_data).decode('utf-8')
    )
    prompt = [image, prompt_text]

    # generate response from model
    responses = model.generate_content(
      prompt,
      generation_config=generation_config,
      safety_settings=safety_settings,
      stream=False,
    )
    report = responses.text

    # update row in database to reflect new report that has just been generated
    docs = db.collection('scans').where('scan_id', '==', scan_id).stream()
    for doc in docs:
        doc.reference.update({'report': report})

    return report,200