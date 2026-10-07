"""Provider-neutral model specifications and OpenAI codec tests (offline)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fruitfly_agent.core.data_model import (
    AssistantMessage,
    TextBlock,
    ToolCallBlock,
    ToolResultMessage,
    UserMessage,
)
from fruitfly_agent.core.errors import FatalError, OverflowError, RetryableError
from fruitfly_agent.providers.anthropic import classify_error as classify_anthropic_error
from fruitfly_agent.providers.openai import OpenAIProvider, classify_error as classify_openai_error
from fruitfly_agent.providers.openai_codec import convert_to_openai
from fruitfly_agent.providers.registry import ProviderRegistry, default_registry, load_model_specs


class ProviderTests(unittest.TestCase):
    def test_public_model_template_loads_without_live_credentials(self) -> None:
        specs = load_model_specs(Path(__file__).resolve().parents[2] / "examples/configuration/models.example.yaml")
        self.assertEqual({"deepseek-flash-openai", "deepseek-flash-anthropic"}, set(specs))
        self.assertEqual("openai", specs["deepseek-flash-openai"].provider.type)
        self.assertEqual("anthropic", specs["deepseek-flash-anthropic"].provider.type)
        self.assertEqual("https://api.deepseek.com", specs["deepseek-flash-openai"].provider.base_url)
        self.assertEqual("https://api.deepseek.com/anthropic", specs["deepseek-flash-anthropic"].provider.base_url)
        self.assertEqual({"reasoning": {"effort": "none"}}, specs["deepseek-flash-openai"].parameters)
        self.assertEqual({}, specs["deepseek-flash-anthropic"].parameters)
        for spec in specs.values():
            with self.subTest(profile=spec.id):
                self.assertEqual("DEEPSEEK_API_KEY", spec.provider.api_key_env)
                self.assertEqual("deepseek-flash", spec.model)
                spec.require(tools=True, streaming=True)
                registry = ProviderRegistry()
                captured = []
                marker = object()
                def construct(model, key):
                    captured.append((model, key))
                    return marker
                registry.register(spec.provider.type, construct)
                self.assertIs(marker, registry.create(spec, {"DEEPSEEK_API_KEY": "offline-placeholder"}))
                self.assertEqual([(spec, "offline-placeholder")], captured)
        # Exercise the real factories and constructor parameters with SDK clients mocked.
        with patch("openai.AsyncOpenAI") as responses, patch("anthropic.AsyncAnthropic") as messages:
            registry = default_registry()
            for spec in specs.values():
                registry.create(spec, {"DEEPSEEK_API_KEY": "offline-placeholder"})
            self.assertEqual("https://api.deepseek.com", responses.call_args.kwargs["base_url"])
            self.assertEqual("https://api.deepseek.com/anthropic", messages.call_args.kwargs["base_url"])

    def test_compatible_endpoint_overflow_messages_are_normalized(self) -> None:
        messages = (
            "prompt_too_long",
            "The input token count (1196265) exceeds the maximum number allowed",
            "This model's maximum prompt length is 131072 but the request is larger",
            "Please reduce the length of the messages or completion",
            "the request exceeds the available context size, try increasing it",
            "invalid params, context window exceeds limit",
            "Range of input length should be [1, 131072]",
        )
        for classify in (classify_openai_error, classify_anthropic_error):
            for message in messages:
                with self.subTest(classifier=classify.__module__, message=message):
                    self.assertIsInstance(classify(Exception(message)), OverflowError)

    def test_structured_sdk_error_code_is_used_for_overflow(self) -> None:
        class SDKError(Exception):
            status_code = 400
            body = {
                "error": {
                    "code": "context_length_exceeded",
                    "message": "request rejected",
                }
            }

        self.assertIsInstance(classify_openai_error(SDKError("bad request")), OverflowError)

    def test_throttling_takes_precedence_over_broad_token_wording(self) -> None:
        error = Exception("ThrottlingException: too many tokens, rate limit exceeded")
        for classify in (classify_openai_error, classify_anthropic_error):
            with self.subTest(classifier=classify.__module__):
                self.assertIsInstance(classify(error, status_code=429), RetryableError)

    def test_unknown_400_is_guarded_for_both_providers(self) -> None:
        for classify in (classify_openai_error, classify_anthropic_error):
            with self.subTest(classifier=classify.__module__):
                error = classify(Exception("invalid request"), status_code=400)
                self.assertIsInstance(error, FatalError)
                self.assertEqual(True, error.details["unknown_400"])

    def test_payload_too_large_is_an_overflow_recovery_signal(self) -> None:
        for classify in (classify_openai_error, classify_anthropic_error):
            with self.subTest(classifier=classify.__module__):
                self.assertIsInstance(
                    classify(Exception("request rejected"), status_code=413),
                    OverflowError,
                )

    def test_openai_codec_preserves_function_call_pairing(self) -> None:
        items = convert_to_openai([
            UserMessage(content="go"),
            AssistantMessage(content=[ToolCallBlock("call-1", "read", {"path": "a"})]),
            ToolResultMessage("call-1", [TextBlock("contents")]),
        ])
        self.assertEqual("function_call", items[1]["type"])
        self.assertEqual("call-1", items[1]["call_id"])
        self.assertEqual("function_call_output", items[2]["type"])
        self.assertEqual("call-1", items[2]["call_id"])

    def test_openai_assembly_normalizes_usage_and_tools(self) -> None:
        class Usage:
            input_tokens = 10
            output_tokens = 4
            input_tokens_details = None

        class Response:
            usage = Usage()
            incomplete_details = None

        message = OpenAIProvider._assemble(
            Response(), ["hello"], {"item-1": {"id": "call-1", "name": "read", "arguments": '{"path":"a"}'}}
        )
        self.assertEqual("toolUse", message.stop_reason)
        self.assertEqual("hello", message.text)
        self.assertEqual("call-1", message.tool_calls[0].id)
        self.assertEqual(10, message.usage.input_tokens)

    def test_model_catalog_and_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.yaml"
            path.write_text(
                "models:\n  test:\n    provider: fake\n    model: exact-id\n"
                "    context_window: 1234\n    api_key_env: FAKE_KEY\n",
                encoding="utf-8",
            )
            spec = load_model_specs(path)["test"]
        registry = ProviderRegistry()
        marker = object()
        registry.register("fake", lambda model, key: marker)
        self.assertIs(marker, registry.create(spec, {"FAKE_KEY": "secret"}))
        self.assertEqual("exact-id", spec.model)
        self.assertEqual(1234, spec.context_window)

    def test_capability_requirements_fail_before_a_paid_run(self) -> None:
        from fruitfly_agent.providers.specs import ModelCapabilities, ModelSpec, ProviderSpec

        spec = ModelSpec(
            "text-only",
            ProviderSpec("fake", "FAKE_KEY"),
            "model",
            1000,
            capabilities=ModelCapabilities(tools=False),
        )
        with self.assertRaisesRegex(ValueError, "tools"):
            spec.require(tools=True)


if __name__ == "__main__":
    unittest.main()
