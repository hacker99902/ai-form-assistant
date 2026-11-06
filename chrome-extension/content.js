
// Prevent registering the message listener multiple times
if (!window.aiFormAssistantListenerAdded) {

    window.aiFormAssistantListenerAdded = true;

    console.log("AI Form Assistant content script loaded.");

    // Normalize field names for matching
    function normalize(text) {
        return String(text || "")
            .toLowerCase()
            .replace(/[^a-z0-9]/g, "");
    }


    // Get the label or identifying text of an input
    function getFieldDescription(field) {

        const parts = [
            field.name,
            field.id,
            field.placeholder,
            field.getAttribute("aria-label"),
            field.getAttribute("autocomplete")
        ];

        if (field.labels) {
            for (const label of field.labels) {
                parts.push(label.innerText);
            }
        }

        const parentLabel = field.closest("label");

        if (parentLabel) {
            parts.push(parentLabel.innerText);
        }

        return parts.filter(Boolean).join(" ");
    }


    // Convert the saved profile into searchable field mappings
    function buildProfileMappings(profile) {

        const mappings = [];

        function addMapping(keys, value) {

            if (
                value === null ||
                value === undefined ||
                String(value).trim() === ""
            ) {
                return;
            }

            mappings.push({
                keys: keys.map(normalize),
                value: String(value).trim()
            });
        }

        // Recursively inspect profile objects
        function inspectObject(object, prefix = "") {

            if (!object || typeof object !== "object") {
                return;
            }

            for (const [key, value] of Object.entries(object)) {

                const fullKey = prefix
                    ? `${prefix} ${key}`
                    : key;

                if (value && typeof value === "object") {
                    inspectObject(value, fullKey);
                } else {
                    addMapping([key, fullKey], value);
                }
            }
        }

        inspectObject(profile);

        return mappings;
    }


    // Find the best matching profile value
    function findMatchingValue(description, mappings) {

        const fieldName = normalize(description);

        if (!fieldName) {
            return null;
        }

        // Aadhaar is deliberately excluded from automatic retrieval
        if (
            fieldName.includes("aadhaar") ||
            fieldName.includes("uid")
        ) {
            return null;
        }

        for (const mapping of mappings) {

            for (const key of mapping.keys) {

                if (!key || key.length < 3) {
                    continue;
                }

                if (
                    fieldName.includes(key) ||
                    key.includes(fieldName)
                ) {
                    return mapping.value;
                }
            }
        }

        return null;
    }


    // Fill a normal input field
    function fillInput(field, value) {

        // Preserve existing user-entered information
        if (field.value.trim() !== "") {
            return false;
        }

        if (
            field.type === "hidden" ||
            field.type === "password" ||
            field.type === "file" ||
            field.type === "submit" ||
            field.type === "button"
        ) {
            return false;
        }

        if (
            field.type === "checkbox" ||
            field.type === "radio"
        ) {
            return false;
        }

        const prototype = field instanceof HTMLTextAreaElement
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;

        const setter = Object.getOwnPropertyDescriptor(
            prototype,
            "value"
        )?.set;

        if (setter) {
            setter.call(field, value);
        } else {
            field.value = value;
        }

        field.dispatchEvent(
            new Event("input", { bubbles: true })
        );

        field.dispatchEvent(
            new Event("change", { bubbles: true })
        );

        return true;
    }


    // Fill dropdowns when an option matches
    function fillSelect(field, value) {

        if (field.value !== "") {
            return false;
        }

        const wanted = normalize(value);

        const matchingOption = Array.from(field.options).find(option => {

            const optionText = normalize(option.textContent);
            const optionValue = normalize(option.value);

            return (
                optionText === wanted ||
                optionValue === wanted
            );
        });

        if (!matchingOption) {
            return false;
        }

        field.value = matchingOption.value;

        field.dispatchEvent(
            new Event("change", { bubbles: true })
        );

        return true;
    }


    // Main autofill operation
    function fillWebsiteForm(profile) {

        const mappings = buildProfileMappings(profile);

        const fields = document.querySelectorAll(
            "input:not([type='hidden']), textarea, select"
        );

        let filledCount = 0;
        let skippedCount = 0;

        fields.forEach(field => {

            const description = getFieldDescription(field);

            const value = findMatchingValue(
                description,
                mappings
            );

            if (!value) {
                skippedCount++;
                return;
            }

            let filled = false;

            if (field.tagName === "SELECT") {
                filled = fillSelect(field, value);
            } else {
                filled = fillInput(field, value);
            }

            if (filled) {
                filledCount++;
            } else {
                skippedCount++;
            }

        });

        return {
            success: true,
            message: `Filled ${filledCount} fields. ${skippedCount} fields were skipped.`,
            filledCount,
            skippedCount
        };
    }


    // Receive autofill requests from background.js
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

        if (message.type === "FILL_FORM") {

            try {

                const result = fillWebsiteForm(message.profile);

                sendResponse(result);

            } catch (error) {

                console.error("Autofill error:", error);

                sendResponse({
                    success: false,
                    message: "An error occurred while filling the form."
                });

            }

        }

        return true;

    });

}
