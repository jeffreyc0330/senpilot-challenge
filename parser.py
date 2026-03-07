import re


# Map of lowercase keywords -> canonical document type names
DOC_TYPE_MAP = {
    "exhibits": "Exhibits",
    "key documents": "Key Documents",
    "key docs": "Key Documents",
    "other documents": "Other Documents",
    "other docs": "Other Documents",
    "transcripts": "Transcripts",
    "recordings": "Recordings",
}


def parse_request(text: str) -> dict:
    """
    Parse an email body and extract matter_number and doc_type.

    Returns:
        dict with keys 'matter_number' (str) and 'doc_type' (str)

    Raises:
        ValueError: if matter number or document type cannot be found
    """
    # Extract matter number (e.g. M12205)
    matter_match = re.search(r'M\d{5}', text)
    if not matter_match:
        raise ValueError(
            "Could not find a matter number in your email. "
            "Please include a matter number like 'M12205'."
        )
    matter_number = matter_match.group(0)

    # Try to find a doc type by checking longest matches first (to catch "key documents" before "documents")
    lower_text = text.lower()
    doc_type = None

    # Sort by descending length so multi-word phrases are matched first
    for keyword in sorted(DOC_TYPE_MAP.keys(), key=len, reverse=True):
        if keyword in lower_text:
            doc_type = DOC_TYPE_MAP[keyword]
            break

    if doc_type is None:
        raise ValueError(
            "Could not determine the document type from your email. "
            "Please specify one of: Exhibits, Key Documents, Other Documents, Transcripts, or Recordings."
        )

    print(f"[parser] Parsed request: matter_number={matter_number}, doc_type={doc_type}")
    return {"matter_number": matter_number, "doc_type": doc_type}
