
document.addEventListener("DOMContentLoaded", () => {

    const fillFormButton = document.getElementById("fillFormButton");
    const refreshProfileButton = document.getElementById("refreshProfileButton");
    const connectProfileButton = document.getElementById("connectProfileButton");

    const profileIdInput = document.getElementById("profileIdInput");
    const profileStatus = document.getElementById("profileStatus");
    const statusMessage = document.getElementById("statusMessage");


    // Display status messages
    function showStatus(message) {
        statusMessage.textContent = message;
    }


    // Load the saved profile ID
    async function loadProfile() {

        profileStatus.textContent = "Checking profile...";

        const stored = await chrome.storage.local.get("profileId");

        if (stored.profileId) {
            profileIdInput.value = stored.profileId;
            profileStatus.textContent = "Profile ID connected. Checking backend...";
        } else {
            profileStatus.textContent = "No profile connected. Enter your Profile ID.";
            return;
        }

        chrome.runtime.sendMessage(
            { type: "GET_PROFILE_STATUS" },
            (response) => {

                if (chrome.runtime.lastError) {
                    profileStatus.textContent = "Could not connect to backend.";
                    return;
                }

                if (response && response.success && response.profileAvailable) {
                    profileStatus.textContent = "Student profile connected successfully.";
                } else {
                    profileStatus.textContent = "Profile unavailable. Check the Profile ID and backend.";
                }

            }
        );
    }


    // Connect a saved profile
    connectProfileButton.addEventListener("click", async () => {

        const profileId = profileIdInput.value.trim();

        if (!profileId) {
            showStatus("Please enter your Profile ID.");
            return;
        }

        await chrome.storage.local.set({ profileId });

        showStatus("Profile ID saved.");

        loadProfile();

    });


    // Refresh profile information
    refreshProfileButton.addEventListener("click", () => {

        loadProfile();
        showStatus("Refreshing profile...");

    });


    // Request autofill
    fillFormButton.addEventListener("click", () => {

        fillFormButton.disabled = true;
        showStatus("Preparing to fill the website...");

        chrome.runtime.sendMessage(
            { type: "FILL_CURRENT_TAB" },
            (response) => {

                fillFormButton.disabled = false;

                if (chrome.runtime.lastError) {
                    showStatus("Extension communication failed.");
                    return;
                }

                if (response && response.success) {
                    showStatus(response.message || "Form filling completed.");
                } else {
                    showStatus(
                        response?.message || "Unable to fill this website."
                    );
                }

            }
        );

    });


    // Initialize popup
    loadProfile();

});
