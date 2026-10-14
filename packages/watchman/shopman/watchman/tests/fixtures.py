from __future__ import annotations

import time

from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status


class FailCheck:
    id = "failure"
    description = "Always fails."
    scopes = frozenset({Scope.LIVENESS, Scope.DIAGNOSTIC})
    timeout_seconds = 0.1

    def run(self, context: CheckContext) -> CheckResult:
        return CheckResult(
            id=self.id,
            status=Status.FAIL,
            summary="synthetic failure",
            evidence={"private": "evidence"},
        )


class ErrorCheck:
    id = "error"
    description = "Raises an exception."
    scopes = frozenset({Scope.LIVENESS, Scope.DIAGNOSTIC})
    timeout_seconds = 0.1

    def run(self, context: CheckContext) -> CheckResult:
        raise RuntimeError("secret exception detail")


class SlowCheck:
    id = "slow"
    description = "Exceeds its declared deadline."
    scopes = frozenset({Scope.DIAGNOSTIC})
    timeout_seconds = 0.001

    def run(self, context: CheckContext) -> CheckResult:
        time.sleep(0.005)
        return CheckResult(id=self.id, status=Status.PASS, summary="late")


class WrongIdCheck:
    id = "expected"
    description = "Returns a different ID."
    scopes = frozenset({Scope.DIAGNOSTIC})
    timeout_seconds = 0.1

    def run(self, context: CheckContext) -> CheckResult:
        return CheckResult(id="different", status=Status.PASS, summary="wrong")
