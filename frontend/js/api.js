
const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

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
    const response = await fetch(
        `${API_BASE_URL}/documents/sessions`,
        { method: "POST" }
    );

    const data = await handleResponse(response);
    return data.session.id;
}

// Upload PDF
async function uploadPDF(sessionId, file) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(
        `${API_BASE_URL}/documents/upload?session_id=${encodeURIComponent(sessionId)}`,
        {
            method: "POST",
            body: formData
        }
    );

    return await handleResponse(response);
}

// Classify uploaded document
async function classifyDocument(documentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/${documentId}/classify`,
        { method: "POST" }
    );

    return await handleResponse(response);
}

// Extract Aadhaar information
async function extractAadhaar(extractedDocumentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/extract-aadhaar`,
        { method: "POST" }
    );

    return await handleResponse(response);
}

// Get extracted document review
async function getDocumentReview(extractedDocumentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/review`
    );

    return await handleResponse(response);
}

// Update extracted profile fields
async function updateProfileFields(extractedDocumentId, fields) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/fields`,
        {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ fields })
        }
    );

    return await handleResponse(response);
}

// Save profile as a draft (no field verification required)
async function saveProfile(extractedDocumentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/save-profile`,
        { method: "POST" }
    );

    return await handleResponse(response);
}

// Retrieve saved profile using profile ID
async function getSavedProfile(profileId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/profiles/${encodeURIComponent(profileId)}`
    );

    return await handleResponse(response);
}

// Legacy function — retained temporarily for compatibility
async function saveVerifiedProfile(extractedDocumentId) {
    return await saveProfile(extractedDocumentId);
}

// Legacy verification function — not needed in the new workflow
async function verifyProfileField(extractedDocumentId, fieldName) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/fields/${encodeURIComponent(fieldName)}/verify`,
        { method: "POST" }
    );

    return await handleResponse(response);
}
