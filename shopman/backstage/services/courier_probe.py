"""Sonda da central de entregas pelo Admin: a mesma sonda do console, no processo que tem os segredos.

## Por que existe

A rodada de homologação da TaOn (#2489) depende de duas ferramentas de linha de
comando: ``courier_machine_probe`` (lê a conta, os avisos e as corridas, e
escreve só com ``--write`` e o id repetido) e ``machine_register_webhook``.
Nenhuma das duas roda pelo console da DigitalOcean: o console não recebe as
variáveis ``SECRET``, então a credencial chega vazia (o mesmo motivo do botão de
e-mail do Diagnóstico), e o token de deploy não tem permissão de ``exec``.

O processo que tem a credencial é o que serve o Admin. Por isso a sonda sai
daqui, chamando os MESMOS comandos com ``call_command``: a máscara do laudo
(nada de nome, telefone, placa, endereço ou token) é a deles, e não uma cópia.

## O que ela NÃO faz

Não escreve na TaOn: só lê a conta, os avisos cadastrados e as corridas. As
escritas (cancelar, agrupar, tirar parada, impulsionar, cadastrar avisos) pedem
prévia, confirmação na página e registro de cada chamada, e chegam num passo
próprio.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from django.core.management import call_command
from django.core.management.base import CommandError

logger = logging.getLogger(__name__)

#: Mais que isto e a requisição do Admin passa do tempo: cada corrida são dez leituras.
MAX_RIDES = 3

@dataclass(frozen=True)
class CourierProbeResult:
    ok: bool
    report: str


def _run(command: str, *args, **options) -> tuple[bool, str]:
    out = io.StringIO()
    try:
        call_command(command, *args, stdout=out, stderr=out, **options)
    except CommandError as exc:
        text = out.getvalue()
        return False, f"{text}\n{exc}".strip()
    except Exception as exc:  # o erro é o resultado da sonda
        logger.warning("courier_probe: %s falhou", command, exc_info=True)
        return False, f"{out.getvalue()}\n{type(exc).__name__}: {exc}".strip()
    return True, out.getvalue().strip()


def rides_from(text: str) -> list[str]:
    return [part.strip() for part in str(text or "").replace(";", ",").split(",") if part.strip()]


def read(*, rides: list[str], window: int = 0, recent: int = 0) -> CourierProbeResult:
    """Só leitura: conta, avisos cadastrados, categorias, janela e corridas."""
    ok, report = _run(
        "courier_machine_probe", ride=list(rides)[:MAX_RIDES], window=int(window or 0), recent=int(recent or 0),
    )
    return CourierProbeResult(ok=ok, report=report)


def webhooks(public_base: str) -> CourierProbeResult:
    """Só leitura: os avisos cadastrados na TaOn, com o token mascarado."""
    ok, report = _run("machine_register_webhook", public_base, list=True)
    return CourierProbeResult(ok=ok, report=report)


__all__ = ["CourierProbeResult", "MAX_RIDES", "read", "rides_from", "webhooks"]
