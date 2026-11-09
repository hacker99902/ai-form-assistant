
const googleLoginButton = document.getElementById("googleLoginButton");
const logoutButton = document.getElementById("logoutButton");
const authStatus = document.getElementById("authStatus");

const profileStatus = document.getElementById("profileStatus");
const refreshProfileButton = document.getElementById("refreshProfileButton");

const fillFormButton = document.getElementById("fillFormButton");
const statusMessage = document.getElementById("statusMessage");

const uploadDocumentsButton = document.getElementById("uploadDocumentsButton");
const documentFiles = document.getElementById("documentFiles");
const uploadStatus = document.getElementById("uploadStatus");

function showStatus(message) {
    statusMessage.textContent = message;
}

function sendMessage(type, extra = {}) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ type, ...extra }, response => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
                return;
            }

            resolve(response);
        });
    });
}

// Check login and profile status

async function refreshStatus() {
    const storage = await chrome.storage.local.get("extensionAccessToken");
    const token = storage.extensionAccessToken;

    if (!token) {
        authStatus.textContent = "Not signed in";
        googleLoginButton.hidden = false;
        logoutButton.hidden = true;
        profileStatus.textContent = "Sign in to load your profile.";
        return;
    }

    // A stored token means the user has signed in.
    // Do not change this status just because profile retrieval fails.
    authStatus.textContent = "Signed in";
    googleLoginButton.hidden = true;
    logoutButton.hidden = false;

    try {
        const result = await sendMessage("GET_PROFILE_STATUS");

        if (!result || !result.success) {
            profileStatus.textContent =
                result?.message || "Unable to check profile status.";
            return;
        }

        profileStatus.textContent = result.profileAvailable
            ? "Approved profile available."
            : "Signed in. Your profile is awaiting approval.";

    } catch (error) {
        profileStatus.textContent =
            "Signed in. Could not check profile status. Try refreshing.";
        console.error("Profile status check failed:", error);
    }
}


// Google login
googleLoginButton.addEventListener("click", async () => {
    googleLoginButton.disabled = true;
    showStatus("Connecting to Google...");

    try {
        const result = await sendMessage("GOOGLE_LOGIN");

        if (!result || !result.success) {
            throw new Error(result?.message || "Google login failed.");
        }

        showStatus(result.message);
        await refreshStatus();

    } catch (error) {
        showStatus(error.message);

    } finally {
        googleLoginButton.disabled = false;
    }
});

// Logout
logoutButton.addEventListener("click", async () => {
    try {
        const result = await sendMessage("LOGOUT");
        showStatus(result.message);
        await refreshStatus();

    } catch (error) {
        showStatus(error.message);
    }
});

// Refresh saved profile status
refreshProfileButton.addEventListener("click", async () => {
    refreshProfileButton.disabled = true;
    profileStatus.textContent = "Loading saved profile...";

    try {
        const profile = await sendMessage("GET_SAVED_PROFILE");

        if (!profile || profile.success === false) {
            throw new Error(profile?.message || "Could not load profile.");
        }

        // Do not print personal profile values to the console.
        const fields = profile.profile_data || {};

        profileStatus.textContent =
            `Profile loaded. ${Object.keys(fields).length} top-level fields available.`;

        showStatus("Profile loaded successfully.");

    } catch (error) {
        profileStatus.textContent = error.message;
        showStatus(error.message);

    } finally {
        refreshProfileButton.disabled = false;
    }
});

// Upload and automatically process PDF documents
uploadDocumentsButton.addEventListener("click", async () => {
    const files = Array.from(documentFiles.files);

    if (files.length === 0) {
        uploadStatus.textContent = "Please select a PDF first.";
        return;
    }

    const invalidFile = files.find(file =>
        file.type !== "application/pdf" &&
        !file.name.toLowerCase().endsWith(".pdf")
    );

    if (invalidFile) {
        uploadStatus.textContent = "Only PDF files are supported.";
        return;
    }

    uploadDocumentsButton.disabled = true;

    const processingResults = [];
    let successfulUploads = 0;

    try {
        for (const file of files) {
            uploadStatus.textContent =
                `Uploading and processing ${file.name}...`;

            const fileBytes = Array.from(
                new Uint8Array(await file.arrayBuffer())
            );

            const result = await sendMessage("UPLOAD_DOCUMENT", {
                fileName: file.name,
                fileBytes
            });

            if (!result || !result.success) {
                throw new Error(
                    result?.message || `Upload failed: ${file.name}`
                );
            }

            successfulUploads++;

            processingResults.push({
                fileName: file.name,
                result: result.processing
            });
        }

        uploadStatus.textContent =
            `${successfulUploads} document(s) uploaded and processed successfully.`;

        console.log("Document processing completed:", processingResults);

        documentFiles.value = "";
        await refreshStatus();

    } catch (error) {
        uploadStatus.textContent =
            `${successfulUploads}/${files.length} document(s) completed. ${error.message}`;

    } finally {
        uploadDocumentsButton.disabled = false;
    }
});

// Fill current website
fillFormButton.addEventListener("click", async () => {
    fillFormButton.disabled = true;
    showStatus("Analyzing website form...");

    try {
        const result = await sendMessage("FILL_CURRENT_TAB");

        if (!result || !result.success) {
            throw new Error(
                result?.message || "Unable to fill this form."
            );
        }

        showStatus(
            `Form filling completed. Filled: ${result.filled || 0}, Skipped: ${result.skipped || 0}`
        );

    } catch (error) {
        showStatus(error.message);

    } finally {
        fillFormButton.disabled = false;
    }
});

// Initialize popup
refreshStatus();
