"""Verify OCI blob hashes and distinguish manifest digest from image config ID."""
import hashlib
import hmac
import json
import sys
import tarfile
from pathlib import Path

archive, image_id, log_path = sys.argv[1:]
with tarfile.open(archive) as tar:
    index_bytes = tar.extractfile("index.json").read()
    index = json.loads(index_bytes)
    for member in tar.getmembers():
        if member.isfile() and member.name.startswith("blobs/sha256/"):
            payload = tar.extractfile(member).read()
            assert hashlib.sha256(payload).hexdigest() == member.name.rsplit("/", 1)[1]
    descriptor = index["manifests"][0]
    manifest_bytes = tar.extractfile("blobs/sha256/" + descriptor["digest"].split(":")[1]).read()
    manifest = json.loads(manifest_bytes)
    assert manifest["mediaType"] == "application/vnd.oci.image.manifest.v1+json"
    assert descriptor["digest"] == "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    assert manifest["config"]["digest"] == image_id
    config = json.loads(tar.extractfile("blobs/sha256/" + image_id.split(":")[1]).read())
    assert config["config"]["User"] == "65532:65532"
    for variable in config["config"].get("Env", []):
        assert not any(word in variable.upper() for word in ["TOKEN=", "PASSWORD=", "DATABASE_URL=", "SECRET_KEY="])

log = Path(log_path).read_text()
records = [json.loads(line.split("admin_ip_probe ", 1)[1]) for line in log.splitlines() if "admin_ip_probe " in line]
assert len(records) == 1, "Only the authorized anonymous GET should log a probe"
assert records[0]["marker"] == "0123456789abcdef"
assert records[0]["do"] == hmac.new(b"ci-synthetic-probe-token-no-real-secret", b"admin-ip-probe:192.0.2.17", hashlib.sha256).hexdigest()
assert records[0]["do"] != records[0]["remote"]
assert records[0]["remote"] == records[0]["xff"][1]
for raw in ["192.0.2.17", "198.51.100.8", "127.0.0.1", "ci-synthetic-probe-token-no-real-secret"]:
    assert raw not in log
print(json.dumps({"oci_manifest_digest": descriptor["digest"],
    "oci_index_digest": "sha256:" + hashlib.sha256(index_bytes).hexdigest(),
    "image_config_digest": image_id, "verified_blobs": True,
    "container_http_and_meta": "passed", "raw_header_and_token_log_check": "passed"}, indent=2))
