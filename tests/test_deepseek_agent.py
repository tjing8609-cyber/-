import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from deepseek_agent import (  # noqa: E402
    DEEPSEEK_VALIDATION_QUESTION,
    create_deepseek_components,
    is_expected_validation_answer,
    load_deepseek_config,
    verify_deepseek_client,
)


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content="0.5", error=None):
        self.content = content
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return FakeResponse(self.content)


class FakeClient:
    def __init__(self, content="0.5", error=None):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(content=content, error=error)


class DeepSeekAgentTests(unittest.TestCase):
    def test_account_config_takes_priority(self):
        config = load_deepseek_config(
            {
                "deepseek_api_key": "account-key",
                "api_base_url": "https://example.test",
                "api_model": "custom-model",
            },
            env={"DEEPSEEK_API_KEY": "env-key"},
        )

        self.assertTrue(config.configured)
        self.assertEqual(config.api_key, "account-key")
        self.assertEqual(config.base_url, "https://example.test")
        self.assertEqual(config.model, "custom-model")
        self.assertEqual(config.source, "account")

    def test_env_config_fallback(self):
        config = load_deepseek_config(
            {},
            env={
                "DEEPSEEK_API_KEY": "env-key",
                "DEEPSEEK_BASE_URL": "https://env.test",
                "DEEPSEEK_MODEL": "deepseek-reasoner",
            },
        )

        self.assertEqual(config.api_key, "env-key")
        self.assertEqual(config.base_url, "https://env.test")
        self.assertEqual(config.model, "deepseek-reasoner")
        self.assertEqual(config.source, "DEEPSEEK_API_KEY")

    def test_missing_key_is_not_configured(self):
        self.assertFalse(load_deepseek_config({}, env={}).configured)

    def test_components_are_empty_without_key(self):
        client, service, config = create_deepseek_components({}, env={})

        self.assertIsNone(client)
        self.assertIsNone(service)
        self.assertFalse(config.configured)

    def test_verify_deepseek_client_success(self):
        config = load_deepseek_config({"deepseek_api_key": "key"}, env={})
        client = FakeClient("sin30° = 1/2")

        result = verify_deepseek_client(client, config)

        self.assertTrue(result.ok)
        call = client.chat.completions.calls[0]
        self.assertEqual(call["model"], "deepseek-chat")
        self.assertEqual(call["messages"][1]["content"], DEEPSEEK_VALIDATION_QUESTION)

    def test_verify_deepseek_client_rejects_unexpected_answer(self):
        config = load_deepseek_config({"deepseek_api_key": "key"}, env={})
        result = verify_deepseek_client(FakeClient("42"), config)

        self.assertFalse(result.ok)
        self.assertIn("unexpected", result.message)

    def test_verify_deepseek_client_failure(self):
        config = load_deepseek_config({"deepseek_api_key": "key"}, env={})
        result = verify_deepseek_client(FakeClient(error=RuntimeError("401 auth failed")), config)

        self.assertFalse(result.ok)
        self.assertIn("401", result.message)

    def test_validation_answer_accepts_common_sin30_forms(self):
        self.assertTrue(is_expected_validation_answer("0.5"))
        self.assertTrue(is_expected_validation_answer("1/2"))
        self.assertTrue(is_expected_validation_answer("二分之一"))
        self.assertTrue(is_expected_validation_answer("一半"))
        self.assertTrue(is_expected_validation_answer(".5"))
        self.assertFalse(is_expected_validation_answer("30"))
        self.assertFalse(is_expected_validation_answer("10.5"))


if __name__ == "__main__":
    unittest.main()
