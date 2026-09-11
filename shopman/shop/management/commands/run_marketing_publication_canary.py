"""Inspect or execute exactly one approved public Marketing consequence."""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

PUBLIC_PLATFORMS = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "google_business": "Perfil da Empresa no Google",
}
PUBLICATION_FORMAT_LABELS = {
    "story": "Stories",
    "feed": "Feed",
    "standard": "atualização padrão",
}
OUTBOX_STATE_LABELS = {
    "pending": "pendente",
    "claimed": "reservada",
    "dispatched": "despachada",
    "dead_letter": "interrompida",
}
TARGET_STATE_LABELS = {
    "queued": "em fila",
    "claimed": "reservado",
    "accepted_unconfirmed": "aceito, aguardando confirmação",
    "confirmed": "confirmado",
    "unknown": "resultado incerto",
    "failed_retryable": "falhou, pode ser repetido com segurança",
    "failed_terminal": "falhou sem repetição automática",
    "cancelled": "cancelado",
}
OUTCOME_LABELS = {
    "confirmed": "confirmado",
    "accepted_unconfirmed": "aceito, aguardando confirmação",
    "unknown": "resultado incerto",
    "failed_retryable": "falhou, pode ser repetido com segurança",
    "failed_terminal": "falhou sem repetição automática",
}


class Command(BaseCommand):
    help = (
        "Inspeciona ou executa uma única postagem pública aprovada, "
        "sem drenar filas históricas."
    )

    def add_arguments(self, parser):
        reference = parser.add_mutually_exclusive_group(required=True)
        reference.add_argument(
            "--outbox-ref",
            help="Referência UUID exata da consequência pública já aprovada.",
        )
        reference.add_argument(
            "--announcement-id",
            type=int,
            help="Atalho somente de preflight; resolve a lane pelo número da tela.",
        )
        parser.add_argument(
            "--platform",
            required=True,
            choices=tuple(PUBLIC_PLATFORMS),
            help="Plataforma pública esperada; divergência bloqueia a execução.",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Cruza a fronteira externa. O default apenas inspeciona.",
        )
        parser.add_argument(
            "--confirm",
            default="",
            help="Frase exata exibida no preflight; obrigatória com --execute.",
        )
        parser.add_argument("--worker-id", default="marketing-publication-canary")
        parser.add_argument("--lease-seconds", type=int, default=60)

    def handle(self, *args, **options):
        from shopman.shop.models import DeliveryTarget, MarketingOutbox
        from shopman.shop.services.marketing_artifacts import (
            resolve_approved_dispatch_artifact,
        )
        from shopman.shop.services.marketing_delivery_runtime import delivery_provider

        platform = str(options["platform"])
        outbox_query = MarketingOutbox.objects.select_related(
            "announcement", "artifact", "command"
        )
        if options.get("announcement_id") is not None:
            if options["execute"]:
                raise CommandError(
                    "Use --announcement-id no preflight e execute com o --outbox-ref exibido."
                )
            matches = list(
                outbox_query.filter(
                    announcement_id=options["announcement_id"],
                    platform=platform,
                )[:2]
            )
            if len(matches) != 1:
                raise CommandError(
                    "O anúncio não possui exatamente uma consequência nessa plataforma."
                )
            outbox = matches[0]
        else:
            raw_ref = str(options["outbox_ref"] or "").strip()
            try:
                exact_ref = uuid.UUID(raw_ref)
            except (TypeError, ValueError, AttributeError) as exc:
                raise CommandError("--outbox-ref precisa ser um UUID válido.") from exc
            try:
                outbox = outbox_query.get(ref=exact_ref)
            except MarketingOutbox.DoesNotExist as exc:
                raise CommandError("A consequência aprovada não foi encontrada.") from exc
        if outbox.platform != platform:
            raise CommandError(
                "A plataforma informada diverge da consequência aprovada; nada foi feito."
            )

        try:
            artifact = resolve_approved_dispatch_artifact(
                outbox.artifact,
                platform=platform,
            )
        except Exception as exc:
            code = getattr(exc, "code", "invalid_approved_artifact")
            raise CommandError(
                f"O conteúdo aprovado não pode ser publicado com segurança ({code})."
            ) from None

        publication_format = str(
            dict(artifact.provider_fields).get("publication_format") or ""
        )
        expected_confirmation = f"PUBLICAR {platform} {outbox.ref}"
        provider_ready = delivery_provider(platform) is not None
        target = DeliveryTarget.objects.filter(outbox=outbox).first()

        self.stdout.write(self.style.MIGRATE_HEADING("Canário público isolado"))
        self.stdout.write(f"  consequência : {outbox.ref}")
        self.stdout.write(f"  anúncio      : {outbox.announcement_id}")
        self.stdout.write(f"  plataforma   : {PUBLIC_PLATFORMS[platform]}")
        self.stdout.write(
            "  formato      : "
            f"{PUBLICATION_FORMAT_LABELS.get(publication_format, publication_format)}"
        )
        self.stdout.write("  alcance      : 1 postagem pública")
        self.stdout.write(
            f"  estado fila  : {_state_label(OUTBOX_STATE_LABELS, outbox.state)}"
        )
        self.stdout.write(
            "  estado destino: "
            f"{_state_label(TARGET_STATE_LABELS, target.state) if target is not None else 'ainda não materializado'}"
        )
        self.stdout.write(
            f"  mídia        : {_media_summary(artifact.image_url)}"
        )
        self.stdout.write(
            f"  integração   : {'pronta' if provider_ready else 'bloqueada'}"
        )
        self.stdout.write(f"  confirmação  : {expected_confirmation}")

        if not options["execute"]:
            self.stdout.write("Nada foi publicado. Revise o preflight antes de executar.")
            self.stdout.write(
                "Comando exato: python manage.py run_marketing_publication_canary "
                f"--outbox-ref {outbox.ref} --platform {platform} --execute "
                f"--confirm \"{expected_confirmation}\""
            )
            return None

        _require_isolated_runtime()
        if str(options["confirm"] or "") != expected_confirmation:
            raise CommandError(
                "Confirmação divergente. Copie exatamente a frase exibida no preflight."
            )
        if not provider_ready:
            raise CommandError(
                "A plataforma não está pronta: confira flag, identificadores e credencial."
            )

        worker_id = str(options["worker_id"] or "marketing-publication-canary")
        lease_seconds = max(10, min(int(options["lease_seconds"]), 15 * 60))
        now = timezone.now()
        if outbox.state == MarketingOutbox.State.PENDING:
            from shopman.shop.services.marketing_outbox import claim_due, publish_claim

            claimed = claim_due(
                worker_id=worker_id,
                now=now,
                limit=1,
                lease_seconds=lease_seconds,
                outbox_refs=(str(outbox.ref),),
            )
            if len(claimed) != 1 or claimed[0].ref != outbox.ref:
                raise CommandError(
                    "A consequência não está vencida/elegível ou foi reservada por outro processo."
                )
            outbox = publish_claim(outbox.ref, worker_id=worker_id, now=now)
        elif outbox.state != MarketingOutbox.State.DISPATCHED:
            raise CommandError(
                f"A consequência está em estado não executável ({outbox.state})."
            )

        # The outbox commit creates one Directive. Its canonical on-commit
        # handler stages only this outbox into the protected target ledger.
        target = DeliveryTarget.objects.filter(outbox=outbox).first()
        if target is None:
            raise CommandError(
                "A consequência foi despachada, mas o alvo protegido não foi materializado."
            )
        if target.state != DeliveryTarget.State.QUEUED:
            self.stdout.write(
                self.style.WARNING(
                    "Nenhuma nova chamada: o alvo já está "
                    f"{_state_label(TARGET_STATE_LABELS, target.state)}."
                )
            )
            return None

        from shopman.shop.services.marketing_delivery_attempts import (
            deterministic_attempt_token,
            execute_approved_target,
        )
        from shopman.shop.services.marketing_delivery_worker import claim_due_targets

        claims = claim_due_targets(
            worker_id=worker_id,
            now=timezone.now(),
            limit=1,
            lease_seconds=lease_seconds,
            platforms=(platform,),
            outbox_refs=(str(outbox.ref),),
        )
        if len(claims.targets) != 1 or claims.targets[0].ref != target.ref:
            target.refresh_from_db()
            raise CommandError(
                "O alvo exato não cruzou o último gate de fatos/estado; "
                "situação="
                f"{_state_label(TARGET_STATE_LABELS, target.state)}, "
                "código técnico="
                f"{target.last_error_code or 'não informado'}."
            )

        token = deterministic_attempt_token(
            target.ref,
            worker_id=worker_id,
            now=timezone.now(),
        )
        execution = execute_approved_target(
            target.ref,
            provider=delivery_provider(platform),
            idempotency_token=token,
            worker_id=worker_id,
            now=timezone.now(),
        )
        execution.target.refresh_from_db()
        self.stdout.write(
            "  resultado    : "
            f"{_state_label(OUTCOME_LABELS, execution.attempt.outcome_kind)}"
        )
        self.stdout.write(
            "  estado final : "
            f"{_state_label(TARGET_STATE_LABELS, execution.target.state)}"
        )
        if execution.target.provider_receipt_ref:
            self.stdout.write(
                f"  comprovante  : {execution.target.provider_receipt_ref}"
            )
        if execution.provider_called:
            self.stdout.write(
                self.style.SUCCESS(
                    "A plataforma recebeu exatamente uma tentativa de publicação."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING("Replay seguro: nenhuma nova chamada externa.")
            )
        return None


def _require_isolated_runtime() -> None:
    if not getattr(settings, "SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED", False):
        raise CommandError("O canário público está desligado na configuração.")
    if getattr(settings, "SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED", False):
        raise CommandError(
            "Desligue o consumer global da outbox antes do canário isolado."
        )
    if getattr(settings, "SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED", False):
        raise CommandError(
            "Desligue o consumer global de entrega antes do canário isolado."
        )


def _media_summary(value: str) -> str:
    text = str(value or "")
    if not text:
        return "sem mídia"
    try:
        parsed = urlsplit(text)
    except ValueError:
        return "URL inválida"
    return f"HTTPS em {parsed.hostname}" if parsed.scheme == "https" else "URL não pública"


def _state_label(labels: dict[str, str], value: object) -> str:
    state = str(value or "")
    return labels.get(state, state or "não informado")
