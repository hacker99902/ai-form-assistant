
const API_BASE_URL = "http://localhost:8000/api/v1";

async function createSession() {
    const response = await fetch(
        `${API_BASE_URL}/documents/sessions`,
        { method: "POST" }
    );

    if (!response.ok) {
        throw new Error("Could not create processing session");
    }

    const data = await response.json();
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

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "PDF upload failed");
    }

    return data;
}
