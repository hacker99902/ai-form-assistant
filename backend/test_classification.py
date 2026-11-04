from app.services.classification_service import classify_documents


pages = [
    {
        "page_number": 1,
        "text": """
        Design a Learning System
        Tom Mitchell
        A learning system improves its performance
        based on experience.
        """
    },
    {
        "page_number": 2,
        "text": """
        The learning problem
        A computer program learns from experience E
        with respect to task T and performance measure P.
        """
    },
    {
        "page_number": 3,
        "text": """
        Final Design
        Checkers Learning Program
        Training experience and target function.
        """
    }
]


try:
    result = classify_documents(pages)

    print("\nClassification successful!\n")

    for document in result.documents:
        print("Document type:", document.document_type)
        print("Start page:", document.start_page)
        print("End page:", document.end_page)
        print("Confidence:", document.confidence)
        print("Evidence:", document.evidence)
        print("-" * 40)

except Exception as error:
    print("Classification failed:", error)  