import os
import time
from typing import TypeVar, Type, Any
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
import anthropic

T = TypeVar("T", bound=BaseModel)

class ClaudeClient:
    def __init__(self, default_model: str = "claude-sonnet-4-6"):
        load_dotenv()
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set in .env")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.default_model = default_model
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _resolve_model(self, model: str | None) -> str:
        return model or self.default_model

    def call_with_structured_output(
        self,
        prompt: str,
        output_model: Type[T],
        model: str = None,
        max_tokens: int = 4096,
        system_prompt: str = None
    ) -> tuple[T, dict[str, Any]]:
        target_model = self._resolve_model(model)
        schema = output_model.model_json_schema()

        tool_def = {
            "name": "submit_response",
            "description": f"Submit structured response matching {output_model.__name__}",
            "input_schema": schema
        }

        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": target_model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": [tool_def],
            "tool_choice": {"type": "tool", "name": "submit_response"}
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        retries = 3
        delay = 1

        for attempt in range(retries):
            start_time = time.time()
            try:
                response = self.client.messages.create(**kwargs)
                latency = time.time() - start_time

                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                self.total_input_tokens += input_tokens
                self.total_output_tokens += output_tokens

                print(f"Claude call: model={target_model}, input={input_tokens} tokens, output={output_tokens} tokens, latency={latency:.2f}s")

                tool_use_block = None
                for block in response.content:
                    if block.type == "tool_use" and block.name == "submit_response":
                        tool_use_block = block
                        break

                if not tool_use_block:
                    raise ValueError("No submit_response tool call found in Claude response")

                parsed_instance = output_model.model_validate(tool_use_block.input)
                metadata = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "model": target_model,
                    "latency": latency
                }
                return parsed_instance, metadata

            except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError, ValidationError, ValueError) as e:
                latency = time.time() - start_time
                print(f"[Attempt {attempt+1}/{retries}] Error during Claude call ({type(e).__name__}): {e}")
                if attempt == retries - 1:
                    raise e
                time.sleep(delay)
                delay *= 2

    def call_text(self, prompt: str, model: str = None, max_tokens: int = 4096, system_prompt: str = None) -> str:
        target_model = self._resolve_model(model)
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": target_model, "max_tokens": max_tokens, "messages": messages}
        if system_prompt:
            kwargs["system"] = system_prompt
        
        response = self.client.messages.create(**kwargs)
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens
        
        text_blocks = [b.text for b in response.content if b.type == "text"]
        return "".join(text_blocks)

    def get_cost_summary(self) -> dict[str, Any]:
        input_cost = (self.total_input_tokens / 1_000_000) * 3.0
        output_cost = (self.total_output_tokens / 1_000_000) * 15.0
        total_cost = input_cost + output_cost
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(total_cost, 6)
        }
