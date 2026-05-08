import importlib

from agent.probe_adapter import (
    close_probe_handle,
    create_probe_handle,
    record_probe_complete,
    record_probe_error,
    record_probe_start,
)


class PlayerImportError(Exception):
    def __init__(self, target, original):
        super().__init__(str(original))
        self.target = target
        self.original = original


def observability_payload(status, context, target, **extra):
    payload = {
        "status": status,
        "account_file": str(context.account_path),
        "mode": context.mode,
        "module": target.module_name,
    }
    payload.update(extra)
    return payload


def import_player_class(target):
    try:
        module = importlib.import_module(target.module_name)
        return getattr(module, target.class_name)
    except ImportError as e:
        raise PlayerImportError(target, e)


def create_player(target, context):
    player_class = import_player_class(target)
    return player_class(account_file=str(context.account_path), headless=context.headless)


def _context_config_for_probe(context):
    try:
        normalized_config = getattr(context, "normalized_config")
    except Exception:
        normalized_config = None
    if isinstance(normalized_config, dict):
        return normalized_config

    try:
        config = getattr(context, "config", {})
    except Exception:
        config = {}
    return config if isinstance(config, dict) else {}


def _create_probe_handle_for_runner(project_root, context):
    try:
        return create_probe_handle(project_root, _context_config_for_probe(context))
    except Exception:
        return None


def _probe_common_kwargs(context):
    return {
        "mode": getattr(context, "mode", ""),
        "account_file": str(getattr(context, "account_path", "")),
    }


def _safe_probe_call(callback, *args, **kwargs):
    try:
        return callback(*args, **kwargs)
    except Exception:
        return None


def execute_player(target, context, update_observability, write_failure_snapshot):
    project_root = str(context.project_root)
    probe_handle = _create_probe_handle_for_runner(project_root, context)
    _safe_probe_call(
        record_probe_start,
        probe_handle,
        **_probe_common_kwargs(context),
        notes=f"module={target.module_name}; class={target.class_name}",
    )
    player = None
    try:
        player = create_player(target, context)
        update_observability(project_root, observability_payload("running", context, target))
        player.run()
        _safe_probe_call(
            record_probe_complete,
            probe_handle,
            **_probe_common_kwargs(context),
            notes=f"module={target.module_name}; status=completed",
        )
        update_observability(project_root, observability_payload("completed", context, target))
    except PlayerImportError as e:
        _safe_probe_call(
            record_probe_error,
            probe_handle,
            e,
            **_probe_common_kwargs(context),
            notes=f"module={target.module_name}; error_type=PlayerImportError",
        )
        update_observability(
            project_root,
            observability_payload("import_error", context, target, error=str(e)),
        )
        raise
    except Exception as e:
        _safe_probe_call(
            record_probe_error,
            probe_handle,
            e,
            **_probe_common_kwargs(context),
            notes=f"module={target.module_name}; error_type={type(e).__name__}",
        )
        snapshot_file = write_failure_snapshot(
            project_root,
            str(context.account_path),
            target.module_name,
            player,
            e,
        )
        update_observability(
            project_root,
            observability_payload("failed", context, target, error=str(e), snapshot=snapshot_file),
        )
        raise
    finally:
        _safe_probe_call(close_probe_handle, probe_handle)


__all__ = [
    "PlayerImportError",
    "create_player",
    "execute_player",
    "import_player_class",
    "observability_payload",
]
