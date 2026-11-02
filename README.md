# AI Form Assistant

AI-powered document extraction, information verification, and intelligent online form autofill.

## Technology Stack

### Frontend
- HTML5
- CSS3
- JavaScript (Vanilla JS)

### Backend
- Python
- FastAPI
- Pydantic

### Document Intelligence
- PyMuPDF – PDF processing and text extraction
- PaddleOCR – OCR for scanned documents
- LLM – Document classification and information extraction

### AI Integration
- OpenRouter API
- Structured JSON extraction
- Semantic field mapping

### Database & Storage
- Supabase PostgreSQL
- Supabase Storage

### Browser Extension
- Chrome Extension Manifest V3
- JavaScript
- DOM manipulation
- Chrome APIs

## Project Modules

1. **Document Upload** – Upload combined PDF documents.
2. **Document Intelligence** – Process PDFs, classify documents, and extract text.
3. **Information Extraction** – Extract structured information using AI.
4. **Profile Verification** – Review, edit, and correct extracted information.
5. **Verified Profile Management** – Store and manage approved information.
6. **Chrome Extension Autofill** – Detect website form fields and automatically fill matching information.

## Project Structure

```text
ai-form-assistant/
│
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   └── requirements.txt
│
├── extension/
├── database/
├── docs/
├── .gitignore
└── README.md
```

## Development Setup

### 1. Frontend

The frontend uses plain HTML, CSS, and JavaScript.

Open the `frontend` folder using VS Code Live Server.

Alternatively, run:

```bash
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500`.

### 2. Backend

Create a Python virtual environment:

```powershell
cd backend
python -m venv venv
```

Activate the environment:

```powershell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Start FastAPI:

```powershell
uvicorn app.main:app --reload --port 8000
```

Backend API:

`http://localhost:8000`

API Documentation:

`http://localhost:8000/docs`

### 3. Database

Supabase PostgreSQL will be used for structured data storage.

Supabase Storage will manage uploaded PDF documents.

## Development Roadmap

1. Project Foundation
2. Supabase Integration
3. PDF Processing Engine
4. OCR & Document Intelligence
5. AI Information Extraction
6. Profile Verification Workspace
7. Verified Profile Engine
8. Chrome Extension & Autofill
9. Integration & Testing

## Project Goal

Build an intelligent application that allows users to upload their documents once, extract and verify their information, and reuse that information to automatically fill online application forms.

**Upload once. Verify once. Fill anywhere.**