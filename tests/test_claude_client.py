from pydantic import BaseModel
from planning.claude_client import ClaudeClient

class MathAnswer(BaseModel):
    answer: str
    confidence: float

def test_claude_client_structured_output():
    client = ClaudeClient()
    prompt = "What is 2+2? Provide your answer and confidence."
    
    result, metadata = client.call_with_structured_output(
        prompt=prompt,
        output_model=MathAnswer
    )
    
    assert isinstance(result, MathAnswer)
    assert "4" in result.answer
    assert 0.0 <= result.confidence <= 1.0
    
    assert "input_tokens" in metadata
    assert "output_tokens" in metadata
    assert "model" in metadata
    assert "latency" in metadata
    
    cost_info = client.get_cost_summary()
    print(f"\n[Test Output] Result: answer='{result.answer}', confidence={result.confidence}")
    print(f"[Test Output] Metadata: {metadata}")
    print(f"[Test Output] Cost Summary: {cost_info}")
