"""Checks that are safe for every Django project."""

from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status


class ProcessCheck:
    id = "process"
    description = "The Django process can execute the Watchman probe."
    scopes = frozenset({Scope.LIVENESS, Scope.READINESS, Scope.DIAGNOSTIC})
    timeout_seconds = 0.05

    def run(self, context: CheckContext) -> CheckResult:
        return CheckResult(
            id=self.id,
            status=Status.PASS,
            summary="process is serving requests",
        )
