"""Pré-visualiza ou envia um teste Marketing pela mesma lane sandbox da API.

Não aceita telefone, subscriber, audience rules nem backend livre. O operador
escolhe uma ``target_ref`` verificada na configuração e, para enviar, informa um
ator com capability própria e uma chave idempotente. Sem ``--send`` é dry-run.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Testa um anúncio em destino sandbox verificado; dry-run por padrão."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-ref",
            required=True,
            help="Ref segura de SHOPMAN_MARKETING_TEST_TARGETS_JSON; nunca um telefone.",
        )
        parser.add_argument("--sku", default="", help="SKU opcional para preencher variáveis.")
        parser.add_argument("--body", default="", help="Texto opcional do artifact de teste.")
        parser.add_argument(
            "--actor",
            default="",
            help="Username staff com send_marketing_test; obrigatório com --send.",
        )
        parser.add_argument(
            "--idempotency-key",
            default="",
            help="Chave única de 16–128 caracteres; obrigatória com --send.",
        )
        parser.add_argument(
            "--send",
            action="store_true",
            help="Executa na lane sandbox. Sem esta flag nada sai.",
        )

    def handle(self, *args, **options):
        from shopman.shop.services import campaign

        target_ref = str(options["target_ref"] or "").strip()
        targets = {item["ref"]: item for item in campaign.marketing_test_target_options()}
        target = targets.get(target_ref)
        if target is None:
            available = ", ".join(sorted(targets)) or "nenhum"
            raise CommandError(
                f"Destino sandbox não autorizado. Refs disponíveis: {available}."
            )

        self.stdout.write(self.style.MIGRATE_HEADING("Teste Marketing isolado"))
        self.stdout.write(f"  destino    : {target['label']} ({target_ref})")
        self.stdout.write(f"  transporte : {target['backend']} sandbox")
        self.stdout.write("  alcance    : exatamente 1")
        self.stdout.write(f"  SKU        : {str(options['sku'] or '').strip() or '(amostra)'}")

        if not options["send"]:
            self.stdout.write("Nada foi enviado. Use --send com ator e idempotency key.")
            return

        username = str(options["actor"] or "").strip()
        if not username:
            raise CommandError("--actor é obrigatório com --send.")

        from django.contrib.auth import get_user_model

        actor = get_user_model().objects.filter(
            username=username,
            is_active=True,
            is_staff=True,
        ).first()
        if actor is None:
            raise CommandError("Ator staff ativo não encontrado.")

        try:
            outcome = campaign.send_test(
                target_ref,
                actor=actor,
                idempotency_key=str(options["idempotency_key"] or ""),
                sku=str(options["sku"] or ""),
                body=str(options["body"] or ""),
            )
        except campaign.MarketingTestThrottled as exc:
            raise CommandError(
                f"Limite de testes atingido; tente em {exc.retry_after}s."
            ) from None
        except campaign.CampaignError as exc:
            raise CommandError(str(exc)) from None

        self.stdout.write(f"  receipt    : {outcome.receipt_ref}")
        self.stdout.write(f"  estado     : {outcome.state}")
        if outcome.replayed:
            self.stdout.write("  repetição  : receipt existente; nenhum segundo envio")
        if outcome.accepted:
            self.stdout.write(self.style.SUCCESS(
                "Sandbox aceitou; isso ainda não confirma entrega no aparelho."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Sandbox não confirmou aceite. Consulte o receipt; não repita unknown."
            ))
