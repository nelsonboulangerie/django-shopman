#!/usr/bin/env python3
"""Agente local do balcão: a ponte do navegador com o hardware do caixa.

O PDV roda no navegador e o navegador não fala ESC/POS. A gaveta não tem cabo
próprio: ela pendura no RJ11 da impressora e abre quando a impressora recebe
``ESC p m t1 t2``. Como a TM-T20 é USB e o driver do sistema já é dono da
interface (é assim que o ``window.print()`` do recibo funciona), não há WebUSB
possível — brigar pela interface quebraria a impressão.

Sobra este caminho: um processo local que recebe um pedido do navegador em
``127.0.0.1`` e entrega bytes crus ao **spooler**, pela mesma fila por onde o
recibo já sai. É o mesmo cano para a gaveta (``/kick``) e para o papel
(``/print``) — comprovante de movimento de caixa hoje, DANFE NFC-e depois, que é
obrigação legal. Por isso ele é do BALCÃO e não da gaveta: a gaveta é um dos
aparelhos que ele alcança, não o escopo dele.

Zero dependências: é um processo que precisa subir junto com o balcão, todo dia,
sem ninguém olhando. ``pip install`` é uma coisa a mais para quebrar às 6h.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.1.0"


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
#: `%LOCALAPPDATA%\NelsonPosCounter` e a config para uma pasta `.config` de estilo
#: Linux, escondida na pasta do usuário. Quem estivesse no balcão procurando o
#: token não acharia. Um lugar, uma resposta.
def install_dir_for(home: Path, *, windows: bool, localappdata: str = "") -> Path:
    if windows:
        return Path(localappdata or home / "AppData" / "Local") / "NelsonPosCounter"
    return home / ".local" / "share" / "nelson-pos-counter"


def config_path_for(home: Path, *, windows: bool, localappdata: str = "") -> Path:
    """Onde a config mora, por sistema.

    No Windows, junto do programa. No Linux/macOS, em ``~/.config`` — que é onde
    quem administra a máquina espera achar.
    """
    if windows:
        return install_dir_for(home, windows=True, localappdata=localappdata) / "agent.json"
    return home / ".config" / "nelson-pos-counter" / "agent.json"


INSTALL_DIR = install_dir_for(
    Path.home(), windows=IS_WINDOWS, localappdata=os.environ.get("LOCALAPPDATA", "")
)


def legacy_config_paths(home: Path, *, windows: bool, localappdata: str = "") -> tuple[Path, ...]:
    """Onde a config já morou antes de o agente ser do balcão. Mais nova primeiro.

    O agente nasceu chutando só a gaveta e se chamava por isso. As máquinas que
    já rodam o antigo têm o ``agent.json`` gravado com o nome velho, e o token
    dele é metade de um par que o Admin guarda: gerar outro em vez de mover
    deixaria os dois lados diferentes, e o balcão passaria a levar 401 no meio
    do troco. No Windows são dois caminhos porque houve uma migração anterior —
    o programa foi para o ``%LOCALAPPDATA%`` e a config ficou na pasta
    ``.config`` de estilo Linux.
    """
    antigas = [home / ".config" / "nelson-pos-drawer" / "agent.json"]
    if windows:
        local = Path(localappdata or home / "AppData" / "Local")
        antigas.insert(0, local / "NelsonPosDrawer" / "agent.json")
    return tuple(antigas)


LEGACY_CONFIG_PATHS = legacy_config_paths(
    Path.home(), windows=IS_WINDOWS, localappdata=os.environ.get("LOCALAPPDATA", "")
)
DEFAULT_CONFIG_PATH = Path(os.environ.get("COUNTER_AGENT_CONFIG") or "") if os.environ.get(
    "COUNTER_AGENT_CONFIG"
) else config_path_for(Path.home(), windows=IS_WINDOWS, localappdata=os.environ.get("LOCALAPPDATA", ""))

LOG_PATH = INSTALL_DIR / "counter-agent.log"
JOURNAL_PATH = INSTALL_DIR / "print-relay.sqlite3"

MAX_PRINT_PAYLOAD_BYTES = 512 * 1024
MAX_HTTP_BODY_BYTES = 768 * 1024
MAX_RELAY_RESPONSE_BYTES = 768 * 1024
RELAY_CLAIM_PATH = "/api/v1/backstage/print-agent/jobs/claim/"
RELAY_ACK_PATH = "/api/v1/backstage/print-agent/jobs/{job_ref}/ack/"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_IDENTITY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:"
)

logger = logging.getLogger("counter-agent")

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
    out += _line("Agente do balcão - Nelson")
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
    server_url: str = ""
    station_ref: str = ""
    agent_id: str = ""
    relay_token: str = ""
    relay_poll_seconds: float = 2.0
    #: Como ESTA gaveta reporta o estado. `None` = ainda não medido, e aí o
    #: agente responde "não sei" em vez de chutar.
    #:
    #: ⚠️ A polaridade NÃO é constante entre montagens. No balcão da Nelson
    #: medimos fechada=0x16 (bit ligado) e aberta=0x12 (bit desligado) — o
    #: INVERSO do que a leitura ingênua do manual sugere. Cravar isso em
    #: constante faria o alerta gritar o dia todo com a gaveta fechada e ficar
    #: mudo quando ela ficasse aberta de verdade: pior que não ter alerta.
    drawer_status: dict | None = None

    @classmethod
    def load(cls, path: Path) -> AgentConfig:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SystemExit(
                f"config não encontrada em {path}.\n"
                "Rode 'python3 counter_agent.py --install' ou aponte COUNTER_AGENT_CONFIG para o arquivo."
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
        normalized_origins = []
        for candidate in origins:
            origin = str(candidate).strip().rstrip("/")
            parsed_origin = urllib.parse.urlparse(origin)
            if (
                not origin
                or parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.username
                or parsed_origin.password
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise SystemExit(f"origem inválida em 'allowed_origins': {origin!r}.")
            normalized_origins.append(origin)
        host = str(raw.get("host") or "127.0.0.1").strip().lower()
        if host not in _LOOPBACK_HOSTS:
            raise SystemExit(
                "config 'host' deve ser loopback: 127.0.0.1, ::1 ou localhost."
            )

        server_url = str(raw.get("server_url") or "").strip().rstrip("/")
        station_ref = str(raw.get("station_ref") or "").strip()
        agent_id = str(raw.get("agent_id") or "").strip()
        relay_token = str(raw.get("relay_token") or "").strip()
        relay_values = (server_url, station_ref, agent_id, relay_token)
        if any(relay_values) and not all(relay_values):
            raise SystemExit(
                "relay incompleto: informe server_url, station_ref, agent_id e relay_token."
            )
        if server_url:
            parsed = urllib.parse.urlparse(server_url)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise SystemExit("'server_url' do relay deve ser uma URL HTTPS sem credenciais.")
            if len(relay_token) < 16:
                raise SystemExit("'relay_token' deve ter no mínimo 16 caracteres.")
            if len(station_ref) > 80 or len(agent_id) > 120:
                raise SystemExit("station_ref/agent_id longos demais.")
            if any(c not in _IDENTITY_CHARS for c in station_ref + agent_id):
                raise SystemExit("station_ref/agent_id contêm caracteres inválidos.")
        try:
            relay_poll_seconds = float(raw.get("relay_poll_seconds") or 2.0)
        except (TypeError, ValueError) as exc:
            raise SystemExit("'relay_poll_seconds' deve ser numérico.") from exc
        if not 0.25 <= relay_poll_seconds <= 60:
            raise SystemExit("'relay_poll_seconds' deve estar entre 0.25 e 60 segundos.")
        return cls(
            queue=queue,
            token=token,
            port=int(raw.get("port") or 47811),
            host=host,
            allowed_origins=tuple(normalized_origins),
            server_url=server_url,
            station_ref=station_ref,
            agent_id=agent_id,
            relay_token=relay_token,
            relay_poll_seconds=relay_poll_seconds,
            drawer_status=raw.get("drawer_status") or None,
        )

    @property
    def relay_enabled(self) -> bool:
        return bool(self.server_url)

    def estado_da_gaveta(self, byte: int) -> bool | None:
        """True = aberta. `None` = esta maquina nunca mediu, entao nao sabemos.

        Devolver `None` em vez de um palpite e o ponto: alerta de gaveta aberta
        que erra a polaridade grita o dia inteiro com a gaveta fechada, e a
        pessoa aprende a ignorar - matando junto o aviso legitimo.
        """
        cfg = self.drawer_status or {}
        mascara, fechada = cfg.get("mask"), cfg.get("closed_value")
        if mascara is None or fechada is None:
            return None
        return (byte & int(mascara)) != int(fechada)

    def allows(self, origin: str) -> bool:
        # Processos locais sem cabeçalho Origin continuam podendo usar a API
        # com o token. Já uma aba do navegador só ganha efeitos se sua origem
        # estiver explicitamente cadastrada: lista vazia nunca significa
        # "qualquer site".
        if not origin:
            return True
        if not self.allowed_origins:
            return False
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


class SpoolerUncertainError(SpoolerError):
    """O agente não sabe se o spooler aceitou antes de a chamada falhar."""


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
        # O processo pode ter sido aceito pelo CUPS antes do timeout. Repetir
        # automaticamente aqui pode imprimir duas etiquetas.
        raise SpoolerUncertainError(f"fila '{queue}' não respondeu em 10s") from exc
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
    # As de HANDLE puro funcionam hoje por acaso: recebem um objeto ctypes, nao
    # um int cru. Declaradas mesmo assim - a hora em que alguem passar um int
    # (foi o que quebrou a leitura da gaveta) e a hora em que ninguem lembra
    # desta distincao.
    winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.StartPagePrinter.restype = wintypes.BOOL
    winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.EndPagePrinter.restype = wintypes.BOOL
    winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    winspool.EndDocPrinter.restype = wintypes.BOOL
    winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    winspool.ClosePrinter.restype = wintypes.BOOL
    winspool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
    winspool.WritePrinter.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]

    def _fail(step: str, *, uncertain: bool = False) -> SpoolerError:
        error = SpoolerUncertainError if uncertain else SpoolerError
        return error(f"{step} falhou (erro {ctypes.get_last_error()}) na fila '{queue}'")

    handle = wintypes.HANDLE()
    if not winspool.OpenPrinterW(queue, ctypes.byref(handle), None):
        raise _fail("abrir a impressora")
    try:
        job = winspool.StartDocPrinterW(handle, 1, ctypes.byref(DOC_INFO_1(title, None, "RAW")))
        if not job:
            raise _fail("iniciar o trabalho")
        page_started = False
        try:
            if not winspool.StartPagePrinter(handle):
                raise _fail("iniciar a página", uncertain=True)
            page_started = True
            written = wintypes.DWORD(0)
            # Comprimento explícito: `create_string_buffer(payload)` sozinho
            # acrescenta um NUL no fim, e um sexto byte indo para a impressora
            # não é o que o manual manda.
            buffer = ctypes.create_string_buffer(payload, len(payload))
            if not winspool.WritePrinter(handle, buffer, len(payload), ctypes.byref(written)):
                raise _fail("escrever na impressora", uncertain=True)
            if written.value != len(payload):
                raise SpoolerUncertainError(
                    f"spooler aceitou {written.value} de {len(payload)} bytes"
                )
            if not winspool.EndPagePrinter(handle):
                raise _fail("encerrar a página", uncertain=True)
            page_started = False
        except BaseException:
            if page_started:
                winspool.EndPagePrinter(handle)
            winspool.EndDocPrinter(handle)
            raise
        if not winspool.EndDocPrinter(handle):
            raise _fail("encerrar o trabalho", uncertain=True)
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
    # As de HANDLE puro funcionam hoje por acaso: recebem um objeto ctypes, nao
    # um int cru. Declaradas mesmo assim - a hora em que alguem passar um int
    # (foi o que quebrou a leitura da gaveta) e a hora em que ninguem lembra
    # desta distincao.
    winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.StartPagePrinter.restype = wintypes.BOOL
    winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.EndPagePrinter.restype = wintypes.BOOL
    winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    winspool.EndDocPrinter.restype = wintypes.BOOL
    winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    winspool.ClosePrinter.restype = wintypes.BOOL
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


# ── Relay HTTPS de saída ──────────────────────────────────────────────────


class RelayError(RuntimeError):
    """Falha segura do protocolo do relay (nunca inclui token nem payload)."""


class RelayTransportError(RelayError):
    pass


class _NoRelayRedirect(urllib.request.HTTPRedirectHandler):
    """Não deixa um 30x encaminhar o Bearer para outro host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RelayInvalidJob(RelayError):
    def __init__(
        self,
        message: str,
        *,
        job_ref: str = "",
        payload_sha256: str = "",
        lease_token: str = "",
        attempt: int = 0,
    ) -> None:
        super().__init__(message)
        self.job_ref = job_ref
        self.payload_sha256 = payload_sha256
        self.lease_token = lease_token
        self.attempt = attempt


@dataclass(frozen=True)
class RelayJob:
    job_ref: str
    attempt: int
    title: str
    payload: bytes
    payload_sha256: str
    lease_token: str
    content_sha256: str = ""

    @classmethod
    def from_claim(cls, raw: dict) -> RelayJob:
        if not isinstance(raw, dict):
            raise RelayInvalidJob("claim não devolveu um objeto JSON")
        job_ref = str(raw.get("job_ref") or "").strip()
        payload_sha256 = str(raw.get("payload_sha256") or "").strip().lower()
        lease_token = str(raw.get("lease_token") or "").strip()
        if (
            not job_ref
            or len(job_ref) > 200
            or any(c not in _IDENTITY_CHARS for c in job_ref)
        ):
            raise RelayInvalidJob("job_ref ausente ou inválido")
        if not 20 <= len(lease_token) <= 128:
            raise RelayInvalidJob("lease_token ausente ou inválido", job_ref=job_ref)
        if len(payload_sha256) != 64 or any(c not in "0123456789abcdef" for c in payload_sha256):
            raise RelayInvalidJob(
                "payload_sha256 ausente ou inválido",
                job_ref=job_ref,
                lease_token=lease_token,
            )
        try:
            attempt = int(raw.get("attempt"))
        except (TypeError, ValueError) as exc:
            raise RelayInvalidJob(
                "attempt ausente ou inválido",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
            ) from exc
        if attempt < 1:
            raise RelayInvalidJob(
                "attempt ausente ou inválido",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
            )
        # `payload_b64` é o contrato canônico. `content_base64` é aceito só
        # para uma implantação gradual de servidores que usaram esse nome na
        # primeira revisão do endpoint.
        encoded = raw.get("payload_b64")
        if encoded is None:
            encoded = raw.get("content_base64")
        if not isinstance(encoded, str) or not encoded:
            raise RelayInvalidJob(
                "payload_b64 ausente",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            )
        # Recusa antes de decodificar uma representação que jamais caberia no
        # teto RAW. O pequeno excesso cobre padding e quebras rejeitadas pelo
        # validate=True.
        max_b64 = ((MAX_PRINT_PAYLOAD_BYTES + 2) // 3) * 4
        if len(encoded) > max_b64:
            raise RelayInvalidJob(
                "payload excede 512 KiB",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            )
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RelayInvalidJob(
                "payload_b64 inválido",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            ) from exc
        if not payload:
            raise RelayInvalidJob(
                "payload vazio",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            )
        if len(payload) > MAX_PRINT_PAYLOAD_BYTES:
            raise RelayInvalidJob(
                "payload excede 512 KiB",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            )
        declared_size = raw.get("payload_size")
        if declared_size is not None:
            try:
                declared_size = int(declared_size)
            except (TypeError, ValueError) as exc:
                raise RelayInvalidJob(
                    "payload_size inválido",
                    job_ref=job_ref,
                    payload_sha256=payload_sha256,
                    lease_token=lease_token,
                    attempt=attempt,
                ) from exc
            if declared_size != len(payload):
                raise RelayInvalidJob(
                    "payload_size não confere",
                    job_ref=job_ref,
                    payload_sha256=payload_sha256,
                    lease_token=lease_token,
                    attempt=attempt,
                )
        actual = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual, payload_sha256):
            raise RelayInvalidJob(
                "payload_sha256 não confere",
                job_ref=job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            )
        return cls(
            job_ref=job_ref,
            attempt=attempt,
            title=" ".join(
                str(raw.get("title") or raw.get("kind") or "documento").split()
            )[:60],
            payload=payload,
            payload_sha256=payload_sha256,
            lease_token=lease_token,
            content_sha256=str(raw.get("content_sha256") or "")[:128],
        )


@dataclass(frozen=True)
class RelayJournalEntry:
    job_ref: str
    payload_sha256: str
    lease_token: str
    attempt: int
    state: str
    spooler_job_id: str
    detail: str
    acknowledged: int


class RelayJournal:
    """Journal mínimo: sem payload/credencial permanente; lease local em 0600."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()
        self.recover_incomplete()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _setup(self) -> None:
        with self._connect() as db:
            # O journal contém o lease bruto necessário para refazer ACK depois
            # de restart. DELETE evita um arquivo `-wal` lateral com permissão
            # própria; o banco principal é 0600.
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA secure_delete=ON")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS print_jobs (
                    job_ref TEXT PRIMARY KEY,
                    payload_sha256 TEXT NOT NULL,
                    lease_token TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    spooler_job_id TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            # Upgrade defensivo para qualquer banco criado por uma revisão de
            # desenvolvimento anterior a ACK persistente.
            columns = {
                str(row[1]) for row in db.execute("PRAGMA table_info(print_jobs)").fetchall()
            }
            if "lease_token" not in columns:
                db.execute(
                    "ALTER TABLE print_jobs ADD COLUMN lease_token TEXT NOT NULL DEFAULT ''"
                )
            if "acknowledged" not in columns:
                db.execute(
                    "ALTER TABLE print_jobs ADD COLUMN acknowledged INTEGER NOT NULL DEFAULT 0"
                )
            if "attempt" not in columns:
                db.execute(
                    "ALTER TABLE print_jobs ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0"
                )
        try:
            self.path.chmod(0o600)
        except OSError:
            logger.warning("não foi possível restringir permissões de %s", self.path, exc_info=True)

    def recover_incomplete(self) -> int:
        """Converte resíduos de processo morto em ACKs terminais seguros."""
        now = time.time()
        with self._connect() as db:
            spooling = db.execute(
                """
                UPDATE print_jobs
                   SET state = 'uncertain',
                       detail = 'agente reiniciou durante envio ao spooler',
                       acknowledged = 0,
                       updated_at = ?
                 WHERE state = 'spooling'
                """,
                (now,),
            )
            # `claimed` foi persistido antes de `spooling`: aqui temos certeza
            # de que o spooler ainda não foi chamado, portanto é falha (não
            # incerteza) e o servidor pode propor nova tentativa auditada.
            claimed = db.execute(
                """
                UPDATE print_jobs
                   SET state = 'failed',
                       detail = 'agente reiniciou antes de chamar o spooler',
                       acknowledged = 0,
                       updated_at = ?
                 WHERE state = 'claimed'
                """,
                (now,),
            )
            return spooling.rowcount + claimed.rowcount

    def get(self, job_ref: str) -> RelayJournalEntry | None:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT job_ref, payload_sha256, lease_token, attempt, state,
                       spooler_job_id, detail, acknowledged
                  FROM print_jobs WHERE job_ref = ?
                """,
                (job_ref,),
            ).fetchone()
        if row is None:
            return None
        return RelayJournalEntry(**dict(row))

    def _same_or_rotate_attempt(
        self,
        entry: RelayJournalEntry,
        *,
        payload_sha256: str,
        lease_token: str,
        attempt: int,
        target_state: str,
        detail: str = "",
    ) -> RelayJournalEntry:
        """Aceita redelivery igual ou retry seguro depois de falha ACKed."""
        if not hmac.compare_digest(entry.payload_sha256, payload_sha256):
            raise RelayInvalidJob(
                "job_ref reapareceu com outro payload_sha256",
                job_ref=entry.job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            )
        if hmac.compare_digest(entry.lease_token, lease_token):
            if entry.attempt != attempt:
                raise RelayInvalidJob(
                    "mesmo lease reapareceu com outro attempt",
                    job_ref=entry.job_ref,
                    payload_sha256=payload_sha256,
                    lease_token=lease_token,
                    attempt=attempt,
                )
            return entry

        # O backend reutiliza o PrintJob/ref em retry de falha comprovada. Só
        # essa combinação prova que o papel anterior NÃO foi aceito e que o ACK
        # respectivo chegou. Submitted/uncertain/ACK pendente ficam fechados.
        if not (
            entry.state == "failed"
            and entry.acknowledged == 1
            and attempt > entry.attempt
        ):
            raise RelayInvalidJob(
                "novo lease recusado: ocorrência anterior não é failed ACKed",
                job_ref=entry.job_ref,
                payload_sha256=payload_sha256,
                lease_token=lease_token,
                attempt=attempt,
            )
        safe_detail = " ".join(str(detail).split())[:240]
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE print_jobs
                   SET lease_token = ?, attempt = ?, state = ?,
                       spooler_job_id = '', detail = ?, acknowledged = 0,
                       updated_at = ?
                 WHERE job_ref = ? AND payload_sha256 = ?
                   AND lease_token = ? AND attempt = ?
                   AND state = 'failed' AND acknowledged = 1
                """,
                (
                    lease_token,
                    attempt,
                    target_state,
                    safe_detail,
                    time.time(),
                    entry.job_ref,
                    payload_sha256,
                    entry.lease_token,
                    entry.attempt,
                ),
            )
            if cursor.rowcount != 1:
                raise RelayError("retry concorreu com outra transição do journal")
        rotated = self.get(entry.job_ref)
        assert rotated is not None
        return rotated

    def record_claimed(self, job: RelayJob) -> RelayJournalEntry:
        now = time.time()
        with self._connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO print_jobs
                    (job_ref, payload_sha256, lease_token, attempt, state,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, 'claimed', ?, ?)
                """,
                (
                    job.job_ref,
                    job.payload_sha256,
                    job.lease_token,
                    job.attempt,
                    now,
                    now,
                ),
            )
        entry = self.get(job.job_ref)
        assert entry is not None
        return self._same_or_rotate_attempt(
            entry,
            payload_sha256=job.payload_sha256,
            lease_token=job.lease_token,
            attempt=job.attempt,
            target_state="claimed",
        )

    def record_rejected(
        self,
        *,
        job_ref: str,
        payload_sha256: str,
        lease_token: str,
        attempt: int,
        detail: str,
    ) -> RelayJournalEntry:
        now = time.time()
        safe_detail = " ".join(str(detail).split())[:240]
        with self._connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO print_jobs
                    (job_ref, payload_sha256, lease_token, attempt, state, detail,
                     acknowledged, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'failed', ?, 0, ?, ?)
                """,
                (
                    job_ref,
                    payload_sha256,
                    lease_token,
                    attempt,
                    safe_detail,
                    now,
                    now,
                ),
            )
        entry = self.get(job_ref)
        assert entry is not None
        return self._same_or_rotate_attempt(
            entry,
            payload_sha256=payload_sha256,
            lease_token=lease_token,
            attempt=attempt,
            target_state="failed",
            detail=safe_detail,
        )

    def begin_spooling(self, job_ref: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE print_jobs SET state = 'spooling', updated_at = ?
                 WHERE job_ref = ? AND state = 'claimed'
                """,
                (time.time(), job_ref),
            )
            return cursor.rowcount == 1

    def set_result(
        self,
        job_ref: str,
        state: str,
        *,
        spooler_job_id: str = "",
        detail: str = "",
    ) -> None:
        if state not in {"submitted_to_spooler", "failed", "uncertain"}:
            raise ValueError(f"estado inválido do journal: {state}")
        safe_detail = " ".join(str(detail).split())[:240]
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE print_jobs
                 SET state = ?, spooler_job_id = ?, detail = ?,
                       acknowledged = 0, updated_at = ?
                 WHERE job_ref = ? AND state = 'spooling'
                """,
                (state, str(spooler_job_id)[:160], safe_detail, time.time(), job_ref),
            )
            if cursor.rowcount != 1:
                raise RelayError("resultado perdeu a posse do estado spooling")

    def pending_acknowledgements(self) -> list[RelayJournalEntry]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT job_ref, payload_sha256, lease_token, attempt, state,
                       spooler_job_id, detail, acknowledged
                  FROM print_jobs
                 WHERE acknowledged = 0
                   AND lease_token != ''
                   AND state IN ('submitted_to_spooler', 'failed', 'uncertain')
                 ORDER BY updated_at, job_ref
                """
            ).fetchall()
        return [RelayJournalEntry(**dict(row)) for row in rows]

    def mark_acknowledged(self, job_ref: str) -> None:
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE print_jobs SET acknowledged = 1, updated_at = ?
                 WHERE job_ref = ?
                """,
                (time.time(), job_ref),
            )
            if cursor.rowcount != 1:
                raise RelayError("ACK refere job ausente do journal")

    def counts(self) -> dict[str, int]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT state, COUNT(*) AS amount FROM print_jobs GROUP BY state"
            ).fetchall()
        return {str(row["state"]): int(row["amount"]) for row in rows}


def _relay_http_post(
    config: AgentConfig,
    path: str,
    payload: dict,
    *,
    timeout: float = 10.0,
) -> tuple[int, dict | None]:
    """POST autenticado; mensagens de erro nunca ecoam corpo ou credencial."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        config.server_url + path,
        data=body,
        headers={
            "Authorization": f"Bearer {config.relay_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"nelson-counter-agent/{VERSION} ({build_id()})",
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRelayRedirect())
        with opener.open(request, timeout=timeout) as response:
            response_status = getattr(response, "status", None)
            status = int(response_status if response_status is not None else response.getcode())
            if status == 204:
                return status, None
            raw = response.read(MAX_RELAY_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RelayTransportError(f"servidor respondeu HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RelayTransportError("não foi possível alcançar o servidor do relay") from exc
    if len(raw) > MAX_RELAY_RESPONSE_BYTES:
        raise RelayTransportError("resposta do relay grande demais")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayTransportError("resposta do relay não é JSON") from exc
    if not isinstance(decoded, dict):
        raise RelayTransportError("resposta do relay não é um objeto")
    return status, decoded


class RelayWorker:
    def __init__(
        self,
        config: AgentConfig,
        *,
        journal: RelayJournal,
        post=_relay_http_post,
        spool=send_raw,
    ) -> None:
        if not config.relay_enabled:
            raise ValueError("relay não configurado")
        self.config = config
        self.journal = journal
        self.post = post
        self.spool = spool
        self.health = "unknown"
        self._next_health_probe = 0.0

    def _metadata(self) -> dict:
        return {
            # O servidor autentica/deriva a identidade da credencial. Estes
            # campos são apenas diagnóstico e nunca fonte de autorização.
            "station_ref": self.config.station_ref,
            "agent_id": self.config.agent_id,
            "version": VERSION,
            "build": build_id(),
            "queue": self.config.queue[:160],
            "health": self.health,
        }

    def _ack(
        self,
        *,
        job_ref: str,
        lease_token: str,
        payload_sha256: str,
        status: str,
        spooler_job_id: str = "",
        detail: str = "",
    ) -> None:
        if status not in {"spooled", "failed", "uncertain"}:
            raise ValueError(f"status inválido: {status}")
        ack = {
            **self._metadata(),
            "lease_token": lease_token,
            "payload_sha256": payload_sha256,
            "status": status,
            "spooler_job_id": str(spooler_job_id)[:160],
            "detail": " ".join(str(detail).split())[:240],
        }
        path = RELAY_ACK_PATH.format(job_ref=urllib.parse.quote(job_ref, safe=""))
        status, _ = self.post(self.config, path, ack)
        if status < 200 or status >= 300:
            raise RelayTransportError(f"ACK recebeu HTTP {status}")

    @staticmethod
    def _ack_status(entry: RelayJournalEntry) -> str:
        return "spooled" if entry.state == "submitted_to_spooler" else entry.state

    def _ack_entry(self, entry: RelayJournalEntry) -> None:
        self._ack(
            job_ref=entry.job_ref,
            lease_token=entry.lease_token,
            payload_sha256=entry.payload_sha256,
            status=self._ack_status(entry),
            spooler_job_id=entry.spooler_job_id,
            detail=entry.detail,
        )
        # Se cair depois de o servidor aceitar e antes desta escrita, o próximo
        # boot manda o mesmo ACK; o digest do backend torna isso idempotente.
        self.journal.mark_acknowledged(entry.job_ref)

    def poll_once(self) -> bool:
        pending = self.journal.pending_acknowledgements()
        if pending:
            # Confirmações duráveis vêm antes de trabalho novo. Assim ACK
            # perdido/restart não dependem de o servidor reemitir o lease bruto.
            for entry in pending:
                self._ack_entry(entry)
            return True

        now = time.monotonic()
        if now >= self._next_health_probe:
            probe = probe_queue(self.config.queue)
            self.health = "ready" if probe.get("ok") else "unavailable"
            self._next_health_probe = now + 30.0
        claim = self._metadata()
        status, response = self.post(self.config, RELAY_CLAIM_PATH, claim)
        if status == 204 or response is None:
            return False
        if status != 200:
            raise RelayTransportError(f"claim recebeu HTTP {status}")
        if "job" in response:
            if response["job"] is None:
                return False
            raw_job = response["job"]
        else:
            raw_job = response
        try:
            job = RelayJob.from_claim(raw_job)
        except RelayInvalidJob as exc:
            # Só é possível encerrar um poison job quando há os três vínculos
            # íntegros exigidos pelo ACK; sem eles, não inventamos identidade.
            if exc.job_ref and exc.payload_sha256 and exc.lease_token and exc.attempt:
                rejected = self.journal.record_rejected(
                    job_ref=exc.job_ref,
                    payload_sha256=exc.payload_sha256,
                    lease_token=exc.lease_token,
                    attempt=exc.attempt,
                    detail=str(exc),
                )
                self._ack_entry(rejected)
                return True
            raise

        entry = self.journal.record_claimed(job)
        if entry.state in {"submitted_to_spooler", "failed", "uncertain"}:
            # ACK perdido/redelivery: repete somente o ACK, nunca o papel.
            self._ack_entry(entry)
            return True
        if entry.state == "spooling":
            self.journal.set_result(
                job.job_ref,
                "uncertain",
                detail="entrega anterior ficou interrompida durante o spool",
            )
            uncertain = self.journal.get(job.job_ref)
            assert uncertain is not None
            self._ack_entry(uncertain)
            return True
        if entry.state != "claimed" or not self.journal.begin_spooling(job.job_ref):
            latest = self.journal.get(job.job_ref)
            if latest and latest.state in {"submitted_to_spooler", "failed", "uncertain"}:
                self._ack_entry(latest)
                return True
            raise RelayError("transição concorrente inesperada no journal")

        # O estado `spooling` está em disco ANTES de tocar no spooler. Se o
        # processo morrer daqui em diante, o próximo boot converte para
        # `uncertain` e jamais reimprime automaticamente.
        try:
            spooler_job_id = self.spool(job.payload, queue=self.config.queue, title=job.title)
        except SpoolerUncertainError as exc:
            self.journal.set_result(job.job_ref, "uncertain", detail=str(exc))
        except SpoolerError as exc:
            self.journal.set_result(job.job_ref, "failed", detail=str(exc))
        else:
            self.journal.set_result(
                job.job_ref,
                "submitted_to_spooler",
                # CUPS/Windows confirmaram aceitação mesmo se sua saída não
                # trouxe um identificador analisável. O backend exige um valor
                # para distinguir ACK spooled de confirmação vazia.
                spooler_job_id=spooler_job_id or "accepted-no-id",
            )
        final = self.journal.get(job.job_ref)
        assert final is not None
        self._ack_entry(final)
        return True

    def run(self, stop: threading.Event) -> None:
        backoff = 1.0
        while not stop.is_set():
            try:
                processed = self.poll_once()
            except (RelayError, OSError, sqlite3.Error, ValueError) as exc:
                logger.warning("relay indisponível: %s", exc)
                stop.wait(backoff)
                backoff = min(backoff * 2, 60.0)
                continue
            backoff = 1.0
            stop.wait(0.25 if processed else self.config.relay_poll_seconds)


def _relay_thread_main(
    config: AgentConfig,
    stop: threading.Event,
    *,
    journal_path: Path | None = None,
) -> None:
    """Inicializa/reabre o journal sem deixar uma falha derrubar a loopback."""
    backoff = 1.0
    path = JOURNAL_PATH if journal_path is None else journal_path
    while not stop.is_set():
        try:
            journal = RelayJournal(path)
        except (OSError, sqlite3.Error) as exc:
            logger.error("relay sem journal disponível: %s", exc)
            stop.wait(backoff)
            backoff = min(backoff * 2, 60.0)
            continue
        RelayWorker(config, journal=journal).run(stop)
        return


# ── HTTP ──────────────────────────────────────────────────────────────────


class CounterAgentHandler(BaseHTTPRequestHandler):
    server_version = f"nelson-counter-agent/{VERSION}"
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
        if length > MAX_HTTP_BODY_BYTES:
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
        rota = self.path.split("?")[0]
        if rota == "/drawer":
            return self._reply(200, self._estado_da_gaveta())
        if rota != "/health":
            self._reply(404, {"ok": False, "error": "rota desconhecida"})
            return
        probe = probe_queue(self.config.queue)
        self._reply(
            200,
            {
                **probe,
                "queue": self.config.queue,
                "version": VERSION,
                "build": build_id(),
                # As pontas do token QUE ESTE PROCESSO ESTÁ USANDO.
                #
                # ⚠️ É a única forma de saber isso. O `build` é o sha256 do
                # `.py`, e reinstalar por cima troca o `agent.json` SEM tocar no
                # `.py` — então o build continua idêntico enquanto o processo
                # vivo segue com o token velho carregado na memória. O
                # `--doctor` lia o token do ARQUIVO e dizia "tudo certo"; quem
                # responde ao navegador é este processo, e ninguém perguntava a
                # ele. O PDV levava 401 "token inválido" sem nenhum diagnóstico
                # capaz de apontar por quê.
                #
                # Só as pontas, e o endpoint é loopback: 8 de 43 caracteres não
                # permitem forjar nada, e sem isto não há como comparar.
                "token_hint": _mascarar(self.config.token),
                # A trava da gaveta esta ARMADA nesta estacao? Só o agente sabe:
                # a medicao vive no `agent.json` do balcao, e o Django nunca
                # alcanca a loopback. Sem esta linha, "a trava esta ligada?" so
                # tinha resposta indo ate o balcao rodar `--doctor`.
                "drawer_lock": {
                    "calibrated": bool(self.config.drawer_status),
                    "query": int((self.config.drawer_status or {}).get("query") or 0),
                },
                "relay": {"enabled": self.config.relay_enabled},
            },
        )

    def _estado_da_gaveta(self) -> dict:
        """A gaveta esta aberta agora? `known: false` quando nao da para saber.

        Sem token de proposito: e leitura, nao efeito. Exigir token aqui
        obrigaria a tela a mandar o segredo num GET a cada poucos segundos, e
        segredo em URL/log e pior que a informacao "a gaveta esta aberta".
        """
        cfg = self.config.drawer_status or {}
        if not cfg:
            # Nunca mediu: a trava simplesmente nao existe neste balcao, e isso
            # e um fato de instalacao, nao uma falha. `calibrated: false` diz ao
            # PDV para ficar quieto.
            return {
                "known": False,
                "calibrated": False,
                "reason": "esta estacao nunca mediu a gaveta. Rode --drawer-status.",
            }
        # ⚠️ Daqui para baixo a estacao JA MEDIU. Todo `known: false` deste
        # ponto em diante e REGRESSAO — o sensor respondia e parou de responder
        # (cabo da gaveta fora, impressora trocada, porta ocupada). O PDV
        # continua sem travar, mas precisa saber a diferenca entre "aqui nunca
        # teve trava" e "a trava tinha e sumiu": a segunda e a fuga mais barata
        # que existe contra a trava, e ela nao pode ser silenciosa.
        query = _status_query(int(cfg.get("query") or 1))
        byte, motivo = _ler_estado(self.config, query=query)
        if byte is None:
            return {"known": False, "calibrated": True, "reason": motivo}
        aberta = self.config.estado_da_gaveta(byte)
        if aberta is None:
            return {"known": False, "calibrated": True, "reason": "polaridade nao configurada"}
        return {"known": True, "calibrated": True, "open": aberta, "raw": f"0x{byte:02x}"}

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
        titulo = " ".join(str(data.get("title") or "documento").split())[:60]
        try:
            payload = base64.b64decode(str(data.get("payload_b64") or ""), validate=True)
        except (binascii.Error, ValueError) as exc:
            logger.warning("impressao recusada: payload invalido (%s)", exc)
            self._reply(400, {"ok": False, "error": "payload_b64 inválido"})
            return
        if not payload:
            self._reply(400, {"ok": False, "error": "payload vazio"})
            return
        if len(payload) > MAX_PRINT_PAYLOAD_BYTES:
            self._reply(400, {"ok": False, "error": "payload excede 512 KiB"})
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
    handler = type("BoundCounterAgentHandler", (CounterAgentHandler,), {"config": config})
    server_class = ThreadingHTTPServer
    if config.host == "::1":
        server_class = type(
            "IPv6ThreadingHTTPServer",
            (ThreadingHTTPServer,),
            {"address_family": socket.AF_INET6},
        )
    httpd = server_class((config.host, config.port), handler)
    relay_stop = threading.Event()
    relay_thread: threading.Thread | None = None
    if config.relay_enabled:
        relay_thread = threading.Thread(
            target=_relay_thread_main,
            args=(config, relay_stop),
            name="print-relay",
            daemon=True,
        )
        relay_thread.start()
        logger.info(
            "relay de impressão ativo (servidor=%s estação=%s agente=%s)",
            config.server_url,
            config.station_ref,
            config.agent_id,
        )
    logger.info(
        "agente do balcão ouvindo em http://%s:%s (fila=%s, origens=%s)",
        config.host,
        config.port,
        config.queue,
        ", ".join(config.allowed_origins) or "nenhuma origem web",
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("encerrando")
    finally:
        relay_stop.set()
        if relay_thread is not None:
            relay_thread.join(timeout=2)
        httpd.server_close()


# ── Instalação ────────────────────────────────────────────────────────────
#
# Mora AQUI, e não num script ao lado, porque um arquivo é o que uma pessoa
# consegue levar até o balcão por qualquer meio — pendrive, scp, ou colando num
# editor. Dois arquivos que precisam chegar juntos são uma chance a mais de
# chegar só um.

UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / "nelson-pos-counter.service"
SERVICE_NAME = "nelson-pos-counter.service"
LAUNCH_AGENT_LABEL = "com.nelson.pos-counter"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
WINDOWS_TASK_NAME = "NelsonPosCounter"

#: O serviço que o agente teve quando ainda era só da gaveta.
#:
#: ⚠️ Ele não é lembrança: numa máquina que já rodava o antigo, o serviço velho
#: continua de pé e SEGURA a porta 47811. O novo então não sobe, quem responde é
#: o código velho — que não conhece as rotas novas — e reinstalar não resolve,
#: porque reinstalar é exatamente o que não está pegando. Custou duas
#: reinstalações no balcão descobrir isso com o nome anterior do arquivo.
LEGACY_SERVICE_NAME = "nelson-pos-drawer.service"
LEGACY_UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / LEGACY_SERVICE_NAME
LEGACY_LAUNCH_AGENT_LABEL = "com.nelson.pos-drawer"
LEGACY_LAUNCH_AGENT_PATH = (
    Path.home() / "Library" / "LaunchAgents" / f"{LEGACY_LAUNCH_AGENT_LABEL}.plist"
)
LEGACY_WINDOWS_TASK_NAME = "NelsonPosDrawer"
LEGACY_WINDOWS_LAUNCHER = "nelson-pos-drawer.cmd"

# Não existe default de origem, de propósito. A primeira versão cravava um
# domínio aqui e ele estava ERRADO — inventado, sem corresponder a nada no
# deployment. Uma constante inventada num arquivo que ninguém revisa vira 403 na
# gaveta, silencioso, no balcão. Quem sabe a origem é o Django
# (`SHOPMAN_POS_BASE_URL`), e o Admin já a coloca no comando de instalação.


def _unit_text(exec_path: Path) -> str:
    return f"""[Unit]
Description=Agente do balcão do PDV (Nelson)
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
    winspool.EnumPrintersW.argtypes = [
        wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
    ]
    winspool.EnumPrintersW.restype = wintypes.BOOL
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


def _write_private_json(path: Path, payload: dict) -> None:
    """Grava credenciais sem janela 0644 e substitui o arquivo atomicamente."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            logger.warning("não foi possível remover o arquivo temporário %s", temporary, exc_info=True)
        raise


def write_config(
    path: Path,
    *,
    queue: str,
    origin: str,
    token: str = "",
    server_url: str = "",
    station_ref: str = "",
    agent_id: str = "",
    relay_token: str = "",
) -> tuple[dict, bool]:
    """Escreve a config, ou preserva a que já existe.

    ``token`` vem do Admin, que é quem tem o par. Sem ele o agente gera um e
    imprime na tela — caminho de emergência, para quem estiver no balcão sem
    acesso ao Admin.

    Reinstalar NÃO troca o token guardado, a não ser que venha um explícito: o
    PDV ficaria batendo com o velho e levando 401 até alguém acertar os dois
    lados — e ninguém quer descobrir isso no meio de um sábado.
    """
    relay_requested = any((server_url, station_ref, agent_id, relay_token))
    if path.exists():
        config = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        if token and token != config.get("token"):
            config["token"] = token
            changed = True
        # Configs antigas vazias deixam de ser abertas a qualquer aba. Quando
        # o instalador novo já conhece a origem, aproveita para fechar a lacuna
        # sem substituir allowlists existentes.
        if origin and not config.get("allowed_origins"):
            config["allowed_origins"] = [origin.rstrip("/")]
            changed = True
        if relay_requested:
            relay_values = {
                "server_url": server_url,
                "station_ref": station_ref,
                "agent_id": agent_id or str(config.get("agent_id") or uuid.uuid4()),
                "relay_token": relay_token,
            }
            for key, value in relay_values.items():
                if value and value != config.get(key):
                    config[key] = value
                    changed = True
        # Valida antes de substituir. Config insegura (`0.0.0.0`) ou relay
        # parcial não entra em serviço por acidente.
        AgentConfig.from_dict(config)
        if changed:
            _write_private_json(path, config)
        else:
            path.chmod(0o600)
        return config, changed
    import secrets

    config = {
        "queue": queue,
        "token": token or secrets.token_urlsafe(32),
        "port": 47811,
        "host": "127.0.0.1",
        # Sem origem declarada a lista fica vazia e pedidos COM Origin são
        # recusados. CLI local e relay não enviam Origin e seguem funcionando.
        "allowed_origins": [origin.rstrip("/")] if origin else [],
    }
    if relay_requested:
        config.update(
            {
                "server_url": server_url,
                "station_ref": station_ref,
                "agent_id": agent_id or str(uuid.uuid4()),
                "relay_token": relay_token,
            }
        )
    AgentConfig.from_dict(config)
    _write_private_json(path, config)
    return config, True


def _arg_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1] if flag in argv and len(argv) > argv.index(flag) + 1 else ""


def stop_legacy_service() -> None:
    """Derruba o serviço do nome antigo, ANTES de subir o novo.

    Só parar não basta: enquanto a unit/tarefa antiga existir, ela ressuscita no
    próximo boot e volta a segurar a porta. Por isso o serviço é parado,
    desabilitado e o arquivo dele apagado.

    Tolerante de propósito — numa máquina nova nada disso existe, e não achar o
    serviço antigo não é erro. Erro é deixá-lo vivo: dois agentes disputando a
    47811 é uma disputa que o velho ganha, porque ele chegou primeiro.
    """
    if IS_WINDOWS:
        _run_quiet(["schtasks", "/end", "/tn", LEGACY_WINDOWS_TASK_NAME])
        _run_quiet(["schtasks", "/delete", "/f", "/tn", LEGACY_WINDOWS_TASK_NAME])
        # A pasta Inicializar é o fallback de quando o agendador recusa. Um
        # `.cmd` esquecido lá sobe o agente antigo a cada logon, e aí a máquina
        # volta a ter o problema no dia seguinte, quando ninguém liga uma coisa
        # à outra.
        _rm(_windows_startup_dir() / LEGACY_WINDOWS_LAUNCHER)
        return
    if IS_MACOS:
        _run_quiet(["launchctl", "bootout", f"gui/{os.getuid()}/{LEGACY_LAUNCH_AGENT_LABEL}"])
        _rm(LEGACY_LAUNCH_AGENT_PATH)
        return
    _run_quiet(["systemctl", "--user", "stop", LEGACY_SERVICE_NAME])
    _run_quiet(["systemctl", "--user", "disable", LEGACY_SERVICE_NAME])
    _rm(LEGACY_UNIT_PATH)
    _run_quiet(["systemctl", "--user", "daemon-reload"])


def _run_quiet(cmd: list[str]) -> None:
    """Roda e engole o resultado.

    Faxina não tem direito de derrubar a instalação: parar um serviço que não
    existe, numa máquina que nunca teve o agente antigo, é o resultado desejado
    — e nem o comando precisa existir.
    """
    try:
        subprocess.run(cmd, capture_output=True, check=False)
    except OSError:  # silêncio-deliberado: faxina aceita serviço/comando legado ausente
        pass


def _rm(path: Path) -> None:
    """Apaga se existir. Arquivo que já não está lá é o resultado desejado."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"aviso: não consegui apagar {path} ({exc}).")


def migrate_legacy_config() -> None:
    """Traz o ``agent.json`` do nome antigo, se ele ainda estiver lá.

    Mover, e não copiar: duas configs na mesma máquina é como o token do PDV e o
    do agente acabam diferentes sem ninguém entender. Não mexe se a config nova
    já existe — a atual é a que manda.
    """
    if DEFAULT_CONFIG_PATH.exists():
        return
    for antiga in LEGACY_CONFIG_PATHS:
        if not antiga.exists():
            continue
        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(antiga), str(DEFAULT_CONFIG_PATH))
        print(f"config movida de {antiga} para {DEFAULT_CONFIG_PATH}")
        return


def _windows_startup_dir() -> Path:
    """Pasta Inicializar do usuário — não precisa de agendador nem privilégio."""
    return (
        Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


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
    launcher = INSTALL_DIR / "nelson-pos-counter.cmd"
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
        startup = _windows_startup_dir()
        try:
            startup.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(launcher, startup / launcher.name)
            print(f"       Coloquei na pasta Inicializar: {startup / launcher.name}")
        except OSError as exc:
            print(f"       Suba na mão quando precisar: {launcher} ({exc})")
        return
    subprocess.run(["schtasks", "/run", "/tn", WINDOWS_TASK_NAME], capture_output=True, check=False)


def _escolher_fila(queues: list[str], rotulo: str) -> str:
    """Escolha por NÚMERO, não digitando o nome do dispositivo.

    Nome de fila do CUPS costuma ser coisa como `EPSON_TM-T20X_Receipt5` — quem
    instala no balcão erra um caractere, o instalador recusa, e a pessoa acha que
    a impressora é que está com problema. Um dígito não tem como sair errado.
    O nome ainda é aceito, para quem já sabe o que quer e para o `--queue`.
    """
    if len(queues) == 1:
        # Uma só: já é a resposta. Perguntar "qual das 1?" é cerimônia.
        unica = queues[0]
        resposta = input(f"Usar a impressora '{unica}'? [S/n] ").strip().lower()
        return "" if resposta.startswith("n") else unica

    print(f"{rotulo.capitalize()}:")
    for i, name in enumerate(queues, start=1):
        print(f"  {i}) {name}")
    escolha = input(f"Número da impressora térmica [1-{len(queues)}]: ").strip()
    if escolha.isdigit() and 1 <= int(escolha) <= len(queues):
        return queues[int(escolha) - 1]
    # Não é número: pode ser o nome digitado, e recusar aqui seria pedantismo.
    return escolha


# ── Diagnóstico e leitura do pino ─────────────────────────────────────────
#
# Quem opera o balcão não tem terminal, não tem `od`, não tem paciência para
# `printf '\x10\x04\x03' | sudo tee`. Cada comando digitado à mão é uma chance
# de errar e concluir que o defeito é da impressora. Estes dois comandos existem
# para que a resposta caiba numa linha e o diagnóstico seja do programa, não da
# pessoa.

def _mascarar(token: str, keep: int = 4) -> str:
    """As pontas do token: ``FxYA…8eRA``. Igual ao `mask_badge` do servidor.

    O agente não importa código do Django (é stdlib pura, roda sozinho no
    balcão), então a regra está escrita duas vezes de propósito. O que não pode
    divergir é o FORMATO: máscaras diferentes nos dois lados não dariam para
    comparar, que é exatamente para o que elas servem aqui.
    """
    token = (token or "").strip()
    if len(token) <= keep * 2:
        return token or "(vazio)"
    return f"{token[:keep]}…{token[-keep:]}"


def doctor() -> int:
    """`--doctor`: responde, de uma vez, se este balcão está são."""
    print("\nAgente do balcão — diagnóstico\n")
    tudo_certo = True

    esperado = build_id()
    print(f"  versão deste arquivo ..... {esperado}")

    # ⚠️ O diagnóstico NÃO pode morrer no primeiro problema que encontra: sem
    # config ele saía com SystemExit e nem chegava a olhar o serviço ou a
    # impressora. Ferramenta de diagnóstico que aborta no primeiro achado obriga
    # a pessoa a consertar às cegas, um item por vez.
    try:
        config = AgentConfig.load(DEFAULT_CONFIG_PATH)
    except SystemExit as exc:
        print(f"  config .................. ✗ {str(exc).splitlines()[0]}")
        print("\n  Sem config o agente não sobe. Reinstale pelo gestor.\n")
        return 1
    print(f"  config ................... {DEFAULT_CONFIG_PATH}")
    # ⚠️ O TOKEN é a única falha que produz "token inválido" no PDV, e era a única
    # coisa que este diagnóstico não olhava: dizia "tudo certo" enquanto o par
    # estava desencontrado. Mostrar as pontas dá onde comparar com o Admin sem
    # revelar a credencial — a mesma máscara que a folha do crachá e a tela do
    # terminal usam (`mask_badge`), para os três serem comparáveis entre si.
    print(f"  token no arquivo ......... {_mascarar(config.token)}")
    if config.relay_enabled:
        print(f"  relay .................... ativo → {config.server_url}")
        print(f"  estação/agente ........... {config.station_ref} / {config.agent_id}")
        print("  credencial do relay ...... configurada (não exibida)")
        if JOURNAL_PATH.exists():
            journal = RelayJournal(JOURNAL_PATH)
            resumo = ", ".join(
                f"{state}={amount}" for state, amount in sorted(journal.counts().items())
            ) or "vazio"
            print(f"  journal do relay ......... {resumo}")
            print(
                "  ACKs pendentes ............ "
                f"{len(journal.pending_acknowledgements())}"
            )
        else:
            print("  journal do relay ......... ainda sem trabalhos")
    else:
        print("  relay .................... desativado (modo local)")

    saude = _wait_until_listening({"port": config.port}, seconds=3)
    if saude is None:
        print("  versão no ar ............. ninguém respondeu na porta")
        print(f"     ✗ o agente não está rodando. Reinstale, ou suba com: python3 {Path(__file__).resolve()}")
        tudo_certo = False
    else:
        rodando = str(saude.get("build") or "?")
        igual = rodando == esperado
        print(f"  versão no ar ............. {rodando}" + ("   ✓" if igual else "   ✗ DIFERENTE"))
        if not igual:
            print("     ✗ quem responde não é este arquivo: a última instalação não pegou.")
            print(f"       na porta: {_quem_ocupa_a_porta(config.port)}")
            print(f"       derrube:  {_comando_de_parada()}")
            tudo_certo = False

        # ⚠️ O TOKEN DO PROCESSO VIVO, que é quem o navegador interroga.
        #
        # Reinstalar troca o `agent.json` sem tocar no `.py`: o `build` fica
        # idêntico, o arquivo tem o token novo, e o processo que está no ar segue
        # com o antigo carregado na memória desde que subiu. O diagnóstico dizia
        # "tudo certo" comparando o arquivo, enquanto o PDV levava 401 do
        # processo. Reiniciar o serviço é o conserto, e sem esta linha não havia
        # como chegar a essa conclusão.
        vivo = str(saude.get("token_hint") or "")
        if not vivo:
            print("  token no ar .............. o agente no ar é anterior a este diagnóstico")
            print("     reinstale pelo gestor para o `--doctor` poder comparar os dois.")
        else:
            bate = vivo == _mascarar(config.token)
            print(f"  token no ar .............. {vivo}" + ("   ✓" if bate else "   ✗ DIFERENTE DO ARQUIVO"))
            if not bate:
                print("     ✗ o processo no ar subiu com outro token: por isso o PDV diz")
                print("       'token inválido' enquanto a linha de comando funciona (ela lê")
                print("       o arquivo; o navegador fala com o processo).")
                print(f"       reinicie:  {_comando_de_parada()}")
                print("       e suba de novo pelo comando do gestor.")
                tudo_certo = False

    if sys.platform.startswith("linux"):
        atual = _servico_ativo(SERVICE_NAME)
        antigo = _servico_ativo(LEGACY_SERVICE_NAME)
        print(f"  serviço .................. {SERVICE_NAME}: {'ativo ✓' if atual else 'PARADO ✗'}")
        print(f"  serviço antigo ........... {'AINDA EXISTE ✗' if antigo else 'removido ✓'}")
        if antigo:
            print("     ✗ o antigo segura a porta e impede o novo de subir.")
            print(f"       derrube: systemctl --user stop {LEGACY_SERVICE_NAME}")
        tudo_certo = tudo_certo and atual and not antigo

    fila = probe_queue(config.queue)
    ok_fila = bool(fila.get("ok"))
    print(f"  impressora ............... {config.queue}: " + ("aceitando ✓" if ok_fila else f"{fila.get('reason') or 'não aceita trabalho'} ✗"))
    tudo_certo = tudo_certo and ok_fila

    # ⚠️ A trava da gaveta é o único recurso deste agente que fica DESLIGADO em
    # silêncio: sem medição, `/drawer` responde "não sei", o PDV nunca trava, e
    # nada em lugar nenhum diz que a proteção não existe. Um balcão sem medição
    # parecia idêntico a um balcão protegido.
    medido = bool(config.drawer_status)
    print("  trava da gaveta .......... " + ("ARMADA ✓ (polaridade medida nesta estação)" if medido else "sem medição ✗"))
    if not medido:
        print("     ✗ o PDV não consegue saber se a gaveta ficou aberta, e a trava")
        print("       da próxima venda nunca vai agir neste balcão.")
        print(f"       meça: {sys.executable} {Path(__file__).resolve()} --drawer-status")
        tudo_certo = False

    print("\n  " + ("tudo certo." if tudo_certo else "há o que resolver acima.") + "\n")
    return 0 if tudo_certo else 1


def _servico_ativo(nome: str) -> bool:
    """`is-active` responde 0 só quando o serviço está de pé."""
    if not shutil.which("systemctl"):
        return False
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", nome], capture_output=True, check=False
    )
    return r.returncode == 0


#: `DLE EOT 3` — status em tempo real do conector da gaveta.
#: `DLE EOT n` - status em tempo real. O `n` escolhe QUAL status.
#:
#: ⚠️ Perguntamos os quatro, e nao so o que eu acho ser o certo. A primeira
#: versao usou `n=3` (status de ERRO) e o balcao devolveu 0x12 com a gaveta
#: fechada E aberta - o byte estava certo, a pergunta e que era outra. Pelo
#: manual o pino da gaveta vive no `n=1` (status da impressora, bit 2), mas
#: perguntar os quatro custa milissegundos e dispensa eu estar certo: quem
#: responde qual muda e a impressora, nao a minha memoria.
_DRAWER_STATUS_QUERIES = {
    1: "status da impressora",
    2: "status offline",
    3: "status de erro",
    4: "sensor de papel",
}


def _status_query(n: int) -> bytes:
    return bytes([0x10, 0x04, n])


#: Compatibilidade interna: os leitores de UMA pergunta ainda usam este.
_DRAWER_STATUS_QUERY = _status_query(1)


def _dispositivos_possiveis() -> list[Path]:
    """Onde o kernel costuma expor a impressora USB, do mais provável ao menos."""
    achados: list[Path] = []
    for padrao in ("/dev/usb/lp*", "/dev/lp*", "/dev/ttyUSB*"):
        achados.extend(sorted(Path("/").glob(padrao.lstrip("/"))))
    return achados


def _ler_pino(device: Path, *, query: bytes = _DRAWER_STATUS_QUERY, timeout: float = 2.0) -> tuple[int | None, str]:
    """Pergunta o estado e lê UM byte. Devolve (byte, motivo-da-falha)."""
    import select

    try:
        fd = os.open(str(device), os.O_RDWR | os.O_NONBLOCK)
    except PermissionError:
        return None, f"sem permissão para abrir {device} (o usuário precisa estar no grupo 'lp')"
    except OSError as exc:
        return None, f"não consegui abrir {device}: {exc}"
    try:
        os.write(fd, query)
        pronto, _, _ = select.select([fd], [], [], timeout)
        if not pronto:
            return None, "a impressora não respondeu (o canal pode ser só de escrita)"
        dados = os.read(fd, 1)
        return (dados[0], "") if dados else (None, "resposta vazia")
    except OSError as exc:
        return None, f"falha ao conversar com {device}: {exc}"
    finally:
        os.close(fd)


def _ler_estado(config, *, query: bytes) -> tuple[int | None, str]:
    """Le um status pelo caminho que ESTE sistema tem."""
    if IS_WINDOWS:
        byte, motivo = _ler_pino_windows(config.queue, query=query)
        if byte is not None:
            return byte, ""
        return _ler_pino_usb_windows(query=query)
    dispositivos = _dispositivos_possiveis()
    if not dispositivos:
        return None, "dispositivo da impressora nao encontrado"
    return _ler_pino(dispositivos[0], query=query)


def _varre_status(ler) -> dict[int, int]:
    """Pergunta os quatro status e devolve {n: byte} do que respondeu.

    `ler` e uma funcao que recebe a pergunta e devolve (byte, motivo) - assim o
    mesmo varredor serve para o Linux, para o spooler e para o USB direto.
    """
    lidos: dict[int, int] = {}
    for n in sorted(_DRAWER_STATUS_QUERIES):
        byte, _motivo = ler(_status_query(n))
        if byte is not None:
            lidos[n] = byte
    return lidos


def _veredito_da_varredura(fechada: dict[int, int], aberta: dict[int, int]) -> int:
    """Qual dos status muda com a gaveta - e o bit exato dentro dele."""
    print("")
    mudaram = []
    for n, rotulo in sorted(_DRAWER_STATUS_QUERIES.items()):
        f, a = fechada.get(n), aberta.get(n)
        if f is None or a is None:
            print(f"  DLE EOT {n} ({rotulo}): sem resposta")
            continue
        marca = "  <-- MUDOU" if f != a else ""
        print(f"  DLE EOT {n} ({rotulo}): fechada 0x{f:02x} · aberta 0x{a:02x}{marca}")
        if f != a:
            mudaram.append((n, f, a))

    if not mudaram:
        print("\n  Nenhum dos quatro status muda com a gaveta.")
        print("  A impressora responde, mas nao reporta o pino nesta montagem.")
        print("  O que resta e o driver da Epson (OPOS/APD); se nem ele, o")
        print("  controle de gaveta aberta tem que ser fisico (gaveta com alarme).\n")
        return 1

    n, f, a = mudaram[0]
    mascara = f ^ a
    print(f"\n  OK, FUNCIONA. `DLE EOT {n}`, bit 0x{mascara:02x}.")

    # Grava o que ESTA gaveta respondeu. A polaridade varia por montagem: aqui
    # medimos fechada=0x16 (bit ligado) e aberta=0x12 (desligado), o inverso do
    # que a leitura ingenua do manual sugere. Salvar o medido, e nunca uma
    # constante, e o que impede o alerta de nascer invertido.
    salvo = _salvar_drawer_status({"query": n, "mask": mascara, "closed_value": f & mascara})
    if salvo:
        print(f"  Aprendido e gravado em {DEFAULT_CONFIG_PATH}.")
        print("  O PDV ja pode avisar quando a gaveta ficar aberta.\n")
    else:
        print("  (nao consegui gravar na config; me mande estas linhas)\n")
    return 0


def _salvar_drawer_status(medido: dict) -> bool:
    """Guarda a polaridade medida junto do resto da config da maquina."""
    try:
        raw = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        raw["drawer_status"] = medido
        DEFAULT_CONFIG_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return True
    except (OSError, ValueError):
        return False


def _veredito_do_pino(fechada: int, aberta: int) -> int:
    """A conclusão do experimento. Uma só, para Linux e Windows não divergirem."""
    if fechada == aberta:
        print(f"\n  Os dois bytes sao iguais (0x{fechada:02x}).")
        print("  A impressora responde, mas nao distingue a gaveta - por este")
        print("  caminho nao da. Controle de gaveta aberta tem que ser fisico.\n")
        return 1
    mudou = fechada ^ aberta
    print(f"\n  OK, FUNCIONA. Fechada 0x{fechada:02x}, aberta 0x{aberta:02x} (bit 0x{mudou:02x}).")
    print("  Da para o sistema saber quando a gaveta fica aberta. Me mande estes")
    print("  dois numeros que eu ligo o alerta.\n")
    return 0


#: GUID da interface que o `usbprint.sys` do Windows expoe para impressora USB.
#: Abrir por aqui fala com o APARELHO, sem passar pelo spooler - que e onde a
#: bidirecionalidade se perde. Documentado pela Microsoft, sem driver de
#: terceiro: e o mesmo caminho que os utilitarios de fabricante usam.
_GUID_USBPRINT = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"


def _caminho_usb_windows() -> tuple[str, str]:
    """Descobre o caminho do dispositivo da impressora USB. ("", motivo) se nao achar."""
    import ctypes
    from ctypes import wintypes

    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8),
        ]

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
            ("Flags", wintypes.DWORD), ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
        ]

    # ⚠️ TODA funcao usada aqui precisa de `argtypes`. Sem isso o ctypes assume
    # `int` de 32 bits para cada argumento, e o handle que o Windows devolve em
    # 64 bits NAO CABE: a chamada morre com "int too long to convert" - erro que
    # parece problema do GUID e nao e. Foi assim que a primeira versao quebrou no
    # balcao, e quebrou duas vezes: na chamada e de novo no `finally`.
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]
    ole32.CLSIDFromString.restype = ctypes.c_long

    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD
    ]
    setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
        ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ]
    setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    guid = GUID()
    if ole32.CLSIDFromString(_GUID_USBPRINT, ctypes.byref(guid)) != 0:
        return "", "nao consegui montar o identificador da interface USB"

    DIGCF_PRESENT, DIGCF_DEVICEINTERFACE = 0x02, 0x10
    conjunto = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    # `restype=HANDLE` devolve None quando o retorno e NULL; sem tratar, o
    # `finally` receberia None e mascararia o erro real.
    if not conjunto or conjunto == wintypes.HANDLE(-1).value:
        return "", "nao consegui listar as impressoras USB do sistema"

    try:
        interface = SP_DEVICE_INTERFACE_DATA()
        interface.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        if not setupapi.SetupDiEnumDeviceInterfaces(conjunto, None, ctypes.byref(guid), 0, ctypes.byref(interface)):
            return "", "nenhuma impressora USB encontrada (ela esta ligada e no USB?)"

        # Primeira chamada so para saber o tamanho; a segunda traz o caminho.
        tamanho = wintypes.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            conjunto, ctypes.byref(interface), None, 0, ctypes.byref(tamanho), None
        )

        class DETALHE(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("DevicePath", ctypes.c_wchar * (tamanho.value or 256))]

        detalhe = DETALHE()
        # 8 em 64 bits, 6 em 32: o cbSize aqui e do CABECALHO, nao da struct
        # inteira. Passar sizeof(DETALHE) faz a chamada falhar com "parametro
        # invalido", que e o erro mais enganoso desta API.
        detalhe.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        if not setupapi.SetupDiGetDeviceInterfaceDetailW(
            conjunto, ctypes.byref(interface), ctypes.byref(detalhe), tamanho, None, None
        ):
            return "", f"nao consegui o caminho do dispositivo (erro {ctypes.get_last_error()})"
        return detalhe.DevicePath, ""
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(conjunto)


def _ler_pino_usb_windows(*, query: bytes = _DRAWER_STATUS_QUERY, timeout: float = 2.0) -> tuple[int | None, str]:
    """Fala com o APARELHO, sem spooler. E o caminho de quem precisa de resposta."""
    import ctypes
    import time
    from ctypes import wintypes

    caminho, motivo = _caminho_usb_windows()
    if not caminho:
        return None, motivo

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Mesma regra do bloco acima: sem `argtypes` o handle de 64 bits nao passa.
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    GENERIC_READ, GENERIC_WRITE, OPEN_EXISTING = 0x80000000, 0x40000000, 3
    h = kernel32.CreateFileW(caminho, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if not h or h == wintypes.HANDLE(-1).value:
        erro = ctypes.get_last_error()
        if erro == 32:  # ERROR_SHARING_VIOLATION
            return None, "o dispositivo esta ocupado - feche o que estiver imprimindo e tente de novo"
        return None, f"nao consegui abrir o dispositivo USB (erro {erro})"
    try:
        escritos = wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(query, len(query))
        if not kernel32.WriteFile(h, buf, len(query), ctypes.byref(escritos), None):
            return None, f"nao consegui perguntar ao aparelho (erro {ctypes.get_last_error()})"

        lido = wintypes.DWORD(0)
        resposta = ctypes.create_string_buffer(8)
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if kernel32.ReadFile(h, resposta, 1, ctypes.byref(lido), None) and lido.value:
                return resposta.raw[0], ""
            time.sleep(0.1)
        return None, "o aparelho nao devolveu nada nem falando direto com ele"
    finally:
        kernel32.CloseHandle(h)


def _ler_pino_windows(queue: str, *, query: bytes = _DRAWER_STATUS_QUERY, timeout: float = 2.0) -> tuple[int | None, str]:
    """Pergunta o estado pelo spooler e tenta LER a resposta de volta.

    O agente ja conversa com o ``winspool.drv`` para imprimir (``OpenPrinter`` +
    ``WritePrinter``); a mesma biblioteca tem ``ReadPrinter``. Tentar ler nao e
    caminho novo - e uma funcao a mais no canal que ja existe.

    O que NAO e garantido: ler de volta pelo spooler depende de a porta e o
    driver serem bidirecionais, e isso varia por instalacao. Quando nao for,
    ``ReadPrinter`` devolve zero bytes - e a resposta honesta e essa, nao um
    chute. O caminho garantido no Windows e o driver da Epson (OPOS/APD), que
    expoe o estado da gaveta como funcao pronta, mas custa uma instalacao.
    """
    import ctypes
    import time
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [
            ("pDocName", wintypes.LPWSTR),
            ("pOutputFile", wintypes.LPWSTR),
            ("pDatatype", wintypes.LPWSTR),
        ]

    winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    # As de HANDLE puro funcionam hoje por acaso: recebem um objeto ctypes, nao
    # um int cru. Declaradas mesmo assim - a hora em que alguem passar um int
    # (foi o que quebrou a leitura da gaveta) e a hora em que ninguem lembra
    # desta distincao.
    winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.StartPagePrinter.restype = wintypes.BOOL
    winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.EndPagePrinter.restype = wintypes.BOOL
    winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    winspool.EndDocPrinter.restype = wintypes.BOOL
    winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    winspool.ClosePrinter.restype = wintypes.BOOL
    winspool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
    winspool.WritePrinter.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]
    winspool.ReadPrinter.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]

    handle = wintypes.HANDLE()
    if not winspool.OpenPrinterW(queue, ctypes.byref(handle), None):
        return None, f"nao consegui abrir a impressora '{queue}' (erro {ctypes.get_last_error()})"
    try:
        info = DOC_INFO_1("estado-gaveta", None, "RAW")
        if not winspool.StartDocPrinterW(handle, 1, ctypes.byref(info)):
            return None, f"nao consegui iniciar o trabalho (erro {ctypes.get_last_error()})"
        try:
            winspool.StartPagePrinter(handle)
            escritos = wintypes.DWORD(0)
            buffer = ctypes.create_string_buffer(query, len(query))
            if not winspool.WritePrinter(handle, buffer, len(query), ctypes.byref(escritos)):
                return None, f"nao consegui perguntar a impressora (erro {ctypes.get_last_error()})"
            winspool.EndPagePrinter(handle)
        finally:
            winspool.EndDocPrinter(handle)

        # A resposta nao vem instantanea: a impressora processa e devolve. Sem
        # esta espera a leitura sai vazia e pareceria "nao e bidirecional"
        # quando e so pressa.
        lido = wintypes.DWORD(0)
        resposta = ctypes.create_string_buffer(8)
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if winspool.ReadPrinter(handle, resposta, 1, ctypes.byref(lido)) and lido.value:
                return resposta.raw[0], ""
            time.sleep(0.1)
        return None, (
            "a impressora nao devolveu nada. Esta porta provavelmente nao e "
            "bidirecional pelo spooler - o caminho garantido no Windows e o "
            "driver da Epson (OPOS/APD)"
        )
    finally:
        winspool.ClosePrinter(handle)


def _drawer_status_windows() -> int:
    """O mesmo experimento do Linux, pelo canal que o Windows tem."""
    config = AgentConfig.load(DEFAULT_CONFIG_PATH)
    print(f"\nLendo pela impressora '{config.queue}' (spooler do Windows)")

    # Descobre UMA vez por qual caminho a impressora responde, e usa ele nas
    # duas leituras. Redescobrir a cada pergunta imprimiria o "tentando falar
    # direto" oito vezes e esconderia o resultado no meio do ruido.
    def pelo_spooler(q):
        return _ler_pino_windows(config.queue, query=q)

    byte, motivo = pelo_spooler(_status_query(1))
    ler = pelo_spooler
    if byte is None:
        print(f"  - pelo spooler: {motivo}")
        print("  - tentando falar direto com o aparelho USB...")
        byte, motivo_usb = _ler_pino_usb_windows(query=_status_query(1))
        if byte is None:
            print(f"  x {motivo_usb}")
            print("\n  Nao da para ler o estado da gaveta nesta maquina.")
            print("  Isso NAO e defeito da impressora: o comando existe e ela responde.")
            print("  O caminho que resta e o driver da Epson (OPOS/APD), que expoe o")
            print("  estado como funcao pronta - mas custa uma instalacao aqui.\n")
            return 1
        print("  (respondeu falando direto com o aparelho)")
        ler = lambda q: _ler_pino_usb_windows(query=q)  # noqa: E731

    varreduras: list[dict[int, int]] = []
    for rotulo in ("FECHADA", "ABERTA"):
        input(f"\n  Deixe a gaveta {rotulo} e tecle Enter... ")
        lidos = _varre_status(ler)
        if not lidos:
            print("  x a impressora parou de responder no meio do teste")
            return 1
        varreduras.append(lidos)
        print("  respondeu: " + " · ".join(f"EOT{n}=0x{b:02x}" for n, b in sorted(lidos.items())))

    return _veredito_da_varredura(varreduras[0], varreduras[1])


def drawer_status(argv: list[str]) -> int:
    """`--drawer-status`: descobre se dá para LER se a gaveta está aberta.

    Não afirma nada de antemão. Lê o byte com a gaveta fechada e de novo com ela
    aberta, e compara — se mudar, o estado é legível e o sistema pode passar a
    avisar "gaveta aberta há 3 minutos". Se não mudar, a resposta honesta é que
    por este caminho não dá, e paramos de gastar tempo.
    """
    if IS_WINDOWS:
        return _drawer_status_windows()

    dispositivos = _dispositivos_possiveis()
    if not dispositivos:
        print("Não achei o dispositivo da impressora (/dev/usb/lp*).")
        print("A impressora está ligada e instalada?")
        return 1
    device = Path(_arg_value(argv, "--device") or dispositivos[0])
    print(f"\nLendo pela {device}" + (f"  (outras: {', '.join(str(d) for d in dispositivos[1:])})" if len(dispositivos) > 1 else ""))

    varreduras: list[dict[int, int]] = []
    for rotulo in ("FECHADA", "ABERTA"):
        input(f"\n  Deixe a gaveta {rotulo} e tecle Enter... ")
        lidos = _varre_status(lambda q: _ler_pino(device, query=q))
        if not lidos:
            byte, motivo = _ler_pino(device)
            print(f"  ✗ {motivo}")
            print("\n  Não dá para ler o estado da gaveta por este caminho.")
            print("  Isso NÃO é defeito: significa que o controle de gaveta aberta")
            print("  precisa ser físico (gaveta com alarme), não de software.\n")
            return 1
        varreduras.append(lidos)
        print("  respondeu: " + " · ".join(f"EOT{n}=0x{b:02x}" for n, b in sorted(lidos.items())))

    return _veredito_da_varredura(varreduras[0], varreduras[1])


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
        queue = _escolher_fila(queues, rotulo)
        if not queue:
            print("erro: nenhuma impressora escolhida.", file=sys.stderr)
            return 1
    if queue not in queues:
        print(f"erro: '{queue}' não está entre as {rotulo} deste computador.", file=sys.stderr)
        return 1

    server_url = _arg_value(argv, "--server-url")
    station_ref = _arg_value(argv, "--station") or _arg_value(argv, "--station-ref")
    agent_id = _arg_value(argv, "--agent-id")
    relay_token = _arg_value(argv, "--relay-token")
    if any((server_url, station_ref, agent_id, relay_token)) and not all(
        (server_url, station_ref, relay_token)
    ):
        print(
            "erro: relay requer --server-url, --station e --relay-token "
            "(--agent-id é opcional e será gerado).",
            file=sys.stderr,
        )
        return 1
    if server_url:
        parsed_relay = urllib.parse.urlparse(server_url)
        if (
            parsed_relay.scheme != "https"
            or not parsed_relay.netloc
            or parsed_relay.username
            or parsed_relay.password
            or parsed_relay.query
            or parsed_relay.fragment
            or len(relay_token) < 16
            or len(station_ref) > 80
            or len(agent_id) > 120
            or any(c not in _IDENTITY_CHARS for c in station_ref + agent_id)
        ):
            print(
                "erro: relay requer URL HTTPS sem credenciais e token com ao menos 16 caracteres.",
                file=sys.stderr,
            )
            return 1

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    migrate_legacy_config()

    target = INSTALL_DIR / "counter_agent.py"
    source = Path(__file__).resolve()
    if source != target.resolve():
        shutil.copyfile(source, target)
    if not IS_WINDOWS:
        target.chmod(0o755)

    token = _arg_value(argv, "--token")
    origin = _arg_value(argv, "--origin")
    config, written = write_config(
        DEFAULT_CONFIG_PATH,
        queue=queue,
        origin=origin,
        token=token,
        server_url=server_url,
        station_ref=station_ref,
        agent_id=agent_id,
        relay_token=relay_token,
    )

    # Primeiro derruba o antigo, depois sobe o novo. Invertido, o novo tenta
    # subir com a porta ocupada, falha calado, e o instalador só descobre lá
    # embaixo, na conferência do `build` — com o operador achando que o agente
    # instalou.
    stop_legacy_service()
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
            "\naviso: sem --origin, pedidos de páginas do navegador serão recusados.\n"
            "       A linha de comando e o relay continuam disponíveis.\n"
            "       Pegue o comando completo no Admin: Terminais do PDV → este\n"
            "       terminal → Baixar o agente e ver como instalar."
        )
    if config.get("server_url"):
        print(
            "Relay HTTPS ativo para a estação "
            f"{config.get('station_ref')} (agente {config.get('agent_id')})."
        )
    if token:
        # Veio do Admin: o par já existe dos dois lados, nada a transcrever.
        print("Token recebido do Admin — nada a copiar de volta.")
    elif written:
        # Emergência: quem está no balcão sem acesso ao Admin. O Admin não tem
        # onde COLAR token — quem gera o par é ele. Então este aqui só faz o
        # agente subir; enquanto os dois lados não baterem, o PDV leva 401. Dizer
        # "cole no Admin" mandava a pessoa procurar um campo que não existe.
        print("\n  ┌─ TOKEN GERADO AQUI, sem o Admin ───────────────────────────")
        print("  │  O agente sobe, mas o PDV só abre quando os dois lados baterem.")
        print("  │  Com acesso ao Admin, reinstale com o comando de lá:")
        print("  │  Terminais do PDV → este terminal → Baixar o agente.")
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
        except (urllib.error.URLError, OSError, ValueError):  # silêncio-deliberado: probe repete até o prazo
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
    if "--doctor" in argv:
        return doctor()
    if "--drawer-status" in argv:
        return drawer_status(argv)
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
