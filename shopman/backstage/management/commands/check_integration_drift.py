"""Configuração degradada vira ``OperatorAlert`` — a prontidão deixa de ser só *pull*.

``build_provider_readiness`` já sabe dizer que o Pix está no simulador, que a
NFC-e aponta para homologação e que ninguém entrega o código de login. Essa
verdade existe desde sempre e mora numa tela: ``/admin/diagnostics/``. Ou seja,
o sistema sabia e esperava alguém perguntar.

Este comando é o irmão de ``check_directive_health``: mesma forma (varredura no
ciclo do ``maintenance_worker``, resultado vira alerta com debounce), aplicada à
configuração em vez da fila. A diferença entre "o sistema sabia e ninguém
perguntou" e "o sistema avisou" é este arquivo.

## A régua de severidade

O mesmo fato — "Pix em homologação" — é bug em produção e decisão consciente no
alpha. Um alerta que não separa os dois grita todo dia sobre uma escolha do dono
e ensina a ignorar o vermelho. Então a régua tem dois eixos:

* **onde estamos** (``shopman.shop.environment.is_production``):

  =====================  ================  ============  ==========
  instância              prontidão         severidade    janela
  =====================  ================  ============  ==========
  produção               ``error``         ``critical``  24 h
  produção               ``warning``       ``error``     24 h
  não-produção           ``error``         ``error``     24 h
  não-produção           ``warning``       ``warning``   7 dias
  =====================  ================  ============  ==========

  ``error`` da prontidão é *configuração insegura*; ``warning`` é *falta
  configuração*. Repare que a própria prontidão já vira a expectativa pelo
  ambiente (em staging, apontar para a NFC-e de **produção** é que é inseguro),
  então esta tabela não repete o julgamento dela — só decide o tom.

* **o que o dono já decidiu** — ``SHOPMAN_INTEGRATION_DRIFT_EXPECTED``, uma
  lista de ``provider`` cujo estado degradado é escolha registrada. Provedor
  listado nunca passa de ``warning`` e usa a janela longa. É a saída para a
  instância que se declara ``production`` e ainda assim mantém, de propósito, a
  NFC-e em homologação: o aviso vira um lembrete semanal em vez de um crítico
  diário, e continua existindo — silenciar de vez não é opção, porque a decisão
  de hoje é a surpresa de daqui a três meses.

## O dedupe

A identidade é ``(provider, lista de pendências)``. Consertar uma pendência de
três muda o conjunto e é fato novo, que merece aviso novo; o mesmo conjunto pela
segunda vez no mesmo dia não é. Como em ``check_catalog_visibility``, a checagem
usa ``active_only=False``: alerta já **reconhecido** também segura a janela.

## O vencimento dos certificados

A prontidão só sabe dizer que um certificado **já** venceu (``expired``) — e aí o
Pix já parou, ou as notas de compra já deixaram de chegar. O mesmo ciclo olha a
DATA de cada certificado conhecido (``known_certificates``: Efí e o e-CNPJ A1 de
Compras) e avisa antes, em marcos:

=========================  ============
faltam                     severidade
=========================  ============
30, 15 e 7 dias            ``warning``
3 dias ou menos, vencido   ``critical``
=========================  ============

Cada marco é UM alerta na vida daquele certificado: o dedupe é
``(provedor, data de vencimento, marco)``, sem janela de tempo. Renovar muda a
data e recomeça a contagem. O crítico sai por e-mail pelo caminho de sempre
(``critical_alerts``). Marco pulado (worker parado) não é recuperado: o aviso
que importa é o do marco em que se está.

Compras entra na leitura quando está ligada (``build_monitored_readiness``); o
PDV e a guarda de deploy continuam só com a prontidão do balcão.

Uso:
    python manage.py check_integration_drift
    python manage.py check_integration_drift --dry-run
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.shop.environment import is_production

logger = logging.getLogger(__name__)

ALERT_TYPE = "integration_config_drift"

#: Janela do dedupe quando o desvio é inesperado — um lembrete por dia.
UNEXPECTED_WINDOW_HOURS = 24

#: Janela quando o desvio é o estado esperado do ambiente (ou decisão registrada
#: em ``SHOPMAN_INTEGRATION_DRIFT_EXPECTED``) — um lembrete por semana.
EXPECTED_WINDOW_HOURS = 24 * 7

CERTIFICATE_ALERT_TYPE = "certificate_expiring"

#: Marcos de antecedência, em dias, com a severidade de cada um. O último marco
#: e o vencimento em si são críticos: é o que sai por e-mail.
CERTIFICATE_MILESTONES: tuple[tuple[int, str], ...] = (
    (3, "critical"),
    (7, "warning"),
    (15, "warning"),
    (30, "warning"),
)


def expected_providers() -> frozenset[str]:
    """Provedores cujo estado degradado é decisão registrada do deployment."""
    raw = getattr(settings, "SHOPMAN_INTEGRATION_DRIFT_EXPECTED", ()) or ()
    if isinstance(raw, str):
        raw = raw.split(",")
    return frozenset(str(item).strip() for item in raw if str(item).strip())


def grade(readiness, *, expected: frozenset[str]) -> tuple[str, int]:
    """Devolve ``(severidade, janela em horas)`` para uma prontidão degradada."""
    if readiness.provider in expected:
        return ("warning", EXPECTED_WINDOW_HOURS)
    if is_production():
        return ("critical" if readiness.status == "error" else "error", UNEXPECTED_WINDOW_HOURS)
    if readiness.status == "error":
        # Insegurança fora de produção continua sendo insegurança: é o adapter
        # simulado ligado sem DEBUG, ou a chave `sk_live_` num staging.
        return ("error", UNEXPECTED_WINDOW_HOURS)
    return ("warning", EXPECTED_WINDOW_HOURS)


def certificate_milestone(expires_at, *, now=None) -> tuple[str, str] | None:
    """Devolve ``(marco, severidade)`` para um certificado, ou ``None`` se ainda é cedo.

    O marco é ``"expired"`` depois do vencimento; antes, o menor marco que já
    foi alcançado (``"3"``, ``"7"``, ``"15"``, ``"30"``). Os dias contam pelo
    calendário local — quem lê o alerta pensa em "dia 10", não em horas UTC.
    """
    now = now or timezone.now()
    if now >= expires_at:
        return ("expired", "critical")
    days_left = (timezone.localtime(expires_at).date() - timezone.localtime(now).date()).days
    for days, severity in CERTIFICATE_MILESTONES:
        if days_left <= days:
            return (str(days), severity)
    return None


def certificate_message(certificate, *, milestone: str, now=None) -> str:
    """Qual certificado, quando vence, o que para e o que fazer."""
    now = now or timezone.now()
    expires_on = certificate.expires_on
    date_text = f"{expires_on:%d/%m/%Y}"
    if milestone == "expired":
        head = f"{certificate.label} venceu em {date_text}."
    else:
        days_left = (expires_on - timezone.localtime(now).date()).days
        if days_left <= 0:
            head = f"{certificate.label} vence hoje, {date_text}."
        elif days_left == 1:
            head = f"{certificate.label} vence amanhã, {date_text}."
        else:
            head = f"{certificate.label} vence em {date_text}, daqui a {days_left} dias."
    return f"{head} {certificate.consequence} {certificate.remedy}"


class Command(BaseCommand):
    help = "Alerta o operador sobre integrações em configuração insegura ou incompleta."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Só reporta, não alerta.")

    def handle(self, *args, **options):
        from shopman.backstage.services.integration_readiness import (
            build_monitored_readiness,
            known_certificates,
        )
        from shopman.shop.services.observability import operational_event

        providers = build_monitored_readiness(mode="runtime")
        degraded = [item for item in providers if not item.ready]
        expected = expected_providers()

        operational_event(
            "integration_drift.checked",
            degraded_count=len(degraded),
            degraded=[item.provider for item in degraded],
            production=is_production(),
        )
        self.stdout.write(
            "integration_drift: degraded="
            f"{','.join(item.provider for item in degraded) or '-'} "
            f"({len(degraded)} de {len(providers)})"
        )

        certificates = known_certificates()
        due = [
            (certificate, milestone)
            for certificate in certificates
            if (milestone := certificate_milestone(certificate.expires_at))
        ]
        self.stdout.write(
            "certificate_expiry: "
            + (", ".join(
                f"{certificate.provider}={certificate.expires_on.isoformat()}" for certificate in certificates
            ) or "-")
        )

        if options["dry_run"]:
            return

        for readiness in degraded:
            self._alert(readiness, expected=expected)
        for certificate, (milestone, severity) in due:
            self._certificate_alert(certificate, milestone=milestone, severity=severity)

    def _certificate_alert(self, certificate, *, milestone: str, severity: str) -> None:
        from shopman.shop.adapters import alert as alert_adapter
        from shopman.shop.services.observability import create_operator_alert

        dedupe_key = (
            f"{CERTIFICATE_ALERT_TYPE}:{certificate.provider}:"
            f"{certificate.expires_on.isoformat()}:{milestone}"
            # O fecho importa: a busca é por SUBSTRING, e sem ele a chave do
            # marco "3" estaria contida na do "30" — o crítico nunca sairia.
            ":fim"
        )
        # Sem janela de tempo: o marco é um só na vida do certificado. Todo alerta
        # desta chave nasce no máximo 30 dias antes do vencimento, então olhar a
        # partir daí cobre todos — reconhecidos e resolvidos inclusive.
        since = certificate.expires_at - timedelta(days=CERTIFICATE_MILESTONES[-1][0] + 1)
        if alert_adapter.recent_exists(
            CERTIFICATE_ALERT_TYPE, since, message_contains=dedupe_key, active_only=False
        ):
            return

        create_operator_alert(
            type=CERTIFICATE_ALERT_TYPE,
            severity=severity,
            message=certificate_message(certificate, milestone=milestone),
            dedupe_key=dedupe_key,
            debounce_minutes=CERTIFICATE_MILESTONES[-1][0] * 24 * 60,
            provider=certificate.provider,
            milestone=milestone,
        )

    def _alert(self, readiness, *, expected: frozenset[str]) -> None:
        from shopman.shop.adapters import alert as alert_adapter
        from shopman.shop.services.observability import create_operator_alert

        severity, window_hours = grade(readiness, expected=expected)
        dedupe_key = f"{ALERT_TYPE}:{readiness.provider}:{','.join(readiness.missing)}"

        cutoff = timezone.now() - timedelta(hours=window_hours)
        if alert_adapter.recent_exists(
            ALERT_TYPE, cutoff, message_contains=dedupe_key, active_only=False
        ):
            logger.info(
                "integration_drift: %s já avisado nesta janela (%s) — sem novo alerta.",
                readiness.provider,
                dedupe_key,
            )
            return

        create_operator_alert(
            type=ALERT_TYPE,
            severity=severity,
            message=self._message(readiness, expected=expected),
            dedupe_key=dedupe_key,
            debounce_minutes=window_hours * 60,
            provider=readiness.provider,
            readiness_status=readiness.status,
        )

    def _message(self, readiness, *, expected: frozenset[str]) -> str:
        head = (
            f"{readiness.label} está em configuração insegura"
            if readiness.status == "error"
            else f"{readiness.label} está sem configuração completa"
        )
        tail = (
            " Este estado está registrado como decisão da casa "
            "(SHOPMAN_INTEGRATION_DRIFT_EXPECTED) — o aviso é lembrete, não novidade."
            if readiness.provider in expected
            else " Conferir em /admin/diagnostics/."
        )
        return f"{head}: {readiness.message.rstrip('.')}.{tail}"
