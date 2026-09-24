"""Trava: segredo de verdade não entra no repositório.

## Por que existe

O repositório é **público**. Em 30/06/2026 a chave de API da Comtele (a única da
conta, a que manda o SMS do login) entrou em `docs/plans/GO-LIVE-SMS-WHATSAPP-STATUS.md`
e, no mesmo dia, virou valor de fixture em `test_otp_sms_comtele.py`. Ficou lá
por quase três meses, até alguém ler o teste. O `secret scanning` do GitHub está
ligado, mas não reconhece chave da Comtele (não é provedor parceiro), então nada
acusou.

Esta trava cobre as duas metades do problema:

1. **Formato de provedor conhecido** (Stripe live, AWS, GitHub, Slack, Google,
   DigitalOcean, SendGrid, webhook do Stripe, token da Meta, chave privada PEM):
   se parece segredo, reprova.
2. **UUID atribuído a nome de credencial** (`api_key`, `token`, `secret`…). É o
   formato da chave da Comtele, e de muitas outras: nenhum provedor detecta, e
   um UUID "de exemplo" nunca é necessário em teste. Use texto que se declara
   falso (`"chave-ficticia-de-teste"`).
3. **Segredo que JÁ vazou** fica na lista negra por **hash** (SHA-256), nunca em
   claro. Se a chave antiga voltar por copiar e colar de um `.env` velho, o teste
   diz qual é, sem republicá-la.

Um valor legítimo que caia num padrão entra em ``_ALLOWED`` com o motivo escrito.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: SHA-256 de segredos que já foram publicados neste repositório. O valor em claro
#: NUNCA entra aqui. Para acrescentar: `printf %s '<segredo>' | shasum -a 256`.
_LEAKED_SHA256 = {
    # Chave de API da Comtele (SMS do login), publicada em 30/06/2026 nos commits
    # cefff8f8e e 4469773ab. Rotação: docs/runbooks/go-live-cutover.md §2.
    "2ca83bf7c04cb2e90176a4d99d46b55fc7c66d0da1911f7492be2dec4bb5abc5",
}

_PROVIDER_PATTERNS = {
    "Stripe secret/restricted live": r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}",
    "Stripe secret test (formato real)": r"\bsk_test_[A-Za-z0-9]{40,}",
    "Stripe webhook secret": r"\bwhsec_[A-Za-z0-9]{24,}",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "Slack token": r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    "Google API key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "DigitalOcean token": r"\bdo[po]_v1_[a-f0-9]{40,}",
    "SendGrid key": r"\bSG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
    "Meta/Facebook token": r"\bEAA[A-Za-z0-9]{60,}",
    "Chave privada PEM": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
}

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_CREDENTIAL_UUID = re.compile(
    r"(?i)(?:api[_-]?key|auth[_-]?key|access[_-]?key|secret|token|password|passwd|x-api-key)"
    r"[\"']?\s*[:=]\s*[\"']" + _UUID + r"[\"']"
)
_ANY_UUID = re.compile(_UUID)
_PROVIDER = {name: re.compile(p) for name, p in _PROVIDER_PATTERNS.items()}

#: (caminho, trecho) legítimos que casam um padrão, cada um com o motivo.
_ALLOWED: dict[tuple[str, str], str] = {}

_SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2", ".ttf",
    ".otf", ".eot", ".zip", ".gz", ".mmdb", ".sqlite3", ".pyc", ".mp4", ".webm", ".avif",
}
_SKIP_NAMES = {"package-lock.json", "uv.lock", "poetry.lock"}


def _tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "-z"],
            capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - sem git
        raise AssertionError("git ls-files falhou: a trava precisa da lista de arquivos versionados") from exc
    files = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        path = REPO / raw.decode("utf-8", "replace")
        if path.suffix.lower() in _SKIP_SUFFIXES or path.name in _SKIP_NAMES:
            continue
        files.append(path)
    return files


def _read(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", "replace")


def _masked(value: str) -> str:
    return value[:6] + "…" if len(value) > 6 else "…"


def test_nenhum_segredo_de_provedor_nem_uuid_de_credencial_versionado():
    findings: list[str] = []
    files = _tracked_files()
    assert len(files) > 500, f"só {len(files)} arquivos: a varredura não está olhando o repositório"

    for path in files:
        text = _read(path)
        if text is None:
            continue
        rel = str(path.relative_to(REPO))
        if rel == "shopman/shop/tests/test_sem_segredo_no_repositorio.py":
            continue

        for uuid in _ANY_UUID.findall(text):
            if hashlib.sha256(uuid.lower().encode()).hexdigest() in _LEAKED_SHA256:
                findings.append(f"{rel}: segredo JÁ VAZADO de volta ao repositório ({_masked(uuid)})")

        for name, rx in _PROVIDER.items():
            for match in rx.finditer(text):
                if (rel, match.group(0)) in _ALLOWED:
                    continue
                findings.append(f"{rel}: {name} ({_masked(match.group(0))})")

        for match in _CREDENTIAL_UUID.finditer(text):
            if (rel, match.group(0)) in _ALLOWED:
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{rel}:{line}: UUID atribuído a credencial — use um valor que se declare falso")

    assert not findings, (
        "Segredo no repositório (que é PÚBLICO). Tire o valor, ponha no segredo do "
        "ambiente e, se ele já foi publicado, ROTACIONE-O — apagar do arquivo não "
        "despublica o histórico:\n  " + "\n  ".join(findings)
    )


def test_a_lista_negra_guarda_hash_e_nao_o_segredo():
    for digest in _LEAKED_SHA256:
        assert re.fullmatch(r"[0-9a-f]{64}", digest), "a lista negra aceita só SHA-256 em hexadecimal"


def test_a_trava_reconhece_o_formato_que_vazou():
    # Prova de que a regra 2 pega o formato da chave da Comtele sem precisar dela.
    fake = '"api_key": "00000000-1111-2222-3333-444444444444"'
    assert _CREDENTIAL_UUID.search(fake)
    assert not _CREDENTIAL_UUID.search('"api_key": "chave-ficticia-de-teste-comtele"')
