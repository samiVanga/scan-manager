import functions_framework
import vertexai
from vertexai.generative_models import GenerativeModel
import vertexai.preview.generative_models as generative_models
from google.cloud import storage
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Initialize Firebase Admin SDK (only required once per function instance)
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'apt-vine-428509-d2',
})
db = firestore.client()

# TODO: update these with your bucket names
TEXT_BUCKET_NAME = 'text_file_store'

# TODO: update these values
# set up the model
location = 'europe-west2'
project_id = 'apt-vine-428509-d2'
vertexai.init(project=project_id, location=location)
model = GenerativeModel("gemini-1.5-pro-001")

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


'''
input: json of the form {scan_id: <string>}

This is for use only for text files - it takes a given text file, and then gets Gemini to simplify it in simple english.
'''
@functions_framework.http
def summarise(request):
    request_json = request.get_json(silent=True)
    scan_id = request_json.get('scan_id')
    technical=request_json.get('technical')

    if not scan_id:
        return 'no scan id', 400
    
    bucket_name = TEXT_BUCKET_NAME
    file_name = scan_id + '.txt'

    # get file contents
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    blob.download_to_filename('/tmp/text.txt')

    with open('/tmp/text.txt') as file:
        contents = file.read()

    if technical == 'N':
        prompt = '''You are a doctor who is summarising a report for a patient. The summary should contain the diagnosis, sympotoms, treatment and any further action that needs to be taken. The summarised report should explain any medical terms or diagnosis so a person with no medical knowledge can understand.The summary should be in easy to understand and concise language.'''
    else:
        prompt = '''You are a doctor who has been presented a report and want a summary of it. The summary should contain the diagnosis, symptoms, treatment and any further action that needs to be taken.The summarised report should keep all the key information and any techincal medical terms.The summary should be in easy to understand and concise language.'''

    prompt += contents
    
    # generate response from model
    responses = model.generate_content(
      prompt,
      generation_config=generation_config,
      safety_settings=safety_settings,
      stream=False,
    )
    newReport = responses.text

    # update row in database to reflect new report that has just been generated
    docs = db.collection('scans').where('scan_id', '==', scan_id).stream()
    for doc in docs:
        doc.reference.update({'report': newReport})

    return newReport, 200