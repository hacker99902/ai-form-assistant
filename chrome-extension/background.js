
const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

// Get the saved JWT token
async function getAccessToken() {
    const stored = await chrome.storage.local.get("extensionAccessToken");

    if (!stored.extensionAccessToken) {
        throw new Error("Please sign in with Google first.");
    }

    return stored.extensionAccessToken;
}

// Sign in using Google OAuth
async function googleLogin() {
    try {
        const loginUrl = `${API_BASE_URL}/auth/extension/login`;

        const redirectUrl = await chrome.identity.launchWebAuthFlow({
            url: loginUrl,
            interactive: true
        });

        if (!redirectUrl) {
            throw new Error("Google login was cancelled.");
        }

        const url = new URL(redirectUrl);
        const code = url.searchParams.get("code");

        if (!code) {
            throw new Error("Authentication code not received.");
        }

        const response = await fetch(
            `${API_BASE_URL}/auth/extension/exchange`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ code })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Token exchange failed.");
        }

        await chrome.storage.local.set({
            extensionAccessToken: data.access_token
        });

        return {
            success: true,
            message: "Successfully signed in with Google."
        };

    } catch (error) {
        return {
            success: false,
            message: error.message
        };
    }
}

// Fetch the user's saved profile
async function getSavedProfile() {
    const token = await getAccessToken();

    const response = await fetch(
        `${API_BASE_URL}/auth/extension/profile`,
        {
            headers: {
                Authorization: `Bearer ${token}`
            }
        }
    );

    if (response.status === 401) {
        await chrome.storage.local.remove("extensionAccessToken");
        throw new Error("Session expired. Please sign in again.");
    }

    if (!response.ok) {
        throw new Error(`Profile request failed: ${response.status}`);
    }

    return await response.json();
}

// Check whether a profile is available
async function checkProfileStatus() {
    try {
        const profile = await getSavedProfile();

        return {
            success: true,
            profileAvailable: !!profile
        };

    } catch (error) {
        // 404 means the user has no approved profile yet.
        if (error.message.includes("404")) {
            return {
                success: true,
                profileAvailable: false,
                message: "Your profile is awaiting approval."
            };
        }

        return {
            success: false,
            profileAvailable: false,
            message: error.message
        };
    }
}

// Fill the currently active website
async function fillCurrentTab() {
    try {
        const profile = await getSavedProfile();

        const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true
        });

        if (!tab || !tab.id || !tab.url) {
            throw new Error("Unable to identify the active website.");
        }

        if (
            tab.url.startsWith("chrome://") ||
            tab.url.startsWith("chrome-extension://")
        ) {
            throw new Error("This page cannot be autofilled.");
        }

        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ["content.js"]
        });

        const result = await chrome.tabs.sendMessage(tab.id, {
            type: "FILL_FORM",
            profile: profile
        });

        return result || {
            success: false,
            message: "The website did not respond."
        };

    } catch (error) {
        return {
            success: false,
            message: error.message
        };
    }
}

// Sign out
async function logout() {
    await chrome.storage.local.remove("extensionAccessToken");

    return {
        success: true,
        message: "Signed out successfully."
    };
}


async function uploadDocument(fileName, fileBytes) {
    const token = await getAccessToken();

    // 1. Create a processing session
    const sessionResponse = await fetch(
        `${API_BASE_URL}/documents/sessions`,
        {
            method: "POST",
            headers: {
                Authorization: `Bearer ${token}`
            }
        }
    );

    if (sessionResponse.status === 401) {
        await chrome.storage.local.remove("extensionAccessToken");
        throw new Error("Session expired. Please sign in again.");
    }

    const sessionData = await sessionResponse.json();

    if (!sessionResponse.ok) {
        throw new Error(
            sessionData.detail || "Could not create processing session."
        );
    }

    const sessionId = sessionData.session.id;
    console.log("Received PDF bytes:", fileBytes.length);
    console.log("PDF signature:", fileBytes.slice(0, 5));
    // 2. Prepare the PDF
    const pdfBlob = new Blob([new Uint8Array(fileBytes)], {
        type: "application/pdf"
    });

    const formData = new FormData();
    formData.append("file", pdfBlob, fileName);

    // 3. Upload the PDF
    const uploadResponse = await fetch(
        `${API_BASE_URL}/documents/upload?session_id=${encodeURIComponent(sessionId)}`,
        {
            method: "POST",
            headers: {
                Authorization: `Bearer ${token}`
            },
            body: formData
        }
    );

    const uploadData = await uploadResponse.json();

    if (uploadResponse.status === 401) {
        await chrome.storage.local.remove("extensionAccessToken");
        throw new Error("Session expired. Please sign in again.");
    }

    if (!uploadResponse.ok) {
        throw new Error(
            uploadData.detail || "PDF upload failed."
        );
    }

    // 4. Automatically process the uploaded document
    const documentId = uploadData.document_id;

    if (!documentId) {
        throw new Error("Upload succeeded, but no document ID was returned.");
    }

    const processingResponse = await fetch(
        `${API_BASE_URL}/documents/auto-process/${encodeURIComponent(documentId)}`,
        {
            method: "POST",
            headers: {
                Authorization: `Bearer ${token}`
            }
        }
    );

    const processingData = await processingResponse.json();

    if (processingResponse.status === 401) {
        await chrome.storage.local.remove("extensionAccessToken");
        throw new Error("Session expired. Please sign in again.");
    }

    if (!processingResponse.ok) {
        throw new Error(
            processingData.detail || "Document processing failed."
        );
    }

    return {
        success: true,
        message: "Document uploaded and processed successfully.",
        document: uploadData,
        processing: processingData
    };
}


// Handle popup requests
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

    if (message.type === "GOOGLE_LOGIN") {
        googleLogin().then(sendResponse);
        return true;
    }

    if (message.type === "GET_PROFILE_STATUS") {
        checkProfileStatus()
            .then(sendResponse)
            .catch(error => sendResponse({
                success: false,
                message: error.message
            }));

        return true;
    }

    if (message.type === "GET_SAVED_PROFILE") {
        getSavedProfile()
            .then(sendResponse)
            .catch(error => sendResponse({
                success: false,
                message: error.message
            }));

        return true;
    }

    if (message.type === "FILL_CURRENT_TAB") {
        fillCurrentTab().then(sendResponse);
        return true;
    }

    if (message.type === "LOGOUT") {
        logout().then(sendResponse);
        return true;
    }
    if (message.type === "UPLOAD_DOCUMENT") {
        uploadDocument(message.fileName, message.fileBytes)
            .then(sendResponse)
            .catch(error => {
                sendResponse({
                    success: false,
                    message: error.message
                });
            });

        return true;
    }
});
