
// ==========================================
// DOM ELEMENTS
// ==========================================

const pdfInput = document.getElementById("pdfInput");
const uploadButton = document.getElementById("uploadButton");
const statusText = document.getElementById("status");

const reviewSection = document.getElementById("reviewSection");
const fieldsContainer = document.getElementById("fieldsContainer");
const reviewStatus = document.getElementById("reviewStatus");

const saveChangesButton = document.getElementById("saveChangesButton");
const saveProfileButton = document.getElementById("saveProfileButton");
const proceedButton = document.getElementById("proceedButton");

const formSection = document.getElementById("formSection");
const fillFormButton = document.getElementById("fillFormButton");
const submitFormButton = document.getElementById("submitFormButton");


// ==========================================
// APPLICATION STATE
// ==========================================

let currentExtractedDocumentId = null;
let currentProfileId = null;
let currentFields = {};


// ==========================================
// INITIAL UI SETUP
// ==========================================

// Old workflow buttons are no longer needed.
if (saveChangesButton) {
    saveChangesButton.hidden = true;
}

if (saveProfileButton) {
    saveProfileButton.hidden = true;
}

proceedButton.hidden = true;
reviewSection.hidden = true;
formSection.hidden = true;


// ==========================================
// PROFILE FIELD MAPPING
// ==========================================

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


// ==========================================
// DISPLAY EXTRACTED INFORMATION
// ==========================================

function renderFields(details) {
    fieldsContainer.replaceChildren();

    currentFields = getProfileFields(details);

    for (const [fieldName, value] of Object.entries(currentFields)) {
        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {
            continue;
        }

        const field = document.createElement("div");
        field.className = "field";

        const label = document.createElement("label");
        label.textContent = formatLabel(fieldName);

        const input = document.createElement("input");
        input.type = "text";
        input.value = String(value);
        input.readOnly = true;

        // Aadhaar is masked by the backend.
        // Never attempt to autofill the masked value.
        if (fieldName === "aadhaar_number") {
            input.readOnly = true;
        }

        field.append(label, input);
        fieldsContainer.appendChild(field);
    }
}


// ==========================================
// UPLOAD AND PROCESS PDF
// ==========================================

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
    formSection.hidden = true;
    proceedButton.hidden = true;

    currentExtractedDocumentId = null;
    currentProfileId = null;
    currentFields = {};

    try {
        // STEP 1: Create session

        statusText.textContent = "Creating session...";

        const sessionId = await createSession();


        // STEP 2: Upload PDF

        statusText.textContent = "Uploading PDF...";

        const uploadData = await uploadPDF(sessionId, file);


        // STEP 3: Classify documents

        statusText.textContent = "Classifying documents...";

        const classificationData = await classifyDocument(
            uploadData.document_id
        );


        // STEP 4: Find Aadhaar document

        const identityDocument = classificationData.documents.find(
            doc =>
                doc.document_type === "identity_document" &&
                doc.document_subtype === "aadhaar"
        );

        if (!identityDocument) {
            throw new Error(
                "No Aadhaar document detected. Currently, this frontend workflow supports Aadhaar extraction."
            );
        }

        currentExtractedDocumentId =
            identityDocument.extracted_document_id;


        // STEP 5: Extract Aadhaar details

        statusText.textContent = "Extracting Aadhaar information...";

        const extractionData = await extractAadhaar(
            currentExtractedDocumentId
        );


        // STEP 6: Display extracted information

        renderFields(extractionData.details);

        reviewStatus.textContent = "Extraction completed";

        reviewSection.hidden = false;
        proceedButton.hidden = false;

        statusText.textContent =
            "Documents processed successfully. Click Proceed to save your profile.";

    } catch (error) {
        console.error("Processing error:", error);
        statusText.textContent = error.message;

    } finally {
        uploadButton.disabled = false;
    }
});


// ==========================================
// PROCEED — SAVE DRAFT PROFILE
// ==========================================

proceedButton.addEventListener("click", async () => {
    if (!currentExtractedDocumentId) {
        statusText.textContent = "Please upload and process a PDF first.";
        return;
    }

    try {
        proceedButton.disabled = true;

        statusText.textContent = "Saving your profile...";

        // Save extracted information as a draft.
        const result = await saveProfile(
            currentExtractedDocumentId
        );

        currentProfileId = result.profile_id;

        if (!currentProfileId) {
            throw new Error("Profile was saved but no profile ID was returned.");
        }

        reviewStatus.textContent = "Profile saved successfully";

        // Open registration form.
        reviewSection.hidden = true;
        formSection.hidden = false;

        statusText.textContent =
            "Your profile has been saved. Click Fill Form to populate the registration form.";

        console.log("Saved profile ID:", currentProfileId);

    } catch (error) {
        console.error("Profile saving error:", error);
        statusText.textContent = error.message;

    } finally {
        proceedButton.disabled = false;
    }
});


// ==========================================
// FILL FORM FROM SAVED DATABASE PROFILE
// ==========================================

fillFormButton.addEventListener("click", async () => {
    if (!currentProfileId) {
        statusText.textContent =
            "No saved profile found. Please process your PDF first.";
        return;
    }

    try {
        fillFormButton.disabled = true;

        statusText.textContent = "Retrieving your saved profile...";

        // Retrieve saved profile from PostgreSQL.
        const savedProfile = await getSavedProfile(currentProfileId);

        const profile = savedProfile.profile_data || {};

        const formMapping = {
            formName: profile.full_name,
            formDOB: profile.date_of_birth,
            formGender: profile.gender,
            formAddress: profile.address,
            formFather: profile.father_or_husband_name
        };

        let filledCount = 0;
        let preservedCount = 0;
        let skippedCount = 0;

        for (const [elementId, value] of Object.entries(formMapping)) {
            const input = document.getElementById(elementId);

            if (!input) {
                console.warn(`Form element not found: ${elementId}`);
                continue;
            }

            // Attach manual-edit tracking only once.
            if (input.dataset.editTrackingAttached !== "true") {
                input.addEventListener("input", () => {
                    const previousAutofill = input.dataset.autofilledValue;

                    if (
                        previousAutofill !== undefined &&
                        input.value !== previousAutofill
                    ) {
                        input.dataset.manuallyEdited = "true";
                    }
                });

                input.dataset.editTrackingAttached = "true";
            }

            // Skip missing profile values.
            if (
                value === null ||
                value === undefined ||
                String(value).trim() === ""
            ) {
                skippedCount++;
                continue;
            }

            const newValue = String(value);
            const currentValue = input.value.trim();

            // Preserve fields manually edited by the user.
            if (input.dataset.manuallyEdited === "true") {
                preservedCount++;
                continue;
            }

            // If a field contains a value that was not filled
            // by our autofill, treat it as manually entered.
            const previousAutofill = input.dataset.autofilledValue;

            if (
                currentValue !== "" &&
                previousAutofill === undefined
            ) {
                input.dataset.manuallyEdited = "true";
                preservedCount++;
                continue;
            }

            // If the field was autofilled earlier but not edited,
            // it can safely be refreshed from the saved profile.
            input.value = newValue;
            input.dataset.autofilledValue = newValue;

            input.dispatchEvent(
                new Event("change", { bubbles: true })
            );

            filledCount++;
        }

        statusText.textContent =
            `${filledCount} fields filled/refreshed. ` +
            `${preservedCount} manually edited fields preserved. ` +
            `${skippedCount} fields skipped.`;

    } catch (error) {
        console.error("Form filling error:", error);
        statusText.textContent = error.message;

    } finally {
        fillFormButton.disabled = false;
    }
});

// ==========================================
// MULTI-PAGE FORM NAVIGATION
// ==========================================

const formPages = document.querySelectorAll(".form-page");

const previousPageButton =
    document.getElementById("previousPageButton");

const nextPageButton =
    document.getElementById("nextPageButton");

const finalSubmitButton =
    document.getElementById("finalSubmitButton");

const pageTitle = document.getElementById("pageTitle");
const pageCounter = document.getElementById("pageCounter");
const progressBar = document.getElementById("progressBar");

const pageTitles = [
    "Personal Information",
    "Class 10 (SSLC) Information",
    "Class 12 (PUC) Information",
    "Engineering Information",
    "Review & Submit"
];

let currentPage = 1;
const totalPages = formPages.length;


// Display selected page
function showPage(pageNumber) {

    currentPage = pageNumber;

    formPages.forEach((page) => {

        const pageNumberInForm = Number(page.dataset.page);

        page.hidden = pageNumberInForm !== currentPage;

        page.classList.toggle(
            "active",
            pageNumberInForm === currentPage
        );

    });

    // Update heading
    pageTitle.textContent = pageTitles[currentPage - 1];

    pageCounter.textContent =
        `Page ${currentPage} of ${totalPages}`;

    // Update progress bar
    progressBar.style.width =
        `${(currentPage / totalPages) * 100}%`;

    // Previous button
    previousPageButton.disabled = currentPage === 1;

    // Next and Submit buttons
    nextPageButton.hidden = currentPage === totalPages;
    finalSubmitButton.hidden = currentPage !== totalPages;

    // Generate review on final page
    if (currentPage === totalPages) {
        generateFinalReview();
    }

    // Scroll to top of form
    formSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


// Next button
nextPageButton.addEventListener("click", () => {

    if (currentPage < totalPages) {
        showPage(currentPage + 1);
    }

});


// Previous button
previousPageButton.addEventListener("click", () => {

    if (currentPage > 1) {
        showPage(currentPage - 1);
    }

});


// ==========================================
// FINAL REVIEW
// ==========================================

function generateFinalReview() {

    const reviewContainer =
        document.getElementById("finalReview");

    reviewContainer.replaceChildren();

    const reviewGroups = [
        {
            title: "Personal Information",
            ids: [
                "formName",
                "formDOB",
                "formGender",
                "formAadhaar",
                "formFather",
                "formMother",
                "formAddress",
                "formMobile",
                "formEmail"
            ]
        },
        {
            title: "Class 10 (SSLC)",
            ids: [
                "sslcBoard",
                "sslcSchool",
                "sslcRegNo",
                "sslcRollNo",
                "sslcYear",
                "sslcEnglish",
                "sslcLanguage",
                "sslcMaths",
                "sslcScience",
                "sslcSocial",
                "sslcTotal",
                "sslcPercentage",
                "sslcGrade",
                "sslcResult"
            ]
        },
        {
            title: "Class 12 (PUC)",
            ids: [
                "pucBoard",
                "pucCollege",
                "pucRegNo",
                "pucRollNo",
                "pucYear",
                "pucStream",
                "pucEnglish",
                "pucLanguage",
                "pucSubject1",
                "pucSubject2",
                "pucSubject3",
                "pucSubject4",
                "pucTotal",
                "pucPercentage",
                "pucGrade",
                "pucResult"
            ]
        },
        {
            title: "Engineering Information",
            ids: [
                "engUniversity",
                "engCollege",
                "engUSN",
                "engBranch",
                "engSemester",
                "engAcademicYear",
                "engCGPA",
                "engBacklogs",
                "sgpa1",
                "sgpa2",
                "sgpa3",
                "sgpa4",
                "sgpa5",
                "sgpa6",
                "sgpa7",
                "sgpa8"
            ]
        }
    ];

    reviewGroups.forEach(group => {

        const section = document.createElement("div");
        section.className = "review-group";

        const heading = document.createElement("h4");
        heading.textContent = group.title;

        section.appendChild(heading);

        group.ids.forEach(id => {

            const input = document.getElementById(id);

            if (!input || !input.value.trim()) {
                return;
            }

            const row = document.createElement("p");

            const label = document.querySelector(
                `label[for="${id}"]`
            );

            const fieldName = label
                ? label.textContent
                : id;

            row.textContent =
                `${fieldName}: ${input.value}`;

            section.appendChild(row);

        });

        reviewContainer.appendChild(section);

    });

}


// ==========================================
// FINAL SUBMISSION
// ==========================================

finalSubmitButton.addEventListener("click", () => {

    const confirmation =
        document.getElementById("confirmInformation");

    if (!confirmation.checked) {

        statusText.textContent =
            "Please confirm that your information is correct.";

        return;
    }

    // This is currently a frontend demo.
    // Actual database submission will be implemented separately.

    statusText.textContent =
        "Registration form completed successfully! Backend submission is not connected yet.";

    console.log("Student registration form data:");

    const formData = {};

    document.querySelectorAll(
        "#formSection input, #formSection select, #formSection textarea"
    ).forEach(input => {

        if (input.id) {
            formData[input.id] =
                input.type === "checkbox"
                    ? input.checked
                    : input.value;
        }

    });

    console.log(formData);

});


// Start on page 1
showPage(1);
