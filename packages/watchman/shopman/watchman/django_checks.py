"""Django system check for Watchman configuration drift."""

from django.core.checks import Error, Tags, register

from shopman.watchman.registry import build_registry


@register(Tags.compatibility)
def check_watchman_configuration(app_configs, **kwargs):
    try:
        build_registry()
    except Exception as exc:  # noqa: BLE001 - Django check must turn config failures into diagnostics
        return [
            Error(
                f"Invalid Watchman configuration ({exc.__class__.__name__}): {exc}",
                id="watchman.E001",
            )
        ]
    return []
