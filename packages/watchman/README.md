# Shopman Watchman

`shopman-watchman` is a small reusable Django app for health checks. It owns the
check contract, registry, runner, JSON representation, probe views and management
command. It deliberately does **not** restart processes, configure a hosting
provider or replace an external uptime monitor.

## Install

```python
INSTALLED_APPS = [
    # ...
    "shopman.watchman",
]

WATCHMAN = {
    "CHECKS": [
        "shopman.watchman.checks.ProcessCheck",
        "myproject.health.DatabaseCheck",
    ],
    "PROFILES": {
        "liveness": ["process"],
        "readiness": ["process", "database"],
        "diagnostic": ["process", "database"],
    },
}
```

Mount the package URLs wherever the deployment expects them:

```python
from django.urls import include, path

urlpatterns = [path("health/", include("shopman.watchman.urls"))]
```

This exposes `health/live/`, `health/ready/` and a staff-only
`health/status/`. Projects may also instantiate the views directly to preserve
existing URL contracts.

## Command

```console
python manage.py watchman check --profile diagnostic --format json
python manage.py watchman list --format json
python manage.py watchman explain process --format json
```

`check` exits with `0` when every check passes or warns, `1` when a check fails
or cannot complete, and `2` for invalid Watchman configuration (the shell sees
Django's command error exit code). The JSON schema is versioned.

## Writing a check

Checks perform their own bounded I/O. The runner provides a deadline but does
not pretend it can safely kill arbitrary Python code after a timeout.

```python
from shopman.watchman import CheckContext, CheckResult, Scope, Status

class DatabaseCheck:
    id = "database"
    description = "Database round-trip"
    scopes = frozenset({Scope.READINESS, Scope.DIAGNOSTIC})
    timeout_seconds = 2.0

    def run(self, context: CheckContext) -> CheckResult:
        timeout = context.remaining_seconds()
        # Execute a database operation with its own timeout <= `timeout`.
        return CheckResult(id=self.id, status=Status.PASS, summary="database answered")
```

Public probes expose only check IDs and statuses. Detailed evidence is available
only from the staff-protected status endpoint or the management command.
