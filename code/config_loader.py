import json
from pathlib import Path


CONFIG_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb2312")


class ConfigLoadError(Exception):
    """Raised when an account/config JSON file cannot be loaded."""


def load_json_config(file_path, encodings=CONFIG_ENCODINGS):
    path = Path(file_path)
    if not path.exists():
        raise ConfigLoadError(f"找不到配置文件: {path}")

    parse_errors = []
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding) as f:
                data = json.load(f)
        except UnicodeDecodeError as e:
            parse_errors.append(f"{encoding}: {e}")
            continue
        except json.JSONDecodeError as e:
            parse_errors.append(f"{encoding}: {e}")
            continue

        if not isinstance(data, dict):
            raise ConfigLoadError(f"配置文件顶层必须是JSON对象: {path}")
        return data

    detail = "; ".join(parse_errors[-2:])
    if detail:
        raise ConfigLoadError(f"无法解析配置文件: {path} ({detail})")
    raise ConfigLoadError(f"无法解析配置文件: {path}")
