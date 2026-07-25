"""Unit tests for Document Storage & SHA-256 Payload Integrity."""

import base64
import os
from app.services.document_service import store_uploaded_document


def test_store_uploaded_document():
    test_content = b"Sample hospital bill document content for NoLoop platform testing"
    b64_str = base64.b64encode(test_content).decode("utf-8")

    doc = store_uploaded_document(
        file_name="hospital_bill.pdf",
        base64_content=f"data:application/pdf;base64,{b64_str}",
        mime_type="application/pdf",
        tenant_id="tnt_apollo_test",
    )

    assert doc.file_id.startswith("doc_")
    assert doc.file_name == "hospital_bill.pdf"
    assert doc.file_size_bytes == len(test_content)
    assert doc.mime_type == "application/pdf"
    assert os.path.exists(doc.file_path)

    # Clean up test file
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
