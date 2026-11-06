
const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

// Retrieve the saved profile ID and fetch the profile
async function getSavedProfile() {

    const stored = await chrome.storage.local.get("profileId");
    const profileId = stored.profileId;

    if (!profileId) {
        throw new Error("No profile ID found. Connect your student profile first.");
    }

    const response = await fetch(
        `${API_BASE_URL}/documents/profiles/${encodeURIComponent(profileId)}`
    );

    if (!response.ok) {
        throw new Error(`Backend request failed: ${response.status}`);
    }

    return await response.json();
}


// Check whether a saved profile is available
async function checkProfileStatus() {

    try {
        const profile = await getSavedProfile();

        return {
            success: true,
            profileAvailable: !!profile
        };

    } catch (error) {

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

        // Get the active browser tab
        const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true
        });

        if (!tab || !tab.id || !tab.url) {
            throw new Error("Unable to identify the active website.");
        }

        // Avoid browser-internal pages
        if (
            tab.url.startsWith("chrome://") ||
            tab.url.startsWith("chrome-extension://") ||
            tab.url.startsWith("https://chrome.google.com/webstore")
        ) {
            throw new Error("This page cannot be autofilled.");
        }

        // Retrieve the saved student profile
        const profile = await getSavedProfile();

        // Inject the website interaction script
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ["content.js"]
        });

        // Send profile information to the website script
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


// Listen for messages from popup.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

    if (message.type === "GET_PROFILE_STATUS") {

        checkProfileStatus().then(sendResponse);
        return true;

    }

    if (message.type === "FILL_CURRENT_TAB") {

        fillCurrentTab().then(sendResponse);
        return true;

    }

});
