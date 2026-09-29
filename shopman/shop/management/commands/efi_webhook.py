"""Garante que a Efí notifica o Pix na URL canônica DESTE deployment.

Uso:
    manage.py efi_webhook                 # confere e, se divergir, cadastra
    manage.py efi_webhook --check         # só confere; não escreve na Efí
    manage.py efi_webhook --soft          # falha visível (stderr + log) sem sair com erro
    manage.py efi_webhook --public-base https://api.exemplo.com.br

Por que existe: o webhook do Pix é cadastrado POR CHAVE na Efí, fora do nosso
banco e fora do spec. O de testes ficou apontando para um domínio que deixou de
existir (``api.staging.nelsonboulangerie.com.br``), e nada acusou: a cobrança
nasce, o cliente paga, a confirmação nunca chega. Sem console no app vivo, o
único lugar que roda código com as credenciais do deployment a cada versão é o
job de release — então é lá que este comando mora, idempotente.

A URL canônica é ``https://<SHOPMAN_OPERATOR_API_HOST>/api/webhooks/efi/pix/
?token=<EFI_WEBHOOK_TOKEN>&ignorar=``:

* ``?token=`` é a autenticação do webhook (a Efí não manda cabeçalho próprio;
  sem proxy mTLS na DO, é o único segredo — ver ``shopman/shop/webhooks/efi.py``);
* ``&ignorar=`` porque a Efí acrescenta ``/pix`` ao FIM da URL cadastrada. Sem
  ele, a notificação chegaria com ``token=<segredo>/pix`` e todo webhook seria
  recusado com 401. Com ele, o acréscimo cai no parâmetro descartável
  (``ignorar=/pix``) — é o mecanismo documentado pela própria Efí;
* o cadastro vai com ``x-skip-mtls-checking: true`` (ver
  ``payment_efi.register_pix_webhook``).

Só age quando o adapter EFETIVO do Pix é a Efí (``Shop.integrations`` antes do
settings, igual à cobrança). Com o simulador, não há o que cadastrar.

O segredo nunca sai inteiro na saída: o token vira ``***``.
"""

from __future__ import annotations

import logging
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

logger = logging.getLogger(__name__)

EFI_PIX_ADAPTER_PATH = "shopman.shop.adapters.payment_efi"


def canonical_webhook_url(public_base: str, token: str) -> str:
    base = public_base.rstrip("/")
    query = urlencode({"token": token})
    return f"{base}{reverse('webhooks:efi-pix-webhook')}?{query}&ignorar="


def _redact(text: object, token: str) -> str:
    text = str(text or "")
    if token:
        for form in {quote(token, safe=""), urlencode({"token": token})[len("token="):], token}:
            text = text.replace(form, "***")
    return text


def _default_public_base() -> str:
    host = str(getattr(settings, "SHOPMAN_OPERATOR_API_HOST", "") or "").strip()
    return f"https://{host}" if host else ""


class Command(BaseCommand):
    help = "Confere e cadastra na Efí o webhook do Pix com a URL canônica deste deployment."

    def add_arguments(self, parser):
        parser.add_argument(
            "--public-base",
            default="",
            help="Base pública HTTPS da API (default: https://<SHOPMAN_OPERATOR_API_HOST>).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Só confere: relata a divergência sem cadastrar.",
        )
        parser.add_argument(
            "--soft",
            action="store_true",
            help="Falha visível (stderr + log de erro) sem código de saída — para o job de release.",
        )

    def handle(self, *args, **options):
        try:
            self._run(options)
        except CommandError as exc:
            if not options.get("soft"):
                raise
            logger.error("efi_webhook: %s", exc)
            self.stderr.write(self.style.ERROR(f"efi_webhook: {exc}"))

    def _run(self, options) -> None:
        from shopman.shop.adapters import get_adapter, payment_efi

        adapter = get_adapter("payment", method="pix")
        adapter_path = str(getattr(adapter, "__name__", "") or adapter or "")
        if adapter_path != EFI_PIX_ADAPTER_PATH:
            self.stdout.write(
                f"Pix não usa a Efí neste deployment ({adapter_path or 'sem adapter'}): nada a cadastrar."
            )
            return

        config = getattr(settings, "SHOPMAN_EFI", {}) or {}
        webhook = getattr(settings, "SHOPMAN_EFI_WEBHOOK", {}) or {}
        token = str(webhook.get("webhook_token") or "").strip()
        pix_key = str(config.get("pix_key") or "").strip()
        public_base = str(options.get("public_base") or "").strip() or _default_public_base()
        environment = "homologação" if config.get("sandbox", True) else "produção"

        missing = [
            name
            for name, value in (
                ("EFI_WEBHOOK_TOKEN", token),
                ("EFI_PIX_KEY", pix_key),
                ("SHOPMAN_OPERATOR_API_HOST (ou --public-base)", public_base),
            )
            if not value
        ]
        if missing:
            raise CommandError(
                "Pix aponta para a Efí, mas o webhook não pode ser cadastrado: falta "
                + ", ".join(missing)
                + ". Sem webhook, o Pix pago não confirma o pedido sozinho."
            )
        if not public_base.startswith("https://"):
            raise CommandError(f"A base pública do webhook precisa ser HTTPS (recebido: {public_base}).")

        desired = canonical_webhook_url(public_base, token)
        shown = _redact(desired, token)

        try:
            current = payment_efi.get_pix_webhook(pix_key)
        except Exception as exc:
            raise CommandError(
                f"Efí ({environment}) não respondeu à consulta do webhook do Pix: "
                f"{_redact(exc, token)} {_redact(getattr(exc, 'efi_error_body', ''), token)}".strip()
            ) from exc

        if current == desired:
            self.stdout.write(self.style.SUCCESS(f"Efí ({environment}): webhook do Pix já cadastrado em {shown}"))
            return

        before = _redact(current, token) if current else "nenhum"
        if options.get("check"):
            raise CommandError(
                f"Efí ({environment}): webhook do Pix diverge — cadastrado: {before}; esperado: {shown}."
            )

        try:
            payment_efi.register_pix_webhook(pix_key, desired)
            confirmed = payment_efi.get_pix_webhook(pix_key)
        except Exception as exc:
            raise CommandError(
                f"Efí ({environment}) recusou o cadastro do webhook do Pix: "
                f"{_redact(exc, token)} {_redact(getattr(exc, 'efi_error_body', ''), token)}".strip()
            ) from exc

        if confirmed != desired:
            raise CommandError(
                f"Efí ({environment}) aceitou o cadastro, mas a releitura devolveu "
                f"{_redact(confirmed, token) if confirmed else 'nenhum'}; esperado: {shown}."
            )

        self.stdout.write(
            self.style.SUCCESS(f"Efí ({environment}): webhook do Pix cadastrado em {shown} (antes: {before}).")
        )
