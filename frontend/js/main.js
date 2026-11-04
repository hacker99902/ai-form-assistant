
const pdfInput = document.getElementById("pdfInput");
const uploadButton = document.getElementById("uploadButton");
const statusText = document.getElementById("status");
const reviewSection = document.getElementById("reviewSection");
const fieldsContainer = document.getElementById("fieldsContainer");
const reviewStatus = document.getElementById("reviewStatus");
const saveChangesButton = document.getElementById("saveChangesButton");
const saveProfileButton = document.getElementById("saveProfileButton");

let currentExtractedDocumentId = null;
let currentFields = {};

// Convert extracted details into backend profile field names.
function getProfileFields(details) {
    const fields = {
        full_name: details.full_name,
        aadhaar_number: details.aadhaar_number,
        date_of_birth: details.date_of_birth,
        year_of_birth: details.year_of_birth,
        gender: details.gender,
        address: details.address,
        father_or_husband_name: details.father_or_husband_name
    };

    const address = details.address_components || {};

    fields.address_house_number = address.house_number;
    fields.address_street = address.street;
    fields.address_locality = address.locality;
    fields.address_city = address.city;
    fields.address_district = address.district;
    fields.address_state = address.state;
    fields.address_pincode = address.pincode;

    return fields;
}

function formatLabel(fieldName) {
    return fieldName
        .replace(/^address_/, "Address ")
        .replaceAll("_", " ")
        .replace(/\b\w/g, char => char.toUpperCase());
}

function renderFields(details) {
    fieldsContainer.replaceChildren();

    currentFields = getProfileFields(details);

    for (const [fieldName, originalValue] of Object.entries(currentFields)) {

        if (originalValue === null || originalValue === undefined || originalValue === "") {
            continue;
        }

        const field = document.createElement("div");
        field.className = "field";

        const label = document.createElement("label");
        label.textContent = formatLabel(fieldName);

        const input = document.createElement("input");
        input.type = "text";
        input.value = String(originalValue);
        input.dataset.fieldName = fieldName;

        // Aadhaar is masked by the backend.
        // Do not send a masked value as a correction.
        if (fieldName === "aadhaar_number") {
            input.readOnly = true;
        }

        const fieldStatus = document.createElement("p");
        fieldStatus.className = "field-status";
        fieldStatus.textContent = "Needs review";

        const verifyButton = document.createElement("button");
        verifyButton.type = "button";
        verifyButton.textContent = "Verify";

        verifyButton.addEventListener("click", async () => {
            try {
                verifyButton.disabled = true;
                fieldStatus.textContent = "Verifying...";

                await verifyProfileField(
                    currentExtractedDocumentId,
                    fieldName
                );

                fieldStatus.textContent = "Verified";
                fieldStatus.style.color = "green";
                verifyButton.textContent = "Verified";

            } catch (error) {
                fieldStatus.textContent = error.message;
                verifyButton.disabled = false;
            }
        });

        field.append(label, input, fieldStatus, verifyButton);
        fieldsContainer.appendChild(field);
    }
}

// Upload and process PDF.
uploadButton.addEventListener("click", async () => {

    const file = pdfInput.files[0];

    if (!file) {
        statusText.textContent = "Please select a PDF first.";
        return;
    }

    if (
        file.type !== "application/pdf" &&
        !file.name.toLowerCase().endsWith(".pdf")
    ) {
        statusText.textContent = "Please select a valid PDF.";
        return;
    }

    if (file.size > 20 * 1024 * 1024) {
        statusText.textContent = "PDF must be smaller than 20 MB.";
        return;
    }

    uploadButton.disabled = true;
    reviewSection.hidden = true;
    currentExtractedDocumentId = null;

    try {
        statusText.textContent = "Creating session...";

        const sessionId = await createSession();

        statusText.textContent = "Uploading PDF...";

        const uploadData = await uploadPDF(sessionId, file);

        statusText.textContent = "Classifying documents...";

        const classificationData = await classifyDocument(
            uploadData.document_id
        );

        const identityDocument = classificationData.documents.find(
            doc => doc.document_type === "identity_document"
        );

        if (!identityDocument) {
            throw new Error(
                "No identity document was detected. Marksheet and resume extraction will be added next."
            );
        }

        currentExtractedDocumentId =
            identityDocument.extracted_document_id;

        statusText.textContent = "Extracting Aadhaar information...";

        const extractionData = await extractAadhaar(
            currentExtractedDocumentId
        );

        renderFields(extractionData.details);

        reviewStatus.textContent = "Needs review";

        reviewSection.hidden = false;

        statusText.textContent =
            "Extraction completed. Please review your information.";

    } catch (error) {
        console.error("Processing error:", error);
        statusText.textContent = error.message;

    } finally {
        uploadButton.disabled = false;
    }
});

// Save user corrections.
saveChangesButton.addEventListener("click", async () => {

    if (!currentExtractedDocumentId) return;

    try {
        saveChangesButton.disabled = true;

        const updatedFields = {};

        const inputs = fieldsContainer.querySelectorAll(
            "input[data-field-name]"
        );

        for (const input of inputs) {
            const fieldName = input.dataset.fieldName;

            if (fieldName === "aadhaar_number") {
                continue;
            }

            const newValue = input.value.trim();

            if (newValue && newValue !== String(currentFields[fieldName])) {
                updatedFields[fieldName] = newValue;
            }
        }

        if (Object.keys(updatedFields).length === 0) {
            statusText.textContent = "No corrections to save.";
            return;
        }

        await updateProfileFields(
            currentExtractedDocumentId,
            updatedFields
        );

        Object.assign(currentFields, updatedFields);

        // A corrected field must be verified again.
        for (const field of fieldsContainer.querySelectorAll(".field")) {
            const input = field.querySelector("input");
            const fieldStatus = field.querySelector(".field-status");
            const verifyButton = field.querySelector("button");

            if (Object.hasOwn(updatedFields, input.dataset.fieldName)) {
                fieldStatus.textContent = "Corrected — needs verification";
                fieldStatus.style.color = "";
                verifyButton.disabled = false;
                verifyButton.textContent = "Verify";
            }
        }

        statusText.textContent = "Corrections saved successfully.";

    } catch (error) {
        statusText.textContent = error.message;

    } finally {
        saveChangesButton.disabled = false;
    }
});

// Save the profile after all fields are verified.
saveProfileButton.addEventListener("click", async () => {

    if (!currentExtractedDocumentId) return;

    try {
        saveProfileButton.disabled = true;
        statusText.textContent = "Saving verified profile...";

        const result = await saveVerifiedProfile(
            currentExtractedDocumentId
        );

        reviewStatus.textContent = "Profile saved";

        statusText.textContent =
            "Verified profile saved successfully.";

        console.log("Profile saved:", result);

    } catch (error) {
        statusText.textContent = error.message;

    } finally {
        saveProfileButton.disabled = false;
    }
});
