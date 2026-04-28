import os
from dataclasses import dataclass

from quiz_answering import QuizAnsweringService


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str = ""
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL
    source: str = "missing"

    @property
    def configured(self):
        return bool(self.api_key)


@dataclass(frozen=True)
class DeepSeekValidationResult:
    ok: bool
    message: str = ""


def _first_text(*values, default=""):
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def load_deepseek_config(account_config=None, env=None):
    account_config = account_config or {}
    env = os.environ if env is None else env

    account_key = _first_text(account_config.get("deepseek_api_key"))
    env_deepseek_key = _first_text(env.get("DEEPSEEK_API_KEY"))
    env_compatible_key = _first_text(env.get("ANTHROPIC_AUTH_TOKEN"))

    api_key = _first_text(account_key, env_deepseek_key, env_compatible_key)
    if account_key:
        source = "account"
    elif env_deepseek_key:
        source = "DEEPSEEK_API_KEY"
    elif env_compatible_key:
        source = "ANTHROPIC_AUTH_TOKEN"
    else:
        source = "missing"

    base_url = _first_text(
        account_config.get("api_base_url"),
        account_config.get("deepseek_base_url"),
        env.get("DEEPSEEK_BASE_URL"),
        env.get("ANTHROPIC_BASE_URL"),
        default=DEFAULT_DEEPSEEK_BASE_URL,
    )
    model = _first_text(
        account_config.get("api_model"),
        account_config.get("deepseek_model"),
        env.get("DEEPSEEK_MODEL"),
        env.get("ANTHROPIC_MODEL"),
        default=DEFAULT_DEEPSEEK_MODEL,
    )

    return DeepSeekConfig(api_key=api_key, base_url=base_url, model=model, source=source)


def create_openai_client(config):
    from openai import OpenAI

    if not config.configured:
        return None
    return OpenAI(api_key=config.api_key, base_url=config.base_url)


def create_deepseek_components(account_config=None, logger=None, env=None):
    config = load_deepseek_config(account_config=account_config, env=env)
    if not config.configured:
        return None, None, config

    client = create_openai_client(config)
    service = QuizAnsweringService(client, config.model, logger=logger)
    return client, service, config


def verify_deepseek_client(client, config, logger=None):
    if client is None or not config.configured:
        return DeepSeekValidationResult(False, "DeepSeek API key is not configured")

    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": "Return only the requested letter."},
                {"role": "user", "content": "Return only A."},
            ],
            temperature=0,
            max_tokens=4,
            stream=False,
        )
        content = response.choices[0].message.content.strip()
        if not content:
            return DeepSeekValidationResult(False, "DeepSeek validation response is empty")
        if logger:
            logger.info(f"✅ DeepSeek API校验成功: model={config.model}, source={config.source}")
        return DeepSeekValidationResult(True, content)
    except Exception as e:
        if logger:
            logger.error(f"❌ DeepSeek API校验失败: {e}")
        return DeepSeekValidationResult(False, str(e))


def create_answering_service(account_config=None, logger=None, env=None):
    _, service, config = create_deepseek_components(
        account_config=account_config,
        logger=logger,
        env=env,
    )
    return service, config


__all__ = [
    "DeepSeekConfig",
    "DeepSeekValidationResult",
    "create_answering_service",
    "create_deepseek_components",
    "create_openai_client",
    "load_deepseek_config",
    "verify_deepseek_client",
]
