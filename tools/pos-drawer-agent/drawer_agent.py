#!/usr/bin/env python3
"""Agente local que abre a gaveta de dinheiro do PDV.

O PDV roda no navegador e o navegador não fala ESC/POS. A gaveta não tem cabo
próprio: ela pendura no RJ11 da impressora e abre quando a impressora recebe
``ESC p m t1 t2``. Como a TM-T20 é USB e o driver do sistema já é dono da
interface (é assim que o ``window.print()`` do recibo funciona), não há WebUSB
possível — brigar pela interface quebraria a impressão.

Sobra este caminho: um processo local que recebe um pedido do navegador em
``127.0.0.1`` e entrega os cinco bytes ao **spooler** como trabalho raw, pela
mesma fila por onde o recibo já sai.

Zero dependências: é um processo que precisa subir junto com o balcão, todo dia,
sem ninguém olhando. ``pip install`` é uma coisa a mais para quebrar às 6h.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.0.0"


def build_id() -> str:
    """Impressão digital deste arquivo.

    A máquina do balcão só recebe atualização pelo download do Admin, e não há
    rede nem pendrive para conferir versões. Sem um carimbo, ninguém sabe se o
    caixa está com o agente atual — e "reinstalei e continua igual" vira meia
    hora perdida.

    Hash do conteúdo em vez de número escrito à mão: ninguém precisa lembrar de
    bumpar, e dois arquivos iguais têm o mesmo carimbo por construção.
    """
    import hashlib

    try:
        fonte = Path(__file__).resolve().read_bytes()
    except OSError:
        return "desconhecido"
    return hashlib.sha256(fonte).hexdigest()[:8]

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"

#: Tudo do agente numa pasta só, por sistema — programa, config e log juntos.
#: A primeira versão espalhava: no Windows o programa ia para
#: `%LOCALAPPDATA%\NelsonPosDrawer` e a config para uma pasta `.config` de estilo
#: Linux, escondida na pasta do usuário. Quem estivesse no balcão procurando o
#: token não acharia. Um lugar, uma resposta.
def install_dir_for(home: Path, *, windows: bool, localappdata: str = "") -> Path:
    if windows:
        return Path(localappdata or home / "AppData" / "Local") / "NelsonPosDrawer"
    return home / ".local" / "share" / "nelson-pos-drawer"


def config_path_for(home: Path, *, windows: bool, localappdata: str = "") -> Path:
    """Onde a config mora, por sistema.

    No Windows, junto do programa. No Linux/macOS, em ``~/.config`` — que é onde
    quem administra a máquina espera achar.
    """
    if windows:
        return install_dir_for(home, windows=True, localappdata=localappdata) / "agent.json"
    return home / ".config" / "nelson-pos-drawer" / "agent.json"


INSTALL_DIR = install_dir_for(
    Path.home(), windows=IS_WINDOWS, localappdata=os.environ.get("LOCALAPPDATA", "")
)
_LEGACY_CONFIG_PATH = Path.home() / ".config" / "nelson-pos-drawer" / "agent.json"
DEFAULT_CONFIG_PATH = Path(os.environ.get("DRAWER_AGENT_CONFIG") or "") if os.environ.get(
    "DRAWER_AGENT_CONFIG"
) else config_path_for(Path.home(), windows=IS_WINDOWS, localappdata=os.environ.get("LOCALAPPDATA", ""))

LOG_PATH = INSTALL_DIR / "drawer-agent.log"

logger = logging.getLogger("drawer-agent")

# ── ESC/POS ───────────────────────────────────────────────────────────────

ESC = 0x1B

#: Teto do pulso, em unidades de 2ms — o que ``ESC p`` aceita por byte.
#: Não é preciosismo: mandar 255 aqui deixa o solenoide energizado por meio
#: segundo. O solenoide da gaveta é feito para pulso, não para carga contínua;
#: segurar demais aquece a bobina. O firmware satura, mas quem lê o log merece
#: ver o valor recusado em vez de descobrir no cheiro de verniz queimado.
_PULSE_UNIT_MS = 2
_PULSE_MAX_UNITS = 255


def kick_bytes(*, pin: int = 0, on_ms: int = 50, off_ms: int = 500) -> bytes:
    """Monta ``ESC p m t1 t2``.

    ``m`` escolhe o pino do conector (0 = pino 2, 1 = pino 5). ``t1``/``t2`` são
    o pulso em unidades de 2ms.

    ⚠️ **Os defaults são 50/500ms, não 25/250.** A sequência canônica da TM-T20
    é ``1B 70 00 19 FA``, e ``0x19``/``0xFA`` são 25 e 250 **unidades** — que a
    2ms cada dão 50ms e 500ms. Chamar isso de "pulso 25/250ms" é atalho comum e
    erra por metade. Esta função fala **milissegundos** porque é o que uma
    pessoa configurando entende; a conversão para unidades é problema dela.
    """
    if pin not in (0, 1):
        raise ValueError("pino da gaveta deve ser 0 (pino 2) ou 1 (pino 5)")
    on_units = _pulse_units(on_ms, "on_ms")
    off_units = _pulse_units(off_ms, "off_ms")
    return bytes([ESC, ord("p"), pin, on_units, off_units])


# ── Página de teste ───────────────────────────────────────────────────────
#
# Antes de compor recibo — e muito antes de compor DANFE, que tem leiaute
# exigido por lei — vale descobrir o que ESTA impressora faz. Esta página não
# tenta ser bonita: ela faz o papel responder três perguntas que ninguém
# consegue responder de cabeça.
#
# ⚠️ A página de código NÃO é chutada aqui. A mesma frase acentuada sai sob
# várias tabelas, rotulada. O papel diz qual está certa; escolher uma no escuro
# é como "PÃO" vira "PÎO" no balcão.

#: `ESC t n` — tabelas de caractere que interessam ao português.
_CODE_PAGES = ((3, "PC860 Portugues"), (2, "PC850 Multilingual"), (16, "WPC1252"))

#: Largura em colunas da Fonte A numa térmica de 80mm. A régua confirma.
_COLUMNS = 48

#: Até onde a régua vai. Passa de 48 de propósito: a Fonte B da TM-T20 dá 64
#: colunas, e a primeira rodada do teste voltou com "coube e sobrou espaço" —
#: sinal de que a impressora não estava na largura que assumi. Régua que para
#: onde eu chutei não descobre largura nenhuma.
_RULER_MAX = 64

#: Frase de aferição de acento. A primeira versão não discriminava: as
#: maiúsculas iam SEM acento no código-fonte (saíam iguais em qualquer tabela) e
#: entre as minúsculas só o "ã" separava as tabelas — um caractere, fácil de não
#: notar. Agora cobre maiúsculas e minúsculas e junta os acentos que MUDAM de
#: byte entre CP860, CP850 e WPC1252.
_ACCENT_SAMPLE = "PÃO ÁGUA AÇÚCAR ÊNFASE ÕRFÃ · pão água açúcar ênfase órfã"


#: Conteúdo do QR de teste. Texto neutro de propósito: o agente é genérico, e um
#: domínio de deployment cravado aqui é a mesma armadilha da origem inventada.
_QR_SAMPLE = "NELSON POS - TESTE DE QR CODE"


def test_print_bytes(*, columns: int = _COLUMNS, qr_data: str = _QR_SAMPLE) -> bytes:
    """Amostra de diagnóstico: acento, largura/alinhamento e QR nativo."""
    out = bytearray()
    out += bytes([ESC, ord("@")])  # reset

    out += _line("TESTE DE IMPRESSAO")
    out += _line("Agente da gaveta - Nelson")
    out += _line("-" * columns)

    # 1) Acento: a mesma frase sob cada tabela, rotulada.
    out += _line("1) ACENTO - qual bloco saiu SEM lixo?")
    out += _line("   (compare letra a letra, inclusive as MAIUSCULAS)")
    for code, nome in _CODE_PAGES:
        out += bytes([ESC, ord("t"), code])
        out += _line(f"  [{nome}]")
        out += _encoded(f"  {_ACCENT_SAMPLE}", code)
    out += bytes([ESC, ord("t"), _CODE_PAGES[0][0]])
    out += _line("")

    # 2) Largura: a régua vai ALÉM do que assumi, senão não descobre nada.
    out += _line("2) LARGURA - ate que numero a regua chega?")
    out += _line(_ruler(_RULER_MAX))
    out += _line(_two_columns("Pao frances", "R$ 0,90", columns))
    out += _line(_two_columns("Sonho de creme", "R$ 7,50", columns))
    out += _line(_two_columns("TOTAL", "R$ 8,40", columns))
    out += _line("")

    # 3) QR nativo: se sair em branco, esta impressora precisa de QR em imagem.
    out += _line("3) QR - saiu um quadrado legivel?")
    out += _qr_code(qr_data)
    out += _line("")
    out += _line("Fim do teste.")

    out += bytes([ESC, ord("d"), 4])  # avanca antes de cortar
    out += bytes([0x1D, ord("V"), 1])  # corte parcial
    return bytes(out)


def _line(text: str) -> bytes:
    return text.encode("cp860", "replace") + b"\n"


def _encoded(text: str, code_page: int) -> bytes:
    """A frase acentuada codificada na tabela que acabou de ser selecionada."""
    encoding = {3: "cp860", 2: "cp850", 16: "cp1252"}.get(code_page, "cp860")
    return text.encode(encoding, "replace") + b"\n"


def _ruler(width: int) -> str:
    """Régua legível: marca dezenas, o resto são traços.

    `----+----1----+----2…` — quem lê o papel só precisa dizer o último número
    que apareceu inteiro, e isso dá a largura real da impressora.
    """
    marcas = []
    for i in range(1, width + 1):
        if i % 10 == 0:
            marcas.append(str(i // 10))
        elif i % 5 == 0:
            marcas.append("+")
        else:
            marcas.append("-")
    return "".join(marcas)


def _two_columns(left: str, right: str, columns: int) -> str:
    """Nome à esquerda, valor à direita, preenchendo a linha."""
    espaco = max(1, columns - len(left) - len(right))
    return f"{left}{' ' * espaco}{right}"[:columns]


def _qr_code(data: str, *, module: int = 6) -> bytes:
    """QR nativo do ESC/POS (`GS ( k`), modelo 2.

    ⚠️ O comprimento conta ``cn``, ``fn`` e ``m`` além dos dados — três bytes a
    mais. Errar isso é o defeito clássico deste comando: a impressora lê menos
    dados do que existe e imprime lixo ou nada.
    """
    payload = data.encode("utf-8")
    tamanho = len(payload) + 3
    return bytes(
        [0x1D, 0x28, 0x6B, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00]  # modelo 2
        + [0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x43, module]  # tamanho do modulo
        + [0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x45, 0x31]  # correcao de erro M
        + [0x1D, 0x28, 0x6B, tamanho % 256, tamanho // 256, 0x31, 0x50, 0x30]
    ) + payload + bytes([0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x51, 0x30])  # imprime


def _pulse_units(value_ms: int, label: str) -> int:
    units = int(value_ms) // _PULSE_UNIT_MS
    if units < 1:
        raise ValueError(f"{label} curto demais: {value_ms}ms não chega a um pulso")
    if units > _PULSE_MAX_UNITS:
        raise ValueError(
            f"{label} longo demais: {value_ms}ms passa do teto de "
            f"{_PULSE_MAX_UNITS * _PULSE_UNIT_MS}ms"
        )
    return units


# ── Config ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentConfig:
    """Fatos da MÁQUINA do balcão — e só eles.

    O pulso e a política (abre na venda? adapter?) moram no Django, por
    terminal, e chegam no request. Se morassem aqui também, um dia os dois
    discordariam e ninguém saberia qual manda.
    """

    queue: str
    token: str
    port: int = 47811
    host: str = "127.0.0.1"
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def load(cls, path: Path) -> AgentConfig:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SystemExit(
                f"config não encontrada em {path}.\n"
                "Rode 'python3 drawer_agent.py --install' ou aponte DRAWER_AGENT_CONFIG para o arquivo."
            ) from exc
        except json.JSONDecodeError as exc:
            raise SystemExit(f"config inválida em {path}: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> AgentConfig:
        queue = str(raw.get("queue") or "").strip()
        token = str(raw.get("token") or "").strip()
        if not queue:
            raise SystemExit("config sem 'queue': o nome da fila CUPS da impressora.")
        # Sem token o agente é um botão de abrir gaveta exposto a qualquer aba
        # que o balcão abrir. Recusar é a única resposta honesta.
        if len(token) < 16:
            raise SystemExit("config sem 'token' (mínimo 16 caracteres).")
        origins = raw.get("allowed_origins") or []
        if not isinstance(origins, list):
            raise SystemExit("'allowed_origins' deve ser uma lista de origens.")
        return cls(
            queue=queue,
            token=token,
            port=int(raw.get("port") or 47811),
            host=str(raw.get("host") or "127.0.0.1"),
            allowed_origins=tuple(str(o).rstrip("/") for o in origins if str(o).strip()),
        )

    def allows(self, origin: str) -> bool:
        if not self.allowed_origins:
            return True
        return (origin or "").rstrip("/") in self.allowed_origins


# ── Spooler ───────────────────────────────────────────────────────────────
#
# Duas implementações, não três. Linux e macOS falam CUPS e usam o MESMO
# comando; só o Windows tem spooler próprio.
#
# ⚠️ O macOS quase ficou de fora por um erro de leitura meu: `lpadmin -m raw`
# responde "Filas brutas não são mais compatíveis com o macOS", e eu li isso
# como "não dá para mandar bytes crus". O que a Apple removeu foi o **driver**
# raw; a **opção de job** `-o raw` continua existindo, e numa fila sem driver
# ela entrega os bytes intactos. Medido: `1b 70 00 19 fa` chegou inteiro.


class SpoolerError(RuntimeError):
    pass


def send_raw(payload: bytes, *, queue: str, title: str = "cash-drawer") -> str:
    """Entrega bytes crus à fila e devolve o id do job."""
    if IS_WINDOWS:
        return _send_raw_windows(payload, queue=queue, title=title)
    return _send_raw_cups(payload, queue=queue, title=title)


def _send_raw_cups(payload: bytes, *, queue: str, title: str) -> str:
    """Linux e macOS.

    ``-o raw`` é o ponto todo: sem ele o CUPS tenta *interpretar* o conteúdo e
    o filtro de texto transforma os cinco bytes em cinco bytes impressos.
    """
    lp = shutil.which("lp")
    if not lp:
        raise SpoolerError("comando 'lp' não encontrado — CUPS instalado?")
    try:
        completed = subprocess.run(
            [lp, "-d", queue, "-o", "raw", "-t", title, "-"],
            input=payload,
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise SpoolerError(f"fila '{queue}' não respondeu em 10s") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or b"").decode("utf-8", "replace").strip()
        raise SpoolerError(detail or f"lp saiu com código {completed.returncode}")
    return _job_id(completed.stdout)


def _send_raw_windows(payload: bytes, *, queue: str, title: str) -> str:
    """Windows, pelo spooler do sistema (winspool), via ctypes.

    O datatype ``RAW`` é o equivalente do ``-o raw`` do CUPS: diz ao spooler
    para entregar os bytes ao aparelho sem passar pelo driver de impressão.
    ctypes em vez de pywin32 porque o agente não tem dependências — o balcão
    não é lugar de `pip install` às 6h da manhã.
    """
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [
            ("pDocName", wintypes.LPWSTR),
            ("pOutputFile", wintypes.LPWSTR),
            ("pDatatype", wintypes.LPWSTR),
        ]

    winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    winspool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
    winspool.WritePrinter.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]

    def _fail(step: str) -> SpoolerError:
        return SpoolerError(f"{step} falhou (erro {ctypes.get_last_error()}) na fila '{queue}'")

    handle = wintypes.HANDLE()
    if not winspool.OpenPrinterW(queue, ctypes.byref(handle), None):
        raise _fail("abrir a impressora")
    try:
        job = winspool.StartDocPrinterW(handle, 1, ctypes.byref(DOC_INFO_1(title, None, "RAW")))
        if not job:
            raise _fail("iniciar o trabalho")
        try:
            if not winspool.StartPagePrinter(handle):
                raise _fail("iniciar a página")
            written = wintypes.DWORD(0)
            # Comprimento explícito: `create_string_buffer(payload)` sozinho
            # acrescenta um NUL no fim, e um sexto byte indo para a impressora
            # não é o que o manual manda.
            buffer = ctypes.create_string_buffer(payload, len(payload))
            if not winspool.WritePrinter(handle, buffer, len(payload), ctypes.byref(written)):
                raise _fail("escrever na impressora")
            if written.value != len(payload):
                raise SpoolerError(f"spooler aceitou {written.value} de {len(payload)} bytes")
            winspool.EndPagePrinter(handle)
        finally:
            winspool.EndDocPrinter(handle)
    finally:
        winspool.ClosePrinter(handle)
    return str(job)


def _job_id(stdout: bytes) -> str:
    # "request id is FILA-42 (1 file(s))" — nunca deixe a falta do id derrubar
    # um kick que já saiu.
    text = (stdout or b"").decode("utf-8", "replace")
    marker = "request id is "
    if marker in text:
        return text.split(marker, 1)[1].split(" ", 1)[0].strip()
    return ""


def probe_queue(queue: str) -> dict:
    """A fila existe e aceita trabalho?

    Isto é o quanto dá para saber sem aparelho na mão. Se a gaveta está plugada
    no RJ11 da impressora, ou se abriu, esta sonda **não** sabe — a resposta
    viria pelo canal bidirecional, que um job de spool não tem. Quem confirma é
    o olho do operador no teste de gaveta.
    """
    if IS_WINDOWS:
        return _probe_queue_windows(queue)
    return _probe_queue_cups(queue)


def _probe_queue_windows(queue: str) -> dict:
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    handle = wintypes.HANDLE()
    if not winspool.OpenPrinterW(queue, ctypes.byref(handle), None):
        return {"ok": False, "accepting": False, "reason": f"impressora '{queue}' não encontrada no Windows"}
    winspool.ClosePrinter(handle)
    return {"ok": True, "accepting": True, "reason": ""}


def _probe_queue_cups(queue: str) -> dict:
    lpstat = shutil.which("lpstat")
    if not lpstat:
        return {"ok": False, "accepting": False, "reason": "comando 'lpstat' não encontrado"}
    try:
        completed = subprocess.run(
            [lpstat, "-a", queue], capture_output=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "accepting": False, "reason": "CUPS não respondeu em 10s"}
    out = (completed.stdout or b"").decode("utf-8", "replace").strip()
    err = (completed.stderr or b"").decode("utf-8", "replace").strip()
    if completed.returncode != 0:
        return {"ok": False, "accepting": False, "reason": err or f"fila '{queue}' desconhecida"}
    accepting = "accepting requests" in out and "not accepting" not in out
    return {
        "ok": accepting,
        "accepting": accepting,
        "reason": "" if accepting else (out or f"fila '{queue}' não está aceitando trabalho"),
    }


# ── HTTP ──────────────────────────────────────────────────────────────────


class DrawerHandler(BaseHTTPRequestHandler):
    server_version = f"nelson-drawer-agent/{VERSION}"
    config: AgentConfig  # injetado pelo serve()

    protocol_version = "HTTP/1.1"

    # -- plumbing ------------------------------------------------------

    def _origin(self) -> str:
        return self.headers.get("Origin") or ""

    def _cors_headers(self) -> None:
        origin = self._origin()
        if origin and self.config.allows(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        # Um comprovante em base64 já passa de 8 KB, e a DANFE passa mais. O
        # teto continua existindo para o agente não virar despejo de memória.
        if length > 512 * 1024:
            raise ValueError("corpo grande demais")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("corpo não é JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("corpo deve ser um objeto JSON")
        return data

    def _authorized(self, data: dict) -> bool:
        # CORS não segura request com efeito colateral: um POST simples CHEGA
        # aqui mesmo com a resposta bloqueada pelo navegador. Quem protege a
        # gaveta é o token; a origem é a segunda tranca.
        token = str(data.get("token") or "")
        return hmac.compare_digest(token, self.config.token)

    # -- rotas ---------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        # Inerte no Chrome de hoje (medido: o preflight nem pede). É a linha que
        # nos poupa uma visita ao balcão se o PNA voltar a ser cobrado.
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/health":
            self._reply(404, {"ok": False, "error": "rota desconhecida"})
            return
        probe = probe_queue(self.config.queue)
        self._reply(200, {**probe, "queue": self.config.queue, "version": VERSION, "build": build_id()})

    def do_POST(self) -> None:  # noqa: N802
        rota = self.path.split("?")[0]
        if rota not in ("/kick", "/print"):
            self._reply(404, {"ok": False, "error": "rota desconhecida"})
            return
        origin = self._origin()
        if origin and not self.config.allows(origin):
            logger.warning("kick recusado: origem %s fora da allowlist", origin)
            self._reply(403, {"ok": False, "error": "origem não autorizada"})
            return
        try:
            data = self._read_json()
        except ValueError as exc:
            self._reply(400, {"ok": False, "error": str(exc)})
            return
        if not self._authorized(data):
            logger.warning("kick recusado: token inválido (origem %s)", origin or "-")
            self._reply(401, {"ok": False, "error": "token inválido"})
            return

        if rota == "/print":
            return self._do_print(data)

        pulse = data.get("pulse") or {}
        reason = str(data.get("reason") or "unspecified")[:60]
        try:
            payload = kick_bytes(
                pin=int(pulse.get("pin", 0)),
                on_ms=int(pulse.get("on_ms", 50)),
                off_ms=int(pulse.get("off_ms", 500)),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("kick recusado: pulso inválido (%s)", exc)
            self._reply(400, {"ok": False, "error": str(exc)})
            return

        try:
            job = send_raw(payload, queue=self.config.queue, title=f"gaveta:{reason}")
        except SpoolerError as exc:
            logger.error("kick FALHOU motivo=%s erro=%s", reason, exc)
            self._reply(502, {"ok": False, "error": str(exc), "queue": self.config.queue})
            return

        # A gaveta abrindo é evento de controle de caixa. O journald guarda a
        # verdade física do balcão; o servidor só sabe o que a tela mandou.
        logger.info("kick OK motivo=%s fila=%s job=%s", reason, self.config.queue, job or "-")
        self._reply(200, {"ok": True, "queue": self.config.queue, "job_id": job})

    def _do_print(self, data: dict) -> None:
        """Imprime bytes JÁ COMPOSTOS pelo servidor.

        O agente não sabe o que é sangria, nem leiaute, nem tabela de acento —
        ele é um cano. Quem compõe é o servidor, dono único do formato; se cada
        balcão compusesse, dois imprimiriam diferente e a DANFE (leiaute exigido
        por lei) teria de ser reimplementada em cada máquina.
        """
        import base64
        import binascii

        titulo = str(data.get("title") or "documento")[:60]
        try:
            payload = base64.b64decode(str(data.get("payload_b64") or ""), validate=True)
        except (binascii.Error, ValueError) as exc:
            logger.warning("impressao recusada: payload invalido (%s)", exc)
            self._reply(400, {"ok": False, "error": "payload_b64 inválido"})
            return
        if not payload:
            self._reply(400, {"ok": False, "error": "payload vazio"})
            return
        try:
            job = send_raw(payload, queue=self.config.queue, title=titulo)
        except SpoolerError as exc:
            logger.error("impressao FALHOU titulo=%s erro=%s", titulo, exc)
            self._reply(502, {"ok": False, "error": str(exc), "queue": self.config.queue})
            return
        logger.info("impressao OK titulo=%s bytes=%s job=%s", titulo, len(payload), job or "-")
        self._reply(200, {"ok": True, "queue": self.config.queue, "job_id": job})

    def log_message(self, fmt: str, *args) -> None:
        logger.debug(fmt, *args)


def serve(config: AgentConfig) -> None:
    handler = type("BoundDrawerHandler", (DrawerHandler,), {"config": config})
    httpd = ThreadingHTTPServer((config.host, config.port), handler)
    logger.info(
        "agente da gaveta ouvindo em http://%s:%s (fila=%s, origens=%s)",
        config.host,
        config.port,
        config.queue,
        ", ".join(config.allowed_origins) or "qualquer",
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("encerrando")
    finally:
        httpd.server_close()


# ── Instalação ────────────────────────────────────────────────────────────
#
# Mora AQUI, e não num script ao lado, porque um arquivo é o que uma pessoa
# consegue levar até o balcão por qualquer meio — pendrive, scp, ou colando num
# editor. Dois arquivos que precisam chegar juntos são uma chance a mais de
# chegar só um.

UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / "nelson-pos-drawer.service"
SERVICE_NAME = "nelson-pos-drawer.service"
LAUNCH_AGENT_LABEL = "com.nelson.pos-drawer"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
WINDOWS_TASK_NAME = "NelsonPosDrawer"

# Não existe default de origem, de propósito. A primeira versão cravava um
# domínio aqui e ele estava ERRADO — inventado, sem corresponder a nada no
# deployment. Uma constante inventada num arquivo que ninguém revisa vira 403 na
# gaveta, silencioso, no balcão. Quem sabe a origem é o Django
# (`SHOPMAN_POS_BASE_URL`), e o Admin já a coloca no comando de instalação.


def _unit_text(exec_path: Path) -> str:
    return f"""[Unit]
Description=Agente da gaveta de dinheiro do PDV (Nelson)
After=cups.service

[Service]
Type=simple
ExecStart=/usr/bin/env python3 {exec_path}
Restart=always
RestartSec=3
# O balcão abre cedo e ninguém vai olhar journal: se cair, sobe de novo.

[Install]
WantedBy=default.target
"""


def _plist_text(exec_path: Path) -> str:
    """LaunchAgent do macOS — o equivalente da unit do systemd.

    `KeepAlive` faz o papel do `Restart=always`: o balcão abre cedo e ninguém
    vai conferir se o agente continua de pé.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LAUNCH_AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>{exec_path}</string>
    <string>--log-file</string>
    <string>{LOG_PATH}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
"""


def list_queues() -> list[str]:
    """Nomes de fila que este sistema conhece."""
    if IS_WINDOWS:
        return _list_queues_windows()
    return _list_queues_cups()


def _list_queues_cups() -> list[str]:
    lpstat = shutil.which("lpstat")
    if not lpstat:
        return []
    try:
        completed = subprocess.run([lpstat, "-a"], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return []
    text = (completed.stdout or b"").decode("utf-8", "replace")
    return [line.split()[0] for line in text.splitlines() if line.strip()]


def _list_queues_windows() -> list[str]:
    """Impressoras instaladas, pelo mesmo winspool que manda o kick.

    Padrão de duas chamadas do EnumPrinters: a primeira só diz de quanta
    memória ele precisa, a segunda preenche.
    """
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

    class PRINTER_INFO_4(ctypes.Structure):
        _fields_ = [
            ("pPrinterName", wintypes.LPWSTR),
            ("pServerName", wintypes.LPWSTR),
            ("Attributes", wintypes.DWORD),
        ]

    flags = 0x00000002 | 0x00000004  # LOCAL | CONNECTIONS
    needed = wintypes.DWORD(0)
    returned = wintypes.DWORD(0)
    winspool.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(needed), ctypes.byref(returned))
    if not needed.value:
        return []
    buffer = ctypes.create_string_buffer(needed.value)
    if not winspool.EnumPrintersW(
        flags, None, 4, buffer, needed.value, ctypes.byref(needed), ctypes.byref(returned)
    ):
        return []
    entries = ctypes.cast(buffer, ctypes.POINTER(PRINTER_INFO_4))
    return [entries[i].pPrinterName for i in range(returned.value) if entries[i].pPrinterName]


def write_config(path: Path, *, queue: str, origin: str, token: str = "") -> tuple[dict, bool]:
    """Escreve a config, ou preserva a que já existe.

    ``token`` vem do Admin, que é quem tem o par. Sem ele o agente gera um e
    imprime na tela — caminho de emergência, para quem estiver no balcão sem
    acesso ao Admin.

    Reinstalar NÃO troca o token guardado, a não ser que venha um explícito: o
    PDV ficaria batendo com o velho e levando 401 até alguém acertar os dois
    lados — e ninguém quer descobrir isso no meio de um sábado.
    """
    if path.exists():
        config = json.loads(path.read_text(encoding="utf-8"))
        if token and token != config.get("token"):
            # Token novo veio do Admin (rotação): é a única razão para mexer.
            config["token"] = token
            path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            path.chmod(0o600)
            return config, True
        return config, False
    import secrets

    config = {
        "queue": queue,
        "token": token or secrets.token_urlsafe(32),
        "port": 47811,
        "host": "127.0.0.1",
        # Sem origem declarada a lista fica VAZIA, que o agente lê como
        # "qualquer origem". É mais frouxo, e o instalador avisa em voz alta —
        # melhor do que cravar um domínio chutado, que vira 403 calado.
        "allowed_origins": [origin.rstrip("/")] if origin else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return config, True


def _arg_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1] if flag in argv and len(argv) > argv.index(flag) + 1 else ""


def _autostart_linux(target: Path) -> None:
    if not shutil.which("systemctl"):
        print(f"aviso: sem systemctl. Suba na mão: python3 {target}")
        return
    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIT_PATH.write_text(_unit_text(target), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], check=False)
    # `restart`, não `enable --now`. O `--now` só SOBE o serviço parado: se já
    # estiver rodando, ele não faz nada — e reinstalar por cima trocava o
    # arquivo enquanto o processo velho seguia servindo o código velho. Foi
    # assim que o balcão baixou o agente novo, reinstalou, e continuou
    # respondendo "rota desconhecida" ao /print que só existe na versão nova.
    # Windows e macOS já reiniciavam de fato (`schtasks /run`, `bootout` +
    # `bootstrap`); só o Linux ficava com o processo antigo.
    subprocess.run(["systemctl", "--user", "restart", SERVICE_NAME], check=False)
    # Sem linger o agente só existe enquanto alguém estiver logado na sessão
    # gráfica — e morre no logout, que é exatamente quando ninguém percebe.
    user = os.environ.get("USER", "")
    linger = subprocess.run(["loginctl", "enable-linger", user], capture_output=True, check=False)
    if linger.returncode != 0:
        print(f"aviso: rode 'sudo loginctl enable-linger {user}'.")


def _autostart_macos(target: Path) -> None:
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT_PATH.write_text(_plist_text(target), encoding="utf-8")
    # `bootout` antes de `bootstrap`: recarregar por cima de um agente já
    # registrado é erro, e reinstalar tem que ser idempotente.
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LAUNCH_AGENT_LABEL}"], capture_output=True, check=False)
    loaded = subprocess.run(
        ["launchctl", "bootstrap", domain, str(LAUNCH_AGENT_PATH)], capture_output=True, check=False
    )
    if loaded.returncode != 0:
        # `bootstrap` é do launchd moderno; em macOS antigo só existe `load`.
        subprocess.run(["launchctl", "load", "-w", str(LAUNCH_AGENT_PATH)], capture_output=True, check=False)


def _windows_launcher(target: Path) -> Path:
    """Um `.cmd` que sobe o agente, para o `schtasks` receber UM caminho só.

    A primeira versão passava o comando inteiro em `/tr`, com três trechos entre
    aspas. O `schtasks` é notoriamente ruim com aspas aninhadas: ele aceita, e
    grava a tarefa com o comando mutilado. Resultado no balcão: a tarefa existe,
    o agente não sobe, e nada avisa — porque o `--kick` da linha de comando é
    outro processo e continua funcionando.

    Com o launcher, `/tr` recebe um caminho sem espaço para ambiguidade. De
    quebra, dá para dar dois cliques nele para subir o agente na mão.
    """
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    launcher = INSTALL_DIR / "nelson-pos-drawer.cmd"
    launcher.write_text(
        "@echo off\r\n"
        f'"{runner}" "{target}" --log-file "{LOG_PATH}"\r\n',
        encoding="utf-8",
    )
    return launcher


def _autostart_windows(target: Path) -> None:
    """Tarefa agendada no logon, apontando para o launcher.

    `pythonw` para o agente não abrir uma janela preta de console no balcão a
    cada boot. Sem privilégio de administrador: a tarefa é do usuário que está
    instalando.
    """
    launcher = _windows_launcher(target)
    created = subprocess.run(
        ["schtasks", "/create", "/f", "/tn", WINDOWS_TASK_NAME, "/tr", str(launcher), "/sc", "onlogon"],
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        detail = (created.stdout or b"").decode("utf-8", "replace").strip()
        print(f"aviso: não consegui agendar o início automático ({detail or 'schtasks falhou'}).")
        # Pasta Inicializar: não precisa de agendador nem de privilégio.
        startup = (
            Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        )
        try:
            startup.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(launcher, startup / launcher.name)
            print(f"       Coloquei na pasta Inicializar: {startup / launcher.name}")
        except OSError as exc:
            print(f"       Suba na mão quando precisar: {launcher} ({exc})")
        return
    subprocess.run(["schtasks", "/run", "/tn", WINDOWS_TASK_NAME], capture_output=True, check=False)


def install(argv: list[str]) -> int:
    if not IS_WINDOWS and not shutil.which("lp"):
        print("erro: comando 'lp' não encontrado — instale o CUPS.", file=sys.stderr)
        return 1

    rotulo = "impressoras instaladas" if IS_WINDOWS else "filas de impressão"
    queue = _arg_value(argv, "--queue")
    queues = list_queues()
    if not queue:
        if not queues:
            print(f"erro: nenhuma das {rotulo} encontrada. A impressora está instalada?", file=sys.stderr)
            return 1
        print(f"{rotulo.capitalize()}:")
        for name in queues:
            print(f"  - {name}")
        queue = input("Nome da impressora térmica: ").strip()
    if queue not in queues:
        print(f"erro: '{queue}' não está entre as {rotulo} deste computador.", file=sys.stderr)
        return 1

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    # Config de uma instalação anterior, quando o Windows guardava em pasta
    # separada. Mover em vez de gerar outra: duas configs na mesma máquina é
    # como o token do PDV e o do agente acabam diferentes sem ninguém entender.
    if IS_WINDOWS and _LEGACY_CONFIG_PATH.exists() and not DEFAULT_CONFIG_PATH.exists():
        shutil.move(str(_LEGACY_CONFIG_PATH), str(DEFAULT_CONFIG_PATH))
        print(f"config movida de {_LEGACY_CONFIG_PATH} para {DEFAULT_CONFIG_PATH}")

    target = INSTALL_DIR / "drawer_agent.py"
    source = Path(__file__).resolve()
    if source != target.resolve():
        shutil.copyfile(source, target)
    if not IS_WINDOWS:
        target.chmod(0o755)

    token = _arg_value(argv, "--token")
    origin = _arg_value(argv, "--origin")
    config, written = write_config(
        DEFAULT_CONFIG_PATH, queue=queue, origin=origin, token=token
    )

    if IS_WINDOWS:
        _autostart_windows(target)
    elif IS_MACOS:
        _autostart_macos(target)
    else:
        _autostart_linux(target)

    print(f"\nAgente instalado em {target}")
    print(f"Versao {VERSION} (build {build_id()}) — confira na tela do Admin se é a atual.")
    if not config.get("allowed_origins"):
        print(
            "\naviso: sem --origin, este agente aceita pedido de QUALQUER página\n"
            "       aberta neste navegador (o token continua obrigatório).\n"
            "       Pegue o comando completo no Admin: Terminais do PDV → gaveta."
        )
    if token:
        # Veio do Admin: o par já existe dos dois lados, nada a transcrever.
        print("Token recebido do Admin — nada a copiar de volta.")
    elif written:
        print("\n  ┌─ COLE ESTE TOKEN no Admin ─────────────────────────────────")
        print("  │  Admin → Terminais do PDV → gaveta → token")
        print("  │")
        print(f"  │  {config['token']}")
        print("  └─────────────────────────────────────────────────────────────")
    else:
        print(f"Config já existia em {DEFAULT_CONFIG_PATH} — token e fila preservados.")
    runner = "python" if IS_WINDOWS else "python3"
    print(f"\nTeste sem navegador:\n  {runner} \"{target}\" --kick")

    # ⚠️ Este bloco existe porque a versão anterior dizia "Agente instalado" sem
    # nunca ter conferido que o agente estava ouvindo. No Windows a tarefa
    # agendada nasceu quebrada, o serviço não subiu, e nada avisou: o `--kick`
    # da linha de comando é OUTRO processo e continuava funcionando, então o
    # defeito só apareceu no botão do PDV, depois, no balcão.
    #
    # Instalador que afirma o que não mediu é o mesmo pecado do health que
    # inventava `ready`. Agora ele bate na própria porta antes de dizer pronto.
    porta = config.get("port", 47811)
    saude = _wait_until_listening(config)

    if saude is None:
        print(
            f"\n✗ O agente NÃO está respondendo em http://127.0.0.1:{porta}/health.\n"
            "  O início automático não pegou. O kick pela linha de comando pode até\n"
            "  funcionar, mas o botão do PDV vai falhar até isto subir.\n"
            f"  Suba na mão para confirmar:  {runner} \"{target}\"\n"
            f"  E veja o motivo em:          {LOG_PATH}"
        )
        return 1

    # ⚠️ Responder não é ser. O bloco acima só sabia que ALGUÉM atende na porta —
    # e quem atendia era o processo ANTIGO, que nunca morreu e continuava segurando
    # o 47811. O instalador trocava o arquivo, dizia "pronto", e o balcão seguia com
    # a versão velha: o botão do PDV falhava com "rota desconhecida" e reinstalar
    # não adiantava, porque reinstalar era exatamente o que não estava pegando.
    #
    # A prova de identidade é o `build` (sha256 do próprio arquivo). Se o que atende
    # não for este arquivo, a instalação NÃO valeu — e dizer o contrário manda o
    # operador procurar defeito na impressora.
    esperado = build_id()
    rodando = str(saude.get("build") or "?")
    if rodando != esperado:
        print(
            f"\n✗ A instalação NÃO pegou: quem atende na porta {porta} é outra versão.\n"
            f"    versão que este arquivo instala: {esperado}\n"
            f"    versão que está no ar agora:     {rodando}\n\n"
            "  O processo antigo continua vivo e segurando a porta, então o novo\n"
            "  nem conseguiu subir. Enquanto isto durar, o PDV vai dizer que o\n"
            "  agente está desatualizado — e vai estar certo.\n\n"
            f"  Quem está na porta:  {_quem_ocupa_a_porta(porta)}\n"
            f"  Derrube e reinstale: {_comando_de_parada()}\n"
            f"                       {runner} \"{target}\" --install"
        )
        return 1

    print(f"\n✓ Agente {esperado} respondendo em http://127.0.0.1:{porta}/health")
    return 0


def _quem_ocupa_a_porta(porta: int) -> str:
    """PID que segura a porta, para o diagnóstico não parar em 'algo está lá'."""
    if os.name == "nt":
        return f'netstat -ano | findstr :{porta}'
    achado = subprocess.run(
        ["lsof", "-ti", f":{porta}"], capture_output=True, text=True, check=False
    )
    pids = achado.stdout.split()
    return f"PID {', '.join(pids)}" if pids else f"não identificado (tente: lsof -i :{porta})"


def _comando_de_parada() -> str:
    if sys.platform.startswith("linux"):
        return f"systemctl --user stop {SERVICE_NAME}"
    if sys.platform == "darwin":
        return f"launchctl bootout gui/$(id -u)/{LAUNCH_AGENT_LABEL}"
    if os.name == "nt":
        return f'schtasks /end /tn "{WINDOWS_TASK_NAME}"'
    return "encerre o processo acima"


def _wait_until_listening(config: dict, *, seconds: int = 10) -> dict | None:
    """Devolve o corpo do `/health`, ou ``None`` se ninguém atender a tempo.

    Devolve o CORPO, não um booleano, porque quem chama precisa saber **quem**
    atendeu — o `build` é a única prova de que o processo no ar é este arquivo.
    """
    import time
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{config.get('port', 47811)}/health"
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(0.5)
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    log_file = _arg_value(argv, "--log-file")
    handlers = None
    if log_file:
        # No Linux o journald captura o stdout; no macOS (launchd) e no Windows
        # (`pythonw`, sem console) ele iria para o nada. Um arquivo devolve a
        # trilha física das aberturas nos três sistemas.
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.FileHandler(log_file, encoding="utf-8")]
    logging.basicConfig(
        level=logging.DEBUG if "--verbose" in argv else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    if "--install" in argv:
        return install(argv)
    config = AgentConfig.load(DEFAULT_CONFIG_PATH)
    if "--kick" in argv:
        # Teste de bancada sem navegador: prova o caminho até o spooler.
        job = send_raw(kick_bytes(), queue=config.queue, title="gaveta:cli")
        print(f"kick enviado para {config.queue} (job {job or '-'})")
        return 0
    if "--test-print" in argv:
        # O papel responde o que ninguém sabe de cabeça: qual página de código
        # acerta os acentos, quantas colunas cabem, e se o QR é nativo.
        job = send_raw(test_print_bytes(), queue=config.queue, title="teste-impressao")
        print(f"página de teste enviada para {config.queue} (job {job or '-'})")
        print("Olhe o papel: 1) qual linha acentuada saiu certa  2) a régua coube  3) o QR apareceu")
        return 0
    serve(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
