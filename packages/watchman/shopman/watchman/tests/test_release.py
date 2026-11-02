import time
import urllib.error

import pytest
from django.test import override_settings

from shopman.watchman.contracts import CheckContext, Status
from shopman.watchman.release import (
    ReleaseIdentityCheck,
    ReleasePayloadError,
    current_release,
    parse_release_payload,
)

SHA_MAIN = "a" * 40
SHA_OLD = "b" * 40
RELEASE_ID = "20261102-1403-aaaaaaa"


def _context():
    return CheckContext(profile="release", deadline=time.monotonic() + 10)


def _payload(component="web", sha=SHA_MAIN, release_id=RELEASE_ID):
    return {"schema_version": 1, "component": component, "release_id": release_id, "build_sha": sha}


CONFIG = {
    "RELEASE_IDENTITY": {
        "expected_sha_env": "EXPECTED",
        "targets": [
            {"id": "web", "url_env": "URL_WEB"},
            {"id": "operator-floor", "url_env": "URL_FLOOR"},
        ],
    }
}
ENV = {"EXPECTED": SHA_MAIN, "URL_WEB": "https://api.test/health/release/", "URL_FLOOR": "https://pdv.test/health/release"}


def _check(answers, env=ENV):
    def fetch(url, timeout):
        answer = answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return ReleaseIdentityCheck(fetcher=fetch, environ=env)


# ── Identity of this process ──────────────────────────────────────────────────


def test_current_release_reads_the_image_environment():
    identity = current_release(
        {"SHOPMAN_BUILD_SHA": SHA_MAIN, "SHOPMAN_RELEASE_ID": RELEASE_ID, "SHOPMAN_RELEASE_COMPONENT": "web"}
    )
    assert identity.identified
    assert identity.to_dict() == _payload()


def test_current_release_never_invents_a_value():
    identity = current_release({}, default_component="web")
    assert not identity.identified
    assert identity.to_dict() == _payload(sha="", release_id="")


def test_malformed_build_values_are_reported_as_absent():
    identity = current_release({"SHOPMAN_BUILD_SHA": "main", "SHOPMAN_RELEASE_ID": "v2.3.1"}, default_component="web")
    assert identity.build_sha == ""
    assert identity.release_id == ""


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {**_payload(), "schema_version": 2},
        {**_payload(), "build_sha": "abc"},
        {**_payload(), "release_id": "latest"},
        {**_payload(), "component": "Web Service"},
        {**_payload(), "build_sha": None},
    ],
)
def test_payload_outside_the_contract_is_rejected(payload):
    with pytest.raises(ReleasePayloadError):
        parse_release_payload(payload)


def test_release_address_is_public_cheap_and_secret_free(client, monkeypatch):
    monkeypatch.setenv("SHOPMAN_BUILD_SHA", SHA_MAIN)
    monkeypatch.setenv("SHOPMAN_RELEASE_ID", RELEASE_ID)
    monkeypatch.setenv("SHOPMAN_RELEASE_COMPONENT", "web")

    response = client.get("/health/release/")

    assert response.status_code == 200
    assert response.json() == _payload()
    assert response["Cache-Control"] == "no-store"
    assert response["X-Shopman-Release"] == RELEASE_ID


def test_release_address_without_identity_says_so(client, monkeypatch):
    for name in ("SHOPMAN_BUILD_SHA", "SHOPMAN_RELEASE_ID", "SHOPMAN_RELEASE_COMPONENT"):
        monkeypatch.delenv(name, raising=False)

    response = client.get("/health/release/")

    assert response.json() == _payload(sha="", release_id="")
    assert "X-Shopman-Release" not in response


# ── Probe ─────────────────────────────────────────────────────────────────────


@override_settings(WATCHMAN=CONFIG)
def test_probe_passes_when_every_component_serves_main():
    check = _check({ENV["URL_WEB"]: _payload(), ENV["URL_FLOOR"]: _payload(component="operator-floor")})

    result = check.run(_context())

    assert result.status is Status.PASS
    assert [c["reason"] for c in result.evidence["components"]] == ["same_commit", "same_commit"]


@override_settings(WATCHMAN=CONFIG)
def test_probe_fails_on_a_different_commit_without_history():
    check = _check({ENV["URL_WEB"]: _payload(), ENV["URL_FLOOR"]: _payload(component="operator-floor", sha=SHA_OLD)})

    result = check.run(_context())

    assert result.status is Status.FAIL
    assert "operator-floor" in result.summary
    assert result.evidence["components"][1]["reason"] == "different_commit"


def _unchanged(target_id, live, expected):
    return target_id == "operator-floor"


def _no_history(target_id, live, expected):
    return None


@override_settings(WATCHMAN={"RELEASE_IDENTITY": {**CONFIG["RELEASE_IDENTITY"], "equivalence": __name__ + "._unchanged"}})
def test_equivalence_accepts_a_component_nothing_touched_since():
    check = _check(
        {ENV["URL_WEB"]: _payload(sha=SHA_OLD), ENV["URL_FLOOR"]: _payload(component="operator-floor", sha=SHA_OLD)}
    )

    result = check.run(_context())

    reasons = {c["id"]: c["reason"] for c in result.evidence["components"]}
    assert reasons == {"web": "behind_expected", "operator-floor": "unchanged_since_live"}
    assert result.status is Status.FAIL


@override_settings(WATCHMAN={"RELEASE_IDENTITY": {**CONFIG["RELEASE_IDENTITY"], "equivalence": __name__ + "._no_history"}})
def test_missing_history_is_unknown_not_pass():
    check = _check(
        {ENV["URL_WEB"]: _payload(), ENV["URL_FLOOR"]: _payload(component="operator-floor", sha=SHA_OLD)}
    )

    assert check.run(_context()).status is Status.UNKNOWN


@override_settings(WATCHMAN=CONFIG)
def test_unreachable_address_is_absence_of_proof():
    check = _check({ENV["URL_WEB"]: _payload(), ENV["URL_FLOOR"]: urllib.error.URLError("down")})

    result = check.run(_context())

    assert result.status is Status.UNKNOWN
    assert result.evidence["components"][1]["reason"] == "unreachable"


@override_settings(WATCHMAN=CONFIG)
def test_build_without_identity_fails():
    check = _check(
        {ENV["URL_WEB"]: _payload(sha="", release_id=""), ENV["URL_FLOOR"]: _payload(component="operator-floor")}
    )

    result = check.run(_context())

    assert result.status is Status.FAIL
    assert result.evidence["components"][0]["reason"] == "unidentified_build"


@override_settings(WATCHMAN=CONFIG)
def test_address_serving_another_component_fails():
    check = _check({ENV["URL_WEB"]: _payload(), ENV["URL_FLOOR"]: _payload(component="operator-office")})

    result = check.run(_context())

    assert result.evidence["components"][1]["reason"] == "other_component"
    assert result.status is Status.FAIL


@override_settings(WATCHMAN=CONFIG)
def test_missing_expected_commit_and_address_are_unknown():
    check = _check({ENV["URL_WEB"]: _payload()}, env={"URL_WEB": ENV["URL_WEB"]})

    result = check.run(_context())

    reasons = [c["reason"] for c in result.evidence["components"]]
    assert reasons == ["expected_sha_missing", "address_not_configured"]
    assert result.status is Status.UNKNOWN


@override_settings(WATCHMAN={})
def test_unconfigured_probe_is_unknown():
    assert ReleaseIdentityCheck(environ={}).run(_context()).status is Status.UNKNOWN
