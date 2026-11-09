// ==========================================
// AI FORM ASSISTANT - MAIN.JS
// Aadhaar + Class 10 + Class 12 + Engineering
// Multi-page autofill with manual-edit preservation
// ==========================================


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


// ==========================================
// APPLICATION STATE
// ==========================================

let currentExtractedDocumentId = null;
let currentProfileId = null;
let currentFields = {};

let currentClass10DocumentId = null;
let currentClass12DocumentId = null;
let currentEngineeringDocumentIds = [];

let currentClass10Details = null;
let currentClass12Details = null;
let currentEngineeringDetails = [];

let academicExtractionErrors = [];
let originalMarksheetValues = {};


// Initial UI setup

if (saveChangesButton) saveChangesButton.hidden = true;
if (saveProfileButton) saveProfileButton.hidden = true;
if (proceedButton) proceedButton.hidden = true;
if (reviewSection) reviewSection.hidden = true;
if (formSection) formSection.hidden = true;


// ==========================================
// COMMON HELPERS
// ==========================================

function setStatus(message) {
    if (statusText) {
        statusText.textContent = message;
    }
}


function asText(value) {
    return value === null || value === undefined
        ? ""
        : String(value);
}


function firstAvailable(...values) {
    return values.find(value =>
        value !== null &&
        value !== undefined &&
        String(value).trim() !== ""
    ) ?? "";
}

function normalizeResult(value) {
    const result = asText(value).trim().toUpperCase();

    if (result === "PASS") return "Pass";
    if (result === "FAIL") return "Fail";
    if (result === "DISTINCTION") return "Distinction";

    return "";
}

function getStudent(details) {
    return details?.student || {};
}


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


function formatLabel(name) {
    return name
        .replace(/^address_/, "Address ")
        .replaceAll("_", " ")
        .replace(/\b\w/g, c => c.toUpperCase());
}


// ==========================================
// DISPLAY EXTRACTED AADHAAR INFORMATION
// ==========================================

function renderFields(details) {

    if (!fieldsContainer) return;

    fieldsContainer.replaceChildren();

    currentFields = getProfileFields(details);

    for (const [name, value] of Object.entries(currentFields)) {

        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {
            continue;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "field";

        const label = document.createElement("label");
        label.textContent = formatLabel(name);

        const input = document.createElement("input");
        input.type = "text";
        input.value = String(value);
        input.readOnly = true;

        wrapper.append(label, input);
        fieldsContainer.appendChild(wrapper);
    }
}


// ==========================================
// MARKSHEET EXTRACTION API
// ==========================================


async function extractAndGetMarksheet(id) {
    const base =
        `${API_BASE_URL}/documents/extracted/${encodeURIComponent(id)}`;

    // Automatic processing already extracted this marksheet.
    // Only retrieve its saved result.
    const response = await fetch(`${base}/review-marksheet`, {
        credentials: "include"
    });

    const review = await handleResponse(response);

    if (!review.details) {
        throw new Error(
            "No saved marksheet extraction was returned."
        );
    }

    console.log("Retrieved marksheet:", review.details);

    return review.details;
}


// ==========================================
// MARKSHEET HELPERS
// ==========================================

function getSemesters(details) {
    return Array.isArray(details?.semesters)
        ? details.semesters
        : [];
}


function getSubjects(details) {

    return getSemesters(details).flatMap(semester =>
        Array.isArray(semester.subjects)
            ? semester.subjects
            : []
    );
}


function subjectMarks(details, keywords) {

    const subjects = getSubjects(details);

    const found = subjects.find(subject => {

        const name = asText(
            subject.subject_name
        ).toLowerCase();

        const code = asText(
            subject.subject_code
        ).toLowerCase();

        return keywords.some(keyword =>
            name.includes(keyword) ||
            code.includes(keyword)
        );
    });

    return found
        ? firstAvailable(
            found.marks_obtained,
            found.total_marks
        )
        : "";
}


function getParentDetails() {

    const sources = [
        currentClass10Details,
        currentClass12Details,
        ...currentEngineeringDetails
    ].filter(Boolean);

    const fatherNames = [];
    const motherNames = [];

    sources.forEach(details => {

        const student = getStudent(details);

        if (student.father_name) {
            fatherNames.push(student.father_name);
        }

        if (student.mother_name) {
            motherNames.push(student.mother_name);
        }
    });

    return {
        father_name: firstAvailable(...fatherNames),
        mother_name: firstAvailable(...motherNames)
    };
}


// ==========================================
// CLASS 10 MAPPING
// ==========================================
function getClass10Mapping(details) {

    const student = getStudent(details);
    const semester = getSemesters(details)[0] || {};
    const subjects = semester.subjects || [];

    const totalMarks = subjects.reduce(
        (sum, subject) =>
            sum + (Number(subject.marks_obtained) || 0),
        0
    );

    const extractedTotal = firstAvailable(
        details.total_marks_obtained,
        semester.total_marks_obtained
    );

    const finalTotal = extractedTotal !== ""
        ? extractedTotal
        : totalMarks || "";

    // Do not guess the official maximum marks or percentage.
    const percentage = firstAvailable(
        details.percentage
    );

    return {

        sslcBoard: firstAvailable(
            student.board,
            details.board
        ),

        sslcSchool: firstAvailable(
            student.school_name,
            details.school_name
        ),

        sslcRegNo: student.registration_number,
        sslcRollNo: student.roll_number,

        sslcYear: firstAvailable(
            details.year_of_passing,
            semester.examination_year
        ),

        sslcEnglish: subjectMarks(
            details,
            ["english"]
        ),

        sslcLanguage: subjectMarks(
            details,
            [
                "kannada",
                "hindi",
                "sanskrit",
                "tamil",
                "telugu",
                "urdu",
                "malayalam",
                "language"
            ]
        ),

        sslcMaths: subjectMarks(
            details,
            ["mathematics", "math"]
        ),

        sslcScience: subjectMarks(
            details,
            ["science"]
        ),

        sslcSocial: subjectMarks(
            details,
            [
                "social science",
                "social studies",
                "social"
            ]
        ),

        sslcTotal: finalTotal,

        sslcPercentage: percentage,

        // No overall grade was extracted.
        sslcGrade: firstAvailable(
            details.grade,
            semester.grade
        ),

        sslcResult: normalizeResult(
            firstAvailable(
                details.overall_result,
                semester.result
            )
        )
    };
}

function normalizeResult(value) {
    const result = asText(value).trim().toUpperCase();

    if (result === "PASS") return "Pass";
    if (result === "FAIL") return "Fail";
    if (result === "DISTINCTION") return "Distinction";

    return "";
}
function getClass12Mapping(details) {

    const student = getStudent(details);
    const semester = getSemesters(details)[0] || {};
    const subjects = semester.subjects || [];

    const totalMarks = subjects.reduce(
        (sum, subject) =>
            sum + (Number(subject.marks_obtained) || 0),
        0
    );

    const maximumMarks = subjects.reduce(
        (sum, subject) =>
            sum + (Number(subject.maximum_marks) || 0),
        0
    );

    const extractedTotal = firstAvailable(
        details.total_marks_obtained,
        semester.total_marks_obtained
    );

    const extractedMaximum = firstAvailable(
        details.maximum_marks,
        semester.maximum_marks
    );

    const finalTotal = extractedTotal !== ""
        ? extractedTotal
        : totalMarks || "";

    const finalMaximum = extractedMaximum !== ""
        ? extractedMaximum
        : maximumMarks || "";

    const calculatedPercentage =
        finalMaximum && finalTotal !== ""
            ? (
                Number(finalTotal) /
                Number(finalMaximum) * 100
            ).toFixed(2)
            : "";

    const markAt = index => {
        const subject = subjects[index];

        if (!subject) return "";

        return firstAvailable(
            subject.marks_obtained,
            subject.total_marks
        );
    };

    return {

        pucBoard: firstAvailable(
            student.board,
            details.board
        ),

        pucCollege: firstAvailable(
            student.college_name,
            details.college_name,
            student.school_name
        ),

        pucRegNo: student.registration_number,
        pucRollNo: student.roll_number,

        pucYear: firstAvailable(
            details.year_of_passing,
            semester.examination_year
        ),

        pucStream: firstAvailable(
            student.stream,
            details.stream,
            student.branch
        ),

        pucEnglish: subjectMarks(
            details,
            ["english"]
        ),

        pucLanguage: subjectMarks(
            details,
            [
                "kannada",
                "hindi",
                "sanskrit",
                "tamil",
                "telugu",
                "urdu",
                "malayalam",
                "language"
            ]
        ),

        pucSubject1: markAt(0),
        pucSubject2: markAt(1),
        pucSubject3: markAt(2),
        pucSubject4: markAt(3),

        pucTotal: finalTotal,

        pucPercentage: firstAvailable(
            details.percentage,
            calculatedPercentage
        ),

        pucGrade: firstAvailable(
            details.grade,
            semester.grade
        ),

        pucResult: normalizeResult(
            firstAvailable(
                details.overall_result,
                semester.result
            )
        )
    };
}
// ==========================================
// ENGINEERING MAPPING
// ==========================================

function getEngineeringMapping(documents) {

    const result = {
        engUniversity: "",
        engCollege: "",
        engUSN: "",
        engBranch: "",
        engSemester: "",
        engAcademicYear: "",
        engCGPA: "",
        engBacklogs: ""
    };

    const semesters = [];

    documents.forEach(details => {

        const student = getStudent(details);

        result.engUniversity = firstAvailable(
            result.engUniversity,
            student.university_name
        );

        result.engCollege = firstAvailable(
            result.engCollege,
            student.college_name
        );

        result.engUSN = firstAvailable(
            result.engUSN,
            student.usn
        );

        result.engBranch = firstAvailable(
            result.engBranch,
            student.branch,
            student.degree
        );

        result.engCGPA = firstAvailable(
            result.engCGPA,
            details.cgpa
        );

        result.engAcademicYear = firstAvailable(
            result.engAcademicYear,
            details.year_of_passing
        );

        semesters.push(...getSemesters(details));
    });

    semesters.sort((a, b) =>
        (Number(a.semester_number) || 999) -
        (Number(b.semester_number) || 999)
    );

    result.engSemester = semesters
        .map(s => s.semester_number)
        .filter(v => v !== null && v !== undefined)
        .join(", ");

    semesters.slice(0, 8).forEach((semester, index) => {

        result[`sgpa${index + 1}`] =
            semester.sgpa ?? "";
    });

    return result;
}


// ==========================================
// UPLOAD + CLASSIFICATION + EXTRACTION
// ==========================================

if (uploadButton) {
    uploadButton.addEventListener("click", async () => {
        const file = pdfInput?.files?.[0];

        if (!file) {
            return setStatus("Please select a PDF first.");
        }

        if (
            file.type !== "application/pdf" &&
            !file.name.toLowerCase().endsWith(".pdf")
        ) {
            return setStatus("Please select a valid PDF.");
        }

        if (file.size > 20 * 1024 * 1024) {
            return setStatus("PDF must be smaller than 20 MB.");
        }

        uploadButton.disabled = true;

        if (reviewSection) reviewSection.hidden = true;
        if (formSection) formSection.hidden = true;

        currentExtractedDocumentId = null;
        currentProfileId = null;
        currentFields = {};

        currentClass10Details = null;
        currentClass12Details = null;
        currentEngineeringDetails = [];
        currentClass10DocumentId = null;
        currentClass12DocumentId = null;
        currentEngineeringDocumentIds = [];
        academicExtractionErrors = [];
        originalMarksheetValues = {};

        try {
            // 1. Create processing session
            setStatus("Creating session...");
            const sessionId = await createSession();

            // 2. Upload PDF
            setStatus("Uploading PDF...");
            const upload = await uploadPDF(sessionId, file);

            if (!upload.document_id) {
                throw new Error("Upload completed without a document ID.");
            }

            // 3. Automatically classify and process all documents
            setStatus("AI is classifying and extracting your documents...");

            const processing = await autoProcessDocument(
                upload.document_id
            );

            // 4. Find processed documents
            const documents = processing.documents || [];

            const aadhaarDoc = documents.find(doc =>
                doc.document_type === "identity_document" &&
                doc.document_subtype === "aadhaar" &&
                doc.status === "processed"
            );

            const academicDocs = documents.filter(doc =>
                ["marksheet", "transcript"].includes(doc.document_type) &&
                doc.status === "processed"
            );

            if (!aadhaarDoc) {
                throw new Error(
                    "Aadhaar was not successfully processed. Please check your uploaded documents."
                );
            }

            currentExtractedDocumentId =
                aadhaarDoc.extracted_document_id;

            currentProfileId = processing.profile_id;

            // 5. Retrieve Aadhaar review details
            setStatus("Loading extracted identity information...");

            const aadhaar = await getDocumentReview(
                currentExtractedDocumentId
            );

            if (!aadhaar.fields) {
                throw new Error("No extracted identity fields were returned.");
            }

            // Convert the backend review format into the format
            // expected by the existing renderFields() function.
            const identityDetails = {};

            for (const [name, field] of Object.entries(aadhaar.fields)) {
                identityDetails[name] = field.value;
            }

            identityDetails.address_components = {
                house_number: identityDetails.address_house_number,
                street: identityDetails.address_street,
                locality: identityDetails.address_locality,
                city: identityDetails.address_city,
                district: identityDetails.address_district,
                state: identityDetails.address_state,
                pincode: identityDetails.address_pincode
            };

            // 6. Retrieve marksheet details
            for (let i = 0; i < academicDocs.length; i++) {
                const doc = academicDocs[i];
                const subtype = doc.document_subtype || "academic document";

                try {
                    setStatus(
                        `Loading ${subtype.replaceAll("_", " ")} (${i + 1}/${academicDocs.length})...`
                    );

                    const details = await extractAndGetMarksheet(
                        doc.extracted_document_id
                    );

                    if (subtype === "class_10") {
                        currentClass10Details = details;
                        currentClass10DocumentId = doc.extracted_document_id;

                    } else if (subtype === "class_12") {
                        currentClass12Details = details;
                        currentClass12DocumentId = doc.extracted_document_id;

                    } else if (
                        [
                            "engineering_semester",
                            "engineering_consolidated",
                            "undergraduate",
                            "academic_transcript"
                        ].includes(subtype) ||
                        doc.document_type === "transcript"
                    ) {
                        currentEngineeringDetails.push(details);
                        currentEngineeringDocumentIds.push(
                            doc.extracted_document_id
                        );
                    }

                } catch (error) {
                    console.error(
                        `Could not load ${subtype}:`,
                        error
                    );

                    academicExtractionErrors.push(
                        `${subtype}: ${error.message}`
                    );
                }
            }

            // 7. Display extracted identity information
            renderFields(identityDetails);

            if (reviewStatus) {
                reviewStatus.textContent = "Needs review";
            }

            if (reviewSection) {
                reviewSection.hidden = false;
            }

            if (proceedButton) {
                proceedButton.hidden = false;
            }

            // 8. Show processing summary
            const processedCount = processing.processed ?? 0;
            const failedCount = processing.failed ?? 0;

            setStatus(
                `Processing complete: ${processedCount} documents processed, ${failedCount} failed. Please review your extracted information.`
            );

        } catch (error) {
            console.error("Processing error:", error);
            setStatus(error.message);

        } finally {
            uploadButton.disabled = false;
        }
    });
}


// ==========================================
// PROCEED — SAVE PROFILE
// ==========================================

if (proceedButton) {

    proceedButton.addEventListener("click", async () => {

        if (!currentExtractedDocumentId) {
            return setStatus(
                "Please process a PDF first."
            );
        }

        try {

            proceedButton.disabled = true;

            setStatus("Saving your profile...");

            const saved = await saveProfile(
                currentExtractedDocumentId
            );

            currentProfileId = saved.profile_id;

            if (!currentProfileId) {
                throw new Error(
                    "Profile saved without a profile ID."
                );
            }

            if (reviewSection) reviewSection.hidden = true;
            if (formSection) formSection.hidden = false;

            setStatus(
                "Profile saved. Click Fill Form to populate all available pages."
            );

            showPage(1);

        } catch (error) {

            console.error("Profile save failed:", error);
            setStatus(error.message);

        } finally {

            proceedButton.disabled = false;
        }
    });
}


// ==========================================
// MANUAL EDIT TRACKING
// ==========================================

function attachManualEditTracking(input) {

    if (
        input.dataset.editTrackingAttached === "true"
    ) {
        return;
    }

    const track = () => {

        const previous =
            input.dataset.autofilledValue;

        if (
            previous !== undefined &&
            input.value !== previous
        ) {
            input.dataset.manuallyEdited = "true";
        }
    };

    input.addEventListener("input", track);
    input.addEventListener("change", track);

    input.dataset.editTrackingAttached = "true";
}


function fillFieldsPreservingManualEdits(mapping) {

    let filledCount = 0;
    let preservedCount = 0;
    let skippedCount = 0;

    for (const [id, value] of Object.entries(mapping)) {

        const input = document.getElementById(id);

        if (!input) continue;

        attachManualEditTracking(input);

        if (
            value === null ||
            value === undefined ||
            String(value).trim() === ""
        ) {
            skippedCount++;
            continue;
        }

        const newValue = String(value);
        // Store original extracted marksheet values.
        if (
            id.startsWith("sslc") ||
            id.startsWith("puc")
        ) {
            originalMarksheetValues[id] = newValue;
        }


        // NEVER OVERWRITE MANUAL EDITS

        if (
            input.dataset.manuallyEdited === "true"
        ) {
            preservedCount++;
            continue;
        }


        // PRESERVE VALUES ENTERED BEFORE AUTOFILL

        if (
            input.value.trim() !== "" &&
            input.dataset.autofilledValue === undefined
        ) {
            input.dataset.manuallyEdited = "true";
            preservedCount++;
            continue;
        }


        // FILL OR REFRESH FIELD

        input.value = newValue;

        input.dataset.autofilledValue = newValue;

        input.dispatchEvent(
            new Event("input", { bubbles: true })
        );

        input.dispatchEvent(
            new Event("change", { bubbles: true })
        );

        filledCount++;
    }

    return {
        filledCount,
        preservedCount,
        skippedCount
    };
}

function detectMarksheetChanges() {

    const changes = {};

    for (const [id, originalValue] of Object.entries(originalMarksheetValues)) {

        const input = document.getElementById(id);

        if (!input) continue;

        const currentValue = input.value.trim();

        if (currentValue !== originalValue) {
            changes[id] = {
                original: originalValue,
                updated: currentValue
            };
        }
    }

    return changes;
}

function updateSaveButtonVisibility() {

    const changes = detectMarksheetChanges();

    if (saveChangesButton) {
        saveChangesButton.hidden =
            Object.keys(changes).length === 0;
    }
}

function attachMarksheetChangeListeners() {

    const marksheetFieldIds = Object.keys(originalMarksheetValues);

    marksheetFieldIds.forEach(id => {

        const input = document.getElementById(id);

        if (!input || input.dataset.saveTrackingAttached === "true") {
            return;
        }

        input.addEventListener("input", updateSaveButtonVisibility);
        input.addEventListener("change", updateSaveButtonVisibility);

        input.dataset.saveTrackingAttached = "true";
    });
}

function getSubjectCorrectionLocation(fieldId) {

    const class10Fields = {
        sslcEnglish: ["english"],
        sslcLanguage: [
            "kannada", "hindi", "sanskrit",
            "tamil", "telugu", "urdu",
            "malayalam", "language"
        ],
        sslcMaths: ["mathematics", "math"],
        sslcScience: ["science"],
        sslcSocial: [
            "social science", "social studies", "social"
        ]
    };

    const class12Fields = {
        pucEnglish: ["english"],
        pucLanguage: [
            "kannada", "hindi", "sanskrit",
            "tamil", "telugu", "urdu",
            "malayalam", "language"
        ]
    };

    let details;
    let documentId;
    let keywords;

    if (class10Fields[fieldId]) {
        details = currentClass10Details;
        documentId = currentClass10DocumentId;
        keywords = class10Fields[fieldId];

    } else if (class12Fields[fieldId]) {
        details = currentClass12Details;
        documentId = currentClass12DocumentId;
        keywords = class12Fields[fieldId];

    } else if (/^pucSubject[1-4]$/.test(fieldId)) {
        details = currentClass12Details;
        documentId = currentClass12DocumentId;

        const subjectIndex = Number(fieldId.slice(-1)) - 1;

        return {
            documentId,
            semesterIndex: 0,
            subjectIndex
        };
    } else {
        return null;
    }

    const semesters = getSemesters(details);

    for (let semesterIndex = 0; semesterIndex < semesters.length; semesterIndex++) {

        const subjects = semesters[semesterIndex].subjects || [];

        const subjectIndex = subjects.findIndex(subject => {
            const name = asText(subject.subject_name).toLowerCase();
            const code = asText(subject.subject_code).toLowerCase();

            return keywords.some(keyword =>
                name.includes(keyword) || code.includes(keyword)
            );
        });

        if (subjectIndex !== -1) {
            return {
                documentId,
                semesterIndex,
                subjectIndex
            };
        }
    }

    return null;
}
// ==========================================
// SAVE MARKSHEET CORRECTIONS
// ==========================================

if (saveChangesButton) {

    saveChangesButton.addEventListener("click", async () => {

        const changes = detectMarksheetChanges();
        const correctionsByDocument = {};

        try {

            saveChangesButton.disabled = true;
            setStatus("Saving marksheet corrections...");

            for (const [fieldId, change] of Object.entries(changes)) {

                const location = getSubjectCorrectionLocation(fieldId);

                // Ignore fields that are not subject marks.
                if (!location) continue;

                if (!location.documentId) {
                    throw new Error("Could not identify the marksheet document.");
                }

                if (change.updated === "") {
                    throw new Error("Subject marks cannot be empty.");
                }

                const marks = Number(change.updated);

                if (!Number.isFinite(marks) || marks < 0) {
                    throw new Error(`Invalid marks entered for ${fieldId}.`);
                }

                if (!correctionsByDocument[location.documentId]) {
                    correctionsByDocument[location.documentId] = [];
                }

                correctionsByDocument[location.documentId].push({
                    semester_index: location.semesterIndex,
                    subject_index: location.subjectIndex,
                    marks_obtained: marks
                });
            }

            const documentIds = Object.keys(correctionsByDocument);

            if (documentIds.length === 0) {
                throw new Error("No subject mark corrections were found.");
            }

            for (const documentId of documentIds) {

                await apiRequest(
                    `${API_BASE_URL}/documents/extracted/${encodeURIComponent(documentId)}/update-marksheet`,
                    {
                        method: "PUT",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            subject_corrections:
                                correctionsByDocument[documentId]
                        })
                    }
                );
            }

            // Update original values after successful saving.
            for (const documentId of documentIds) {
                for (const [fieldId, change] of Object.entries(changes)) {
                    const location = getSubjectCorrectionLocation(fieldId);

                    if (location?.documentId === documentId) {
                        originalMarksheetValues[fieldId] = change.updated;
                    }
                }
            }

            updateSaveButtonVisibility();

            setStatus("Marksheet corrections saved successfully!");

        } catch (error) {

            console.error("Marksheet correction failed:", error);
            setStatus("Could not save corrections: " + error.message);

        } finally {

            saveChangesButton.disabled = false;
        }
    });
}
// ==========================================
// RETRIEVE FULL AADHAAR FROM BACKEND
// ==========================================

async function getFullAadhaar(profileId) {

    const data = await apiRequest(
        `${API_BASE_URL}/documents/profiles/${encodeURIComponent(profileId)}/aadhaar`
    );

    if (!data.aadhaar_number) {
        throw new Error(
            "The backend did not return an Aadhaar number."
        );
    }

    return data.aadhaar_number;
}


// ==========================================
// FILL ALL AVAILABLE FORM PAGES
// ==========================================

if (fillFormButton) {

    fillFormButton.addEventListener("click", async () => {

        if (!currentProfileId) {
            return setStatus(
                "No saved profile. Please upload and process your PDF first."
            );
        }

        try {

            fillFormButton.disabled = true;

            setStatus("Retrieving saved profile...");

            // 1. GET SAVED PROFILE

            const saved = await getSavedProfile(
                currentProfileId
            );

            const profile = saved.profile_data || {};

            const parents = getParentDetails();


            // 2. GET FULL AADHAAR FROM LOCAL BACKEND

            let aadhaarNumber = "";

            try {

                setStatus("Retrieving Aadhaar securely...");

                aadhaarNumber = await getFullAadhaar(
                    currentProfileId
                );

            } catch (error) {

                console.error(
                    "Aadhaar retrieval failed:",
                    error.message
                );

                setStatus(
                    "Could not retrieve full Aadhaar. Filling other available fields..."
                );
            }


            // 3. BUILD FORM MAPPING

            const mapping = {

                // PAGE 1 — PERSONAL INFORMATION

                formName: profile.full_name,

                formDOB: profile.date_of_birth,

                formGender: profile.gender,

                formAadhaar: aadhaarNumber,

                formAddress: profile.address,

                // Father name: Aadhaar first, marksheet fallback.

                formFather: firstAvailable(
                    profile.father_or_husband_name,
                    parents.father_name
                ),

                // Mother name comes from academic documents.

                formMother: parents.mother_name,

                // Fill only when actually available.

                formMobile: firstAvailable(
                    profile.mobile_number,
                    currentClass10Details?.student?.mobile_number,
                    currentClass12Details?.student?.mobile_number
                ),

                formEmail: firstAvailable(
                    profile.email,
                    currentClass10Details?.student?.email,
                    currentClass12Details?.student?.email
                ),


                // PAGE 2 — CLASS 10

                ...(currentClass10Details
                    ? getClass10Mapping(currentClass10Details)
                    : {}),


                // PAGE 3 — CLASS 12

                ...(currentClass12Details
                    ? getClass12Mapping(currentClass12Details)
                    : {}),


                // PAGE 4 — ENGINEERING

                ...(currentEngineeringDetails.length
                    ? getEngineeringMapping(
                        currentEngineeringDetails
                    )
                    : {})
            };


            // 4. FILL FORM WHILE PRESERVING MANUAL EDITS

            const result =
                fillFieldsPreservingManualEdits(mapping);
            attachMarksheetChangeListeners();
            updateSaveButtonVisibility();

            setStatus(
                `${result.filledCount} fields filled/refreshed. ` +
                `${result.preservedCount} manually edited fields preserved. ` +
                `${result.skippedCount} unavailable fields skipped.`
            );

            // Do not log mapping: it contains full Aadhaar.

            console.log("Autofill completed:", {
                filledCount: result.filledCount,
                preservedCount: result.preservedCount,
                skippedCount: result.skippedCount,
                aadhaarFilled: Boolean(aadhaarNumber)
            });

        } catch (error) {

            console.error("Form filling failed:", error);
            setStatus(error.message);

        } finally {

            fillFormButton.disabled = false;
        }
    });
}


// ==========================================
// MULTI-PAGE NAVIGATION
// ==========================================

const formPages =
    document.querySelectorAll(".form-page");

const previousPageButton =
    document.getElementById("previousPageButton");

const nextPageButton =
    document.getElementById("nextPageButton");

const finalSubmitButton =
    document.getElementById("finalSubmitButton");

const pageTitle =
    document.getElementById("pageTitle");

const pageCounter =
    document.getElementById("pageCounter");

const progressBar =
    document.getElementById("progressBar");


const pageTitles = [
    "Personal Information",
    "Class 10 (SSLC) Information",
    "Class 12 (PUC) Information",
    "Engineering Information",
    "Review & Submit"
];

let currentPage = 1;

const totalPages = formPages.length;


function showPage(number) {

    if (!formPages.length) return;

    currentPage = Math.max(
        1,
        Math.min(number, totalPages)
    );

    formPages.forEach(page => {

        const pageNumber =
            Number(page.dataset.page);

        page.hidden =
            pageNumber !== currentPage;

        page.classList.toggle(
            "active",
            pageNumber === currentPage
        );
    });


    if (pageTitle) {
        pageTitle.textContent =
            pageTitles[currentPage - 1] ||
            `Page ${currentPage}`;
    }

    if (pageCounter) {
        pageCounter.textContent =
            `Page ${currentPage} of ${totalPages}`;
    }

    if (progressBar) {
        progressBar.style.width =
            `${currentPage / totalPages * 100}%`;
    }

    if (previousPageButton) {
        previousPageButton.disabled =
            currentPage === 1;
    }

    if (nextPageButton) {
        nextPageButton.hidden =
            currentPage === totalPages;
    }

    if (finalSubmitButton) {
        finalSubmitButton.hidden =
            currentPage !== totalPages;
    }

    if (currentPage === totalPages) {
        generateFinalReview();
    }

    formSection?.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


if (nextPageButton) {

    nextPageButton.addEventListener("click", () => {

        if (currentPage < totalPages) {
            showPage(currentPage + 1);
        }
    });
}


if (previousPageButton) {

    previousPageButton.addEventListener("click", () => {

        if (currentPage > 1) {
            showPage(currentPage - 1);
        }
    });
}


// ==========================================
// FINAL REVIEW
// ==========================================

function generateFinalReview() {

    const container =
        document.getElementById("finalReview");

    if (!container) return;

    container.replaceChildren();

    const groups = [

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


    groups.forEach(group => {

        const section =
            document.createElement("section");

        section.className = "review-group";

        const heading =
            document.createElement("h4");

        heading.textContent = group.title;

        section.appendChild(heading);


        group.ids.forEach(id => {

            const input =
                document.getElementById(id);

            if (
                !input ||
                !String(input.value).trim()
            ) {
                return;
            }

            const row =
                document.createElement("p");

            const label =
                document.querySelector(
                    `label[for="${id}"]`
                );

            // Avoid displaying the full Aadhaar in review text.
            const displayValue = id === "formAadhaar"
                ? `XXXX XXXX ${input.value.slice(-4)}`
                : input.value;

            row.textContent =
                `${label?.textContent || id}: ${displayValue}`;

            section.appendChild(row);
        });

        container.appendChild(section);
    });
}


// ==========================================
// FINAL SUBMISSION — DEMO ONLY
// ==========================================

if (finalSubmitButton) {

    finalSubmitButton.addEventListener("click", () => {

        const confirmation =
            document.getElementById("confirmInformation");

        if (
            confirmation &&
            !confirmation.checked
        ) {
            return setStatus(
                "Please confirm that your information is correct."
            );
        }

        const formData = {};

        document.querySelectorAll(
            "#formSection input, " +
            "#formSection select, " +
            "#formSection textarea"
        ).forEach(input => {

            if (input.id) {

                formData[input.id] =
                    input.type === "checkbox"
                        ? input.checked
                        : input.value;
            }
        });

        // Do not log formData because it contains Aadhaar.

        setStatus(
            "Form review completed. Actual backend submission is not connected yet."
        );
    });
}


// ==========================================
// INITIALIZE FORM
// ==========================================

if (formPages.length) {
    showPage(1);
}


// ==========================================
// GOOGLE AUTHENTICATION
// ==========================================

const authSection = document.getElementById("authSection");
const loginContainer = document.getElementById("loginContainer");
const userContainer = document.getElementById("userContainer");

const googleLoginButton = document.getElementById("googleLoginButton");
const logoutButton = document.getElementById("logoutButton");

const userPicture = document.getElementById("userPicture");
const userName = document.getElementById("userName");
const userEmail = document.getElementById("userEmail");

const homeSection = document.getElementById("homeSection");

async function checkAuthentication() {
    try {
        const user = await apiRequest(
            `${API_BASE_URL}/auth/me`
        );

        loginContainer.hidden = true;
        userContainer.hidden = false;

        if (homeSection) homeSection.hidden = false;
        if (authSection) authSection.hidden = false;

        userName.textContent = user.full_name || "User";
        userEmail.textContent = user.email || "";

        if (user.picture_url) {
            userPicture.src = user.picture_url;
            userPicture.hidden = false;
        } else {
            userPicture.hidden = true;
        }

    } catch (error) {
        loginContainer.hidden = false;
        userContainer.hidden = true;

        if (homeSection) homeSection.hidden = true;
        if (reviewSection) reviewSection.hidden = true;
        if (formSection) formSection.hidden = true;
    }
}

// Google Login
if (googleLoginButton) {
    googleLoginButton.addEventListener("click", () => {
        window.location.href =
            `${API_BASE_URL}/auth/google/login`;
    });
}

// Logout
if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
        try {
            await apiRequest(
                `${API_BASE_URL}/auth/logout`,
                { method: "POST" }
            );

            currentProfileId = null;
            currentExtractedDocumentId = null;

            if (homeSection) homeSection.hidden = true;
            if (reviewSection) reviewSection.hidden = true;
            if (formSection) formSection.hidden = true;

            loginContainer.hidden = false;
            userContainer.hidden = true;

            setStatus("You have been logged out.");

        } catch (error) {
            setStatus("Logout failed: " + error.message);
        }
    });
}

// Check login status when the application opens
checkAuthentication();
