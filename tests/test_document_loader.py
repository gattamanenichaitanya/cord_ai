import pytest
from planning.document_loader import load_document, detect_sections

def test_load_acme_document():
    doc_path = "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    doc_input = load_document(doc_path)
    
    assert doc_input.file_type == "docx"
    assert doc_input.title != ""
    assert doc_input.section_count > 5
    
    content = doc_input.content_markdown
    assert "Workflow 6.1" in content or "At-Risk Customer Alert" in content or "At-Risk" in content
    
    print("\n" + "="*50)
    print(f"Loaded Document Title: {doc_input.title}")
    print(f"Section Count: {doc_input.section_count}")
    print("="*50)
    print("FIRST 500 CHARACTERS OF CONTENT_MARKDOWN:")
    print("="*50)
    print(content[:500])
    print("="*50 + "\n")
