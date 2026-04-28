import importlib


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


def execute_player(target, context, update_observability, write_failure_snapshot):
    project_root = str(context.project_root)
    player = None
    try:
        player = create_player(target, context)
        update_observability(project_root, observability_payload("running", context, target))
        player.run()
        update_observability(project_root, observability_payload("completed", context, target))
    except PlayerImportError as e:
        update_observability(
            project_root,
            observability_payload("import_error", context, target, error=str(e)),
        )
        raise
    except Exception as e:
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


__all__ = [
    "PlayerImportError",
    "create_player",
    "execute_player",
    "import_player_class",
    "observability_payload",
]
