import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from deepseek_agent import load_deepseek_config  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
