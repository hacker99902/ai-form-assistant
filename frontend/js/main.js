
const pdfInput = document.getElementById("pdfInput");
const uploadButton = document.getElementById("uploadButton");
const statusText = document.getElementById("status");
const results = document.getElementById("results");
const resultData = document.getElementById("resultData");

uploadButton.addEventListener("click", async () => {
    const file = pdfInput.files[0];

    if (!file) {
        statusText.textContent = "Please select a PDF first.";
        return;
    }

    if (file.size > 20 * 1024 * 1024) {
        statusText.textContent = "PDF must be smaller than 20 MB.";
        return;
    }

    uploadButton.disabled = true;
    statusText.textContent = "Processing PDF...";

    try {
        const sessionId = await createSession();
        const data = await uploadPDF(sessionId, file);

        statusText.textContent = "PDF processed successfully!";
        results.hidden = false;

        resultData.textContent = JSON.stringify(
            data,
            null,
            2
        );

    } catch (error) {
        statusText.textContent = error.message;
    } finally {
        uploadButton.disabled = false;
    }
});
