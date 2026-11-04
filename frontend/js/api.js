
const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

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

async function createSession() {
    const response = await fetch(
        `${API_BASE_URL}/documents/sessions`,
        { method: "POST" }
    );

    const data = await handleResponse(response);
    return data.session.id;
}

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

async function classifyDocument(documentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/${documentId}/classify`,
        { method: "POST" }
    );

    return await handleResponse(response);
}

async function extractAadhaar(extractedDocumentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/extract-aadhaar`,
        { method: "POST" }
    );

    return await handleResponse(response);
}

async function getDocumentReview(extractedDocumentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/review`
    );

    return await handleResponse(response);
}

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

async function verifyProfileField(extractedDocumentId, fieldName) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/fields/${encodeURIComponent(fieldName)}/verify`,
        { method: "POST" }
    );

    return await handleResponse(response);
}

async function saveVerifiedProfile(extractedDocumentId) {
    const response = await fetch(
        `${API_BASE_URL}/documents/extracted/${extractedDocumentId}/save-profile`,
        { method: "POST" }
    );

    return await handleResponse(response);
}
