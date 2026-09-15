"""Runs inside the offline container, exercising real Django WSGI META."""
import os
import time
import urllib.error
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
base = "http://127.0.0.1:" + os.environ.get("PORT", "8080")
for _attempt in range(50):
    try:
        with opener.open(base + "/health/", timeout=1) as response:
            assert response.read() == b"ok"
        break
    except OSError:
        time.sleep(0.1)
else:
    raise AssertionError("Observer did not start")

headers = {"X-Shopman-Admin-IP-Probe": os.environ["SHOPMAN_ADMIN_IP_PROBE_TOKEN"],
           "X-Shopman-Admin-IP-Probe-ID": "0123456789abcdef",
           "DO-Connecting-IP": "192.0.2.17", "X-Forwarded-For": "198.51.100.8, 127.0.0.1"}
for supplied in [{}, headers]:
    with opener.open(urllib.request.Request(base + "/admin/login/", headers=supplied)) as response:
        assert response.read() == b"isolated ingress observer"
        assert not response.headers.get("Set-Cookie")
        assert not response.headers.get("DO-Connecting-IP")
try:
    opener.open(urllib.request.Request(base + "/admin/login/", data=b"", headers=headers))
except urllib.error.HTTPError as error:
    assert error.code == 405
else:
    raise AssertionError("POST accepted")
print("container_http_smoke_passed")
