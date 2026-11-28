"""Out-of-band OTP delivery channel for the live storefront E2E harness."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class E2EFileSender:
    """Deliver the generated code through a process-shared, private file."""

    reveals_code = True

    def send_code(self, target: str, code: str, method: str) -> bool:
        del target, method
        destination_value = os.environ.get("SHOPMAN_E2E_OTP_FILE", "").strip()
        if not destination_value:
            return False

        destination = Path(destination_value)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                delete=False,
            ) as stream:
                stream.write(code)
                temporary = Path(stream.name)
            temporary.chmod(0o600)
            temporary.replace(destination)
            temporary = None
            destination.chmod(0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return True
