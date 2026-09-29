#!/usr/bin/env python3
"""Player local de dois menuboards e controlador HDMI-CEC (somente stdlib)."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "1.0"
USER_AGENT = f"Shopman Menuboard Player/{VERSION}"
LOG = logging.getLogger("menuboard-player")


@dataclass(frozen=True)
class ScreenConfig:
    ref: str
    cec_adapter: str
    token: str
    window_position: str
    window_size: str


@dataclass(frozen=True)
class PlayerConfig:
    server_url: str
    poll_seconds: int
    standby_delay_minutes: int
    chromium: str
    screens: tuple[ScreenConfig, ...]
    state_dir: Path

    @classmethod
    def from_dict(cls, raw: dict, *, home: Path | None = None) -> PlayerConfig:
        server_url = str(raw.get("server_url") or "").strip().rstrip("/")
        parsed = urlsplit(server_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("server_url precisa ser uma origem HTTP(S) válida")
        poll_seconds = _positive_int(raw.get("poll_seconds", 30), "poll_seconds")
        standby_delay = _nonnegative_int(raw.get("standby_delay_minutes", 30), "standby_delay_minutes")
        chromium = str(raw.get("chromium") or "chromium").strip()
        if not chromium:
            raise ValueError("chromium não pode ficar vazio")
        screens_raw = raw.get("screens")
        if not isinstance(screens_raw, list) or not screens_raw:
            raise ValueError("screens precisa ter ao menos uma tela")
        screens: list[ScreenConfig] = []
        refs: set[str] = set()
        adapters: set[str] = set()
        for index, item in enumerate(screens_raw):
            if not isinstance(item, dict):
                raise ValueError(f"screens[{index}] precisa ser um objeto")
            screen = ScreenConfig(
                ref=str(item.get("ref") or "").strip(),
                cec_adapter=str(item.get("cec_adapter") or "").strip(),
                token=str(item.get("token") or "").strip(),
                window_position=str(item.get("window_position") or "").strip(),
                window_size=str(item.get("window_size") or "").strip(),
            )
            if not screen.ref or not screen.cec_adapter or len(screen.token) < 20:
                raise ValueError(f"screens[{index}] precisa de ref, cec_adapter e token válido")
            if not _pair_of_ints(screen.window_position, allow_zero=True):
                raise ValueError(f"window_position inválido em screens[{index}]")
            if not _pair_of_ints(screen.window_size, allow_zero=False):
                raise ValueError(f"window_size inválido em screens[{index}]")
            if screen.ref in refs or screen.cec_adapter in adapters:
                raise ValueError("cada tela precisa de ref e cec_adapter únicos")
            refs.add(screen.ref)
            adapters.add(screen.cec_adapter)
            screens.append(screen)
        root = home or Path.home()
        state_dir = Path(raw.get("state_dir") or root / ".local/share/nelson-menuboard-player").expanduser()
        return cls(server_url, poll_seconds, standby_delay, chromium, tuple(screens), state_dir)


@dataclass
class ScreenRuntime:
    config: ScreenConfig
    browser: subprocess.Popen | None = None
    power_on: bool | None = None
    sleep_started_at: float | None = None
    next_transition_at: datetime | None = None


def _positive_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} precisa ser inteiro maior que zero")
    return value


def _nonnegative_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} precisa ser inteiro não negativo")
    return value


def _pair_of_ints(value: str, *, allow_zero: bool) -> bool:
    try:
        values = [int(part) for part in value.split(",")]
    except ValueError:
        return False
    return len(values) == 2 and all(number >= (0 if allow_zero else 1) for number in values)


def load_config(path: Path) -> PlayerConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"não foi possível ler {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("a raiz da configuração precisa ser um objeto JSON")
    return PlayerConfig.from_dict(raw)


def browser_command(config: PlayerConfig, screen: ScreenConfig) -> list[str]:
    profile = config.state_dir / "profiles" / screen.ref
    return [
        config.chromium,
        "--kiosk",
        "--no-first-run",
        "--disable-session-crashed-bubble",
        "--disable-features=Translate",
        f"--user-data-dir={profile}",
        f"--window-position={screen.window_position}",
        f"--window-size={screen.window_size}",
        f"{config.server_url}/menuboard/{screen.ref}/",
    ]


def cec_command(screen: ScreenConfig) -> list[str]:
    return ["cec-client", "-s", "-d", "1", screen.cec_adapter]


class Player:
    def __init__(self, config: PlayerConfig, *, dry_run: bool = False, monotonic=time.monotonic):
        self.config = config
        self.dry_run = dry_run
        self.monotonic = monotonic
        self.screens = [ScreenRuntime(screen) for screen in config.screens]

    def start_browsers(self) -> None:
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        for runtime in self.screens:
            self.ensure_browser(runtime)

    def ensure_browser(self, runtime: ScreenRuntime) -> None:
        if runtime.browser is not None and runtime.browser.poll() is None:
            return
        command = browser_command(self.config, runtime.config)
        if self.dry_run:
            LOG.info("DRY-RUN navegador %s: %s", runtime.config.ref, command)
            return
        if runtime.browser is not None:
            LOG.warning("%s: Chromium encerrou; abrindo de novo", runtime.config.ref)
        profile = self.config.state_dir / "profiles" / runtime.config.ref
        profile.mkdir(parents=True, exist_ok=True)
        runtime.browser = subprocess.Popen(command)  # noqa: S603 — config local explícita

    def close(self) -> None:
        for runtime in self.screens:
            if runtime.browser is not None and runtime.browser.poll() is None:
                runtime.browser.terminate()

    def tick(self) -> None:
        for runtime in self.screens:
            self.ensure_browser(runtime)
            try:
                intent = self.fetch_intent(runtime.config)
                self.apply_intent(runtime, intent)
            except (OSError, ValueError, urllib.error.URLError) as exc:
                LOG.warning("%s: controle indisponível: %s", runtime.config.ref, exc)
                self.fail_open_if_wake_is_due(runtime)

    def fetch_intent(self, screen: ScreenConfig) -> dict:
        request = urllib.request.Request(
            f"{self.config.server_url}/menuboard/{screen.ref}/control/",
            headers={"Authorization": f"Bearer {screen.token}", "User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read(64 * 1024))
        if not isinstance(payload, dict) or payload.get("ref") != screen.ref:
            raise ValueError("resposta de controle não corresponde à tela")
        if payload.get("mode") not in {"content", "sleep", "message"}:
            raise ValueError("modo de controle desconhecido")
        if not isinstance(payload.get("standby_allowed"), bool):
            raise ValueError("standby_allowed ausente ou inválido")
        return payload

    def apply_intent(self, runtime: ScreenRuntime, intent: dict) -> None:
        runtime.next_transition_at = _parse_datetime(intent.get("next_transition_at"))
        if not intent["standby_allowed"]:
            runtime.sleep_started_at = None
            self.set_power(runtime, on=True)
            return
        if runtime.sleep_started_at is None:
            runtime.sleep_started_at = self.monotonic()
        elapsed = self.monotonic() - runtime.sleep_started_at
        delay = self.config.standby_delay_minutes * 60
        self.set_power(runtime, on=elapsed < delay)

    def fail_open_if_wake_is_due(self, runtime: ScreenRuntime) -> None:
        transition = runtime.next_transition_at
        if runtime.power_on is False and transition is not None and datetime.now(UTC) >= transition:
            LOG.warning("%s: horário de acordar passou sem rede; acordando por segurança", runtime.config.ref)
            runtime.sleep_started_at = None
            self.set_power(runtime, on=True)

    def set_power(self, runtime: ScreenRuntime, *, on: bool) -> None:
        if runtime.power_on is on:
            return
        stdin = "on 0\nas\n" if on else "standby 0\n"
        if self.dry_run:
            LOG.info("DRY-RUN CEC %s: %r -> %s", runtime.config.ref, stdin, cec_command(runtime.config))
            runtime.power_on = on
            return
        completed = subprocess.run(  # noqa: S603 — lista fixa, sem shell
            cec_command(runtime.config),
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            check=False,
        )
        if completed.returncode:
            raise OSError(f"cec-client saiu {completed.returncode}: {completed.stdout[-300:]}")
        runtime.power_on = on
        LOG.info("%s: TV %s", runtime.config.ref, "acordada" if on else "em standby")


def _parse_datetime(value) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("next_transition_at inválido") from exc
    if parsed.tzinfo is None:
        raise ValueError("next_transition_at precisa ter fuso horário")
    return parsed.astimezone(UTC)


def doctor(config: PlayerConfig, *, dry_run: bool = False) -> bool:
    ok = True
    for binary in (config.chromium, "cec-client"):
        found = shutil.which(binary)
        if not found and not dry_run:
            LOG.error("não encontrei %s no PATH", binary)
            ok = False
        else:
            LOG.info("%s: %s", binary, found or "ignorado no dry-run")
    player = Player(config, dry_run=dry_run)
    for screen in config.screens:
        if not Path(screen.cec_adapter).exists() and not dry_run:
            LOG.error("%s: adaptador CEC não existe: %s", screen.ref, screen.cec_adapter)
            ok = False
        try:
            intent = player.fetch_intent(screen)
            LOG.info("%s: servidor respondeu modo=%s", screen.ref, intent["mode"])
        except Exception as exc:  # diagnóstico precisa listar todas as falhas
            LOG.error("%s: endpoint de controle falhou: %s", screen.ref, exc)
            ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(args.config)
    except ValueError as exc:
        parser.error(str(exc))
    if args.doctor:
        return 0 if doctor(config, dry_run=args.dry_run) else 1
    player = Player(config, dry_run=args.dry_run)
    try:
        player.start_browsers()
        while True:
            player.tick()
            if args.once:
                break
            time.sleep(config.poll_seconds)
    except KeyboardInterrupt:
        LOG.info("encerrando")
    finally:
        player.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
