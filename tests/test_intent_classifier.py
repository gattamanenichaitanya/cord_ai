import pytest
from dashboard.chat.intent_classifier import classify_intent, Intent, ClassifiedIntent
from planning.claude_client import ClaudeClient

def test_intent_classification():
    """
    Test suite for the intent classifier using a real ClaudeClient instance
    with simulated context data.
    """
    client = ClaudeClient()
    
    # 6 mock requirements
    available_requirements = [
        {"id": "REQ-001", "title": "ACS Risk Score Custom Field"},
        {"id": "REQ-002", "title": "ACS NPS Score Custom Field"},
        {"id": "REQ-003", "title": "ACS Customer Segment"},
        {"id": "REQ-004", "title": "At-Risk Customer Alert workflow"},
        {"id": "REQ-005", "title": "Slack Notification Integration"},
        {"id": "REQ-006", "title": "Daily KPI Dashboard Reports"},
    ]
    
    context = {
        "document_loaded": True,
        "available_requirements": available_requirements,
        "available_plans": ["REQ-001", "REQ-002"],
        "current_canvas_focus": "welcome"
    }
    
    # 6 test cases to verify
    test_cases = [
        {
            "message": "extract the requirements",
            "expected_intent": Intent.EXTRACT_REQUIREMENTS,
            "validate": lambda ci: True
        },
        {
            "message": "plan REQ-004",
            "expected_intent": Intent.PLAN_REQUIREMENT,
            "validate": lambda ci: ci.requirement_id == "REQ-004"
        },
        {
            "message": "plan the at-risk workflow",
            "expected_intent": Intent.PLAN_REQUIREMENT,
            "validate": lambda ci: ci.requirement_id == "REQ-004"
        },
        {
            "message": "show me the list",
            "expected_intent": Intent.SHOW_ARTIFACT,
            "validate": lambda ci: ci.artifact_target == "requirements"
        },
        {
            "message": "what's re-enrollment?",
            "expected_intent": Intent.EXPLAIN,
            "validate": lambda ci: "re-enrollment" in (ci.question or "").lower()
        },
        {
            "message": "asdfghjkl",
            "expected_intent": Intent.UNKNOWN,
            "validate": lambda ci: True
        }
    ]
    
    print("\n" + "="*80)
    print("RUNNING INTENT CLASSIFIER TEST SUITE (REAL CLAUDE CALLS)")
    print("="*80)
    
    failures = []
    
    for case in test_cases:
        msg = case["message"]
        print(f"\nUser Message: '{msg}'")
        
        # Run classification
        result = classify_intent(msg, context, client)
        
        print(f"   Intent: {result.intent.value}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Acknowledgment: '{result.acknowledgment}'")
        if result.requirement_id:
            print(f"   Requirement ID: {result.requirement_id}")
        if result.requirement_reference:
            print(f"   Requirement Ref: {result.requirement_reference}")
        if result.artifact_target:
            print(f"   Artifact Target: {result.artifact_target}")
        if result.question:
            print(f"   Question: '{result.question}'")
            
        # Validations
        try:
            assert result.intent == case["expected_intent"], f"Expected {case['expected_intent']}, got {result.intent}"
            assert case["validate"](result), f"Extra validation check failed for: {result}"
            print("   [PASS] Match Successful!")
        except AssertionError as e:
            print(f"   [FAIL] AssertionError: {e}")
            failures.append((msg, e))
            
    print("\n" + "="*80)
    print(f"TEST SUITE COMPLETE: {len(test_cases) - len(failures)}/{len(test_cases)} Passed.")
    print("="*80)
    
    if failures:
        pytest.fail(f"Intent classifier test failures occurred: {failures}")
