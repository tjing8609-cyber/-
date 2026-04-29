"""Small helpers for inspecting OpenAI-compatible chat responses."""

import json


def safe_get(value, name, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def first_choice(response):
    choices = safe_get(response, "choices", []) or []
    if not choices:
        return None
    return choices[0]


def content_to_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            text = safe_get(item, "text")
            if text is None:
                text = safe_get(item, "content")
            if text:
                parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def extract_chat_message_text(response):
    choice = first_choice(response)
    if choice is None:
        return ""
    message = safe_get(choice, "message", {}) or {}
    return content_to_text(safe_get(message, "content", "")).strip()


def response_to_plain_data(response):
    if response is None:
        return None
    if isinstance(response, dict):
        return response
    for method_name in ("model_dump", "dict", "to_dict_recursive", "to_dict"):
        method = getattr(response, method_name, None)
        if callable(method):
            try:
                return method()
            except TypeError:
                try:
                    return method(exclude_none=True)
                except Exception:
                    pass
            except Exception:
                pass
    return repr(response)


def summarize_chat_response(response, max_chars=1200):
    choice = first_choice(response)
    message = safe_get(choice, "message", {}) if choice is not None else {}
    content = content_to_text(safe_get(message, "content", ""))
    reasoning = content_to_text(safe_get(message, "reasoning_content", ""))
    refusal = content_to_text(safe_get(message, "refusal", ""))
    raw_data = response_to_plain_data(response)
    try:
        raw = json.dumps(raw_data, ensure_ascii=False, default=str)
    except Exception:
        raw = repr(raw_data)
    if len(raw) > max_chars:
        raw = raw[:max_chars] + "...<truncated>"

    parts = [
        f"id={safe_get(response, 'id', '')}",
        f"model={safe_get(response, 'model', '')}",
        f"finish_reason={safe_get(choice, 'finish_reason', '')}",
        f"content_len={len(content.strip())}",
        f"reasoning_len={len(reasoning.strip())}",
    ]
    if refusal:
        parts.append(f"refusal={refusal[:200]!r}")
    tool_calls = safe_get(message, "tool_calls")
    if tool_calls:
        parts.append(f"tool_calls={tool_calls!r}")
    usage = safe_get(response, "usage")
    if usage:
        parts.append(f"usage={usage!r}")
    parts.append(f"raw={raw}")
    return "; ".join(parts)


def summarize_exception(error, max_chars=1000):
    pieces = [f"{error.__class__.__name__}: {error}"]
    for attr in ("status_code", "code", "type", "param"):
        value = getattr(error, attr, None)
        if value:
            pieces.append(f"{attr}={value}")
    body = getattr(error, "body", None)
    if body:
        pieces.append(f"body={body!r}")
    response = getattr(error, "response", None)
    if response is not None:
        try:
            pieces.append(f"response_status={getattr(response, 'status_code', '')}")
            pieces.append(f"response_text={getattr(response, 'text', '')[:max_chars]!r}")
        except Exception:
            pieces.append(f"response={response!r}")
    text = "; ".join(pieces)
    if len(text) > max_chars:
        return text[:max_chars] + "...<truncated>"
    return text
