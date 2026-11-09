
// Prevent registering the message listener multiple times
if (!window.aiFormAssistantListenerAdded) {
    window.aiFormAssistantListenerAdded = true;

    console.log("AI Form Assistant content script loaded.");

    // Normalize text for reliable matching
    function normalize(text) {
        return String(text || "")
            .toLowerCase()
            .replace(/[^a-z0-9]/g, "");
    }

    // Explicit aliases for supported profile fields
    const FIELD_ALIASES = {
        full_name: ["fullname", "studentname", "applicantname"],
        date_of_birth: ["dateofbirth", "dob", "birthdate"],
        gender: ["gender", "sex"],

        father_or_husband_name: [
            "fathername",
            "husbandname",
            "fatherorhusbandname"
        ],

        mobile_number: [
            "mobilenumber",
            "phonenumber",
            "contactnumber"
        ],

        email: ["email", "emailaddress"],

        address: [
            "fulladdress",
            "completeaddress",
            "residentialaddress"
        ],

        address_city: ["city", "addresscity"],
        address_state: ["state", "addressstate"],
        address_district: ["district", "addressdistrict"],
        address_pincode: ["pincode", "postalcode", "zipcode"],

        address_street: ["street", "streetaddress", "addressstreet"],
        address_locality: ["locality", "addresslocality"],
        address_house_number: ["housenumber", "addresshousenumber"],

        school_name: ["schoolname"],
        board: ["board", "educationboard"],
        college_name: ["collegename"],
        university_name: ["universityname"],
        degree: ["degree"],
        branch: ["branch", "department"],
        stream: ["stream"],
        usn: ["usn", "universityseatnumber"],
        year_of_passing: ["yearofpassing", "passingyear"],
        cgpa: ["cgpa"],
        percentage: ["percentage"]
    };

    // Get field identifiers in priority order
    function getFieldDescriptions(field) {
        const descriptions = [];

        function add(value, priority) {
            const normalized = normalize(value);

            if (normalized) {
                descriptions.push({
                    value: normalized,
                    priority
                });
            }
        }

        add(field.name, 100);
        add(field.id, 95);
        add(field.getAttribute("autocomplete"), 90);
        add(field.getAttribute("aria-label"), 85);

        if (field.labels) {
            for (const label of field.labels) {
                add(label.innerText, 80);
            }
        }

        const parentLabel = field.closest("label");

        if (parentLabel) {
            add(parentLabel.innerText, 75);
        }

        add(field.placeholder, 60);

        return descriptions;
    }

    // Convert saved profile into searchable mappings
    function buildProfileMappings(profile) {
        const mappings = [];

        function inspect(object) {
            if (!object || typeof object !== "object") {
                return;
            }

            for (const [key, value] of Object.entries(object)) {

                if (
                    value &&
                    typeof value === "object" &&
                    !Array.isArray(value)
                ) {
                    inspect(value);
                    continue;
                }

                if (
                    value === null ||
                    value === undefined ||
                    String(value).trim() === ""
                ) {
                    continue;
                }

                const normalizedKey = normalize(key);

                // Never include Aadhaar or UID
                if (
                    normalizedKey.includes("aadhaar") ||
                    normalizedKey.includes("uid")
                ) {
                    continue;
                }

                const aliases = FIELD_ALIASES[key] || [];

                mappings.push({
                    key: normalizedKey,
                    aliases: [
                        normalizedKey,
                        ...aliases.map(normalize)
                    ],
                    value: String(value).trim()
                });
            }
        }

        inspect(profile);

        return mappings;
    }

    // Find the best matching profile value
    function findMatchingValue(field, mappings) {
        const descriptions = getFieldDescriptions(field);

        if (!descriptions.length) {
            return null;
        }

        // Never autofill sensitive or credential fields
        const forbidden = [
            "aadhaar",
            "uid",
            "password",
            "otp",
            "captcha",
            "creditcard"
        ];

        if (
            descriptions.some(description =>
                forbidden.some(word =>
                    description.value.includes(word)
                )
            )
        ) {
            return null;
        }

        const candidates = [];

        for (const description of descriptions) {
            for (const mapping of mappings) {
                for (const alias of mapping.aliases) {

                    if (!alias || alias.length < 3) {
                        continue;
                    }

                    // Exact matching only
                    if (description.value === alias) {
                        candidates.push({
                            mapping,
                            priority: description.priority,
                            aliasLength: alias.length
                        });
                    }
                }
            }
        }

        if (!candidates.length) {
            return null;
        }

        candidates.sort((a, b) =>
            b.priority - a.priority ||
            b.aliasLength - a.aliasLength
        );

        return candidates[0].mapping.value;
    }

    // Set values using native setters
    function setNativeValue(field, value) {
        let prototype;

        if (field instanceof HTMLTextAreaElement) {
            prototype = HTMLTextAreaElement.prototype;
        } else if (field instanceof HTMLSelectElement) {
            prototype = HTMLSelectElement.prototype;
        } else {
            prototype = HTMLInputElement.prototype;
        }

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
    }

    // Handle date formats
    function prepareValue(field, value) {
        if (field.type === "date") {

            const iso = String(value).match(
                /^(\d{4})-(\d{2})-(\d{2})$/
            );

            if (iso) {
                return value;
            }

            const indian = String(value).match(
                /^(\d{2})-(\d{2})-(\d{4})$/
            );

            if (indian) {
                return `${indian[3]}-${indian[2]}-${indian[1]}`;
            }
        }

        return String(value);
    }

    // Fill text, date and other supported inputs
    function fillInput(field, value) {

        // Preserve existing values
        if (String(field.value).trim() !== "") {
            return false;
        }

        if (
            field.disabled ||
            field.readOnly ||
            [
                "hidden",
                "password",
                "file",
                "submit",
                "button",
                "reset",
                "checkbox",
                "radio"
            ].includes(field.type)
        ) {
            return false;
        }

        const preparedValue = prepareValue(field, value);

        try {
            setNativeValue(field, preparedValue);
            return true;
        } catch (error) {
            console.warn(
                "Could not fill field:",
                field,
                error
            );

            return false;
        }
    }

    // Fill dropdowns
    function fillSelect(field, value) {

        if (field.value !== "" || field.disabled) {
            return false;
        }

        const wanted = normalize(value);

        const matchingOption = Array.from(
            field.options
        ).find(option => {

            return (
                normalize(option.textContent) === wanted ||
                normalize(option.value) === wanted
            );
        });

        if (!matchingOption) {
            return false;
        }

        setNativeValue(field, matchingOption.value);

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

            const value = findMatchingValue(
                field,
                mappings
            );

            if (value === null) {
                skippedCount++;
                return;
            }

            const filled = field.tagName === "SELECT"
                ? fillSelect(field, value)
                : fillInput(field, value);

            if (filled) {
                filledCount++;

                console.log(
                    "Autofilled:",
                    field.name || field.id
                );
            } else {
                skippedCount++;
            }
        });

        return {
            success: true,
            message: `Filled ${filledCount} fields. ${skippedCount} skipped.`,
            filledCount,
            skippedCount
        };
    }

    // Receive autofill requests from background.js
    chrome.runtime.onMessage.addListener(
        (message, sender, sendResponse) => {

            if (message.type === "FILL_FORM") {
                try {
                    const result = fillWebsiteForm(
                        message.profile
                    );

                    sendResponse(result);

                } catch (error) {

                    console.error(
                        "Autofill error:",
                        error
                    );

                    sendResponse({
                        success: false,
                        message: "An error occurred while filling the form."
                    });
                }
            }

            return true;
        }
    );
}
