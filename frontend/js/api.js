
const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

// Centralized API request helper.
// Sends the Google login session cookie with every request.
async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        credentials: "include"
    });

    return await handleResponse(response);
}

// Handle API responses
async function handleResponse(response) {
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        const message =
            typeof data.detail === "string"
                ? data.detail
                : "Request failed.";

        throw new Error(message);
    }

    return data;
}

// Create a processing session
async function createSession() {
    const data = await apiRequest(
        `${API_BASE_URL}/documents/sessions`,
        { method: "POST" }
    );

    return data.session.id;
}

// Upload PDF
async function uploadPDF(sessionId, file) {
    const formData = new FormData();
    formData.append("file", file);

    return await apiRequest(
        `${API_BASE_URL}/documents/upload?session_id=${encodeURIComponent(sessionId)}`,
        {
            method: "POST",
            body: formData
        }
    );
}


// Automatically classify and process all documents in an uploaded PDF.
async function autoProcessDocument(documentId) {
    return await apiRequest(
        `${API_BASE_URL}/documents/auto-process/${encodeURIComponent(documentId)}`,
        { method: "POST" }
    );
}


// Classify uploaded document
async function classifyDocument(documentId) {
    return await apiRequest(
        `${API_BASE_URL}/documents/${documentId}/classify`,
        { method: "POST" }
    );
}

// Extract Aadhaar information
async function extractAadhaar(extractedDocumentId) {
    return await apiRequest(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/extract-aadhaar`,
        { method: "POST" }
    );
}

// Get extracted document review
async function getDocumentReview(extractedDocumentId) {
    return await apiRequest(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/review`
    );
}

// Update extracted profile fields
async function updateProfileFields(extractedDocumentId, fields) {
    return await apiRequest(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/fields`,
        {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ fields })
        }
    );
}

// Save profile as a draft
async function saveProfile(extractedDocumentId) {
    return await apiRequest(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/save-profile`,
        { method: "POST" }
    );
}

// Retrieve saved profile using profile ID
async function getSavedProfile(profileId) {
    return await apiRequest(
        `${API_BASE_URL}/documents/profiles/${encodeURIComponent(profileId)}`
    );
}

// Legacy function — retained temporarily
async function saveVerifiedProfile(extractedDocumentId) {
    return await saveProfile(extractedDocumentId);
}

// Legacy verification function
async function verifyProfileField(extractedDocumentId, fieldName) {
    return await apiRequest(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/fields/${encodeURIComponent(fieldName)}/verify`,
        { method: "POST" }
    );
}
    