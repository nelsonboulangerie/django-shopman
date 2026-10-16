# Shopman Watchman

`shopman-watchman` is a small reusable Django app for health checks and cheap
route-budget observation. It owns the check contract, registry, runner, JSON
representation, probe views, management command and the O(1) in-memory budget
recorder. It deliberately does **not** restart processes, configure a hosting
provider or replace an external uptime monitor: liveness tells the supervisor to
restart, and a monitor outside the instance proves that the supervisor itself is
still reachable.

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
    "BUDGETS": {
        "catalog": {
            "method": "GET",
            "route": "/api/catalog/",
            "max_duration_ms": 500,
            "max_queries": 20,
            "consecutive_failures": 3,
            "recovery_samples": 3,
        }
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

## Route budgets

Call `get_recorder().record(...)` after a request. Unconfigured routes cost one
dictionary lookup; configured routes add one bounded `deque` append. There is no
I/O and no global lock. Three consecutive breaches open an incident, reminders
use exponential spacing, and three healthy samples emit a resolved event. The
host decides how log events reach Sentry or e-mail and can expose
`PerformanceBudgetCheck` in a non-public profile.

Query budgets are enforced only when the host supplies a query count. Absence is
never interpreted as zero.

For configured routes, the first healthy observation emits a structured INFO
pulse; `BUDGET_HEARTBEAT_SAMPLES` (default: 1000) controls later pulses. The
cumulative count distinguishes "no breach" from "no measurement" without a
timer, thread, I/O or database query on ordinary requests; the only additional
hot-path work is an integer comparison.

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
