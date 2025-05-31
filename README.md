# Scan Manager

A cloud-integrated medical imaging management system developed during a summer internship at **Reply**, designed to facilitate secure scan uploads, patient data handling, reporting, and viewing via a web-based OHIF viewer using **Google Cloud Functions** and **Flask**. This web-app was co-developed with James Housden and Matthew Zahra,

---


##  Tech Stack

| Component             | Technology                            |
|----------------------|----------------------------------------|
| Backend API        | Flask + Google Cloud Functions         |
| Chatbot Interface  | Dialogflow (intent matching)           |
| Cloud Storage      | Firebase Cloud Storage (DICOMs, JSON)  |
| Auth & Hosting     | Firebase (optional auth) + Netlify     |
| Viewer             | OHIF Viewer for DICOM scan display     |



---

## Features

- **Upload Scans** (DICOM) + patient data to cloud
-  **Search Patients** by name or PID
- **View Scans** via OHIF Viewer (web-based)
- **Generate Reports** from scan metadata
- **Chatbot** to guide users and answer usage-related questions
- **Delete Patients/Files** to maintain data hygiene
- **Change Status / Summarise Documents**

---

## Cloud Functions Overview (`/cloud functions`)

Each Python file corresponds to a deployed Google Cloud Function:

| File                     | Functionality                              |
|--------------------------|---------------------------------------------|
| `upload-scan-and-patient-data.py` | Upload scans and patient metadata      |
| `download-data.py`      | Download scans as a bundle                  |
| `generate-report.py`    | Generate reports from uploaded scan data    |
| `patient-search.py`     | Search patients by name/PID                 |
| `change-status.py`      | Update patient/scan status (e.g. reviewed)  |
| `summarise-document.py` | Extract and summarise scan notes            |
| `delete-patient.py`     | Delete patient records                      |
| `delete-files.py`       | Remove specific scan files                  |
| `pid-to-scans.py`       | Retrieve all scans linked to a patient      |
| `pid-to-patient-details.py` | Retrieve patient metadata                |

---

##  Chatbot Features 

- Provides app usage guidance (`app_usage.txt`)
- Answers common questions about MRI scans from `chatbot_knowledge.txt`
- Easily extendable with additional commands or Q&A pairs

---

## OHIF Viewer 

- Integrated OHIF instance for viewing uploaded DICOM scans
- Customisable and hosted locally or on Netlify
- Uses platform folders like `modes/`, `extensions/`, and `.scripts/` for configuration

---
## Authors
**James Housden**, **Matthew Zahra**, and **Samiksha Vanga** for Go Reply.
