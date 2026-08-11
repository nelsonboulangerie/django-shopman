"""Enviar UM anúncio de teste para UM telefone, de verdade.

Existe porque "o painel diz enviado" e "o celular vibrou" são fatos diferentes, e só o
segundo prova que o transporte funciona ponta a ponta. O caminho normal de campanha
resolve audiência a partir de consentimento e mapeamento de subscriber; para provar o
TRANSPORTE isso é ruído — este comando fala direto com o adapter e conta exatamente o
que ele respondeu.

**Não é porta dos fundos do consentimento.** Um telefone por execução, nomeado na linha
de comando por quem tem acesso ao servidor, e envio real só com ``--send``. Não resolve
audiência, não lê `CommunicationConsent`, e por isso mesmo não serve para alcançar
cliente: serve para o dono testar o próprio número.

## O que funciona hoje — medido em 2026-08-10, não suposto

**Nenhum transporte entrega neste momento.** O comando está certo; as credenciais não.

· **sms** (Comtele) — chave e rota presentes (`.env` local e staging), mas a API devolve
  **HTTP 500** com um `message` opaco. Não é este caminho: o remetente de OTP
  (`otp_sms_comtele`), que usa payload idêntico, falha igual. É a conta/chave/rota na
  Comtele que precisa de atenção.
· **manychat** (WhatsApp) — token só no staging. E `_resolve_subscriber` aceita apenas
  `subscriber_id` numérico ou um resolver configurado (não há): telefone com `+` falha
  com "Could not resolve subscriber". Passe o subscriber_id do ManyChat se o tiver.
· **whatsapp-meta** — `WHATSAPP_PHONE_NUMBER_ID`/`ACCESS_TOKEN` ausentes; inerte.

Quando qualquer um destes três for resolvido, este comando entrega sem mudança de
código — é por isso que ele existe: separar "o software está errado" de "a credencial
está errada", que são consertos de pessoas diferentes.

## Como usar

Ver o que sairia, sem enviar nada:

    python manage.py send_test_announcement --phone "+5543984049009"

Enviar de verdade (staging, ou local com a trava aberta):

    python manage.py send_test_announcement --phone "+5543984049009" --send
    SHOPMAN_SMS_ALLOW_IN_DEBUG=true python manage.py send_test_announcement \\
        --phone "+5543984049009" --send

⚠️ Em DEBUG os adapters externos são **inertes** por padrão (`_external.inert`), então
localmente o comando relata "inerte" em vez de enviar — é a trava que impede um reseed
de disparar SMS para número de verdade. Abrir a trava é explícito, por isso o comando
diz na cara quando ela está fechada.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

#: Corpo padrão quando não se aponta um anúncio real.
DEFAULT_BODY = "Teste do Shopman: se você recebeu isto, o transporte está de pé."


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Envia um anúncio de teste para UM telefone (SMS ou WhatsApp), de verdade com --send."

    def add_arguments(self, parser):
        parser.add_argument(
            "--phone",
            required=True,
            help='Telefone único, E.164. Ex: "+5543984049009". Para o WhatsApp via '
                 "ManyChat, aceita também o subscriber_id numérico.",
        )
        parser.add_argument(
            "--channel",
            default="sms",
            # Os nomes são os do registro real (`SHOPMAN_NOTIFICATION_ADAPTERS`), não
            # apelidos: "whatsapp" não é adapter, "manychat" é. Um nome por coisa.
            choices=["sms", "manychat", "console", "email"],
            help="Transporte, pelo nome do adapter. 'sms' = Comtele. "
                 "'manychat' = WhatsApp via ManyChat (exige subscriber_id).",
        )
        parser.add_argument(
            "--announcement",
            type=int,
            default=None,
            help="pk de um Announcement real, para enviar o texto DELE. "
                 "Sem isto, usa um corpo de teste.",
        )
        parser.add_argument(
            "--body",
            default="",
            help="Texto avulso, quando você quer escolher a mensagem na mão.",
        )
        parser.add_argument(
            "--sku",
            default="",
            help="SKU real para preencher as variáveis do template (nome, quantidade, "
                 "link do botão). Sem ele o teste não prova nada sobre um template "
                 "aprovado, porque as variáveis chegariam vazias.",
        )
        parser.add_argument(
            "--name",
            default="",
            help="Primeiro nome de quem recebe, para o {{customer_name}} do template.",
        )
        parser.add_argument(
            "--send",
            action="store_true",
            help="Envia DE VERDADE. Sem esta flag o comando só mostra o que sairia.",
        )

    def _template_fields(self, options) -> dict:
        """As variáveis que o template aprovado espera, com valores REAIS quando dá.

        `available_qty` sai da disponibilidade de verdade: um teste com número inventado
        validaria a fiação e mentiria sobre o conteúdo.
        """
        sku = str(options.get("sku") or "").strip()
        fields = {
            "customer_name": str(options.get("name") or "").strip(),
            "product_name": "",
            "product_sku": sku,
            "available_qty": "",
        }
        if not sku:
            return fields

        try:
            from shopman.shop.projections import catalog_context

            product = catalog_context.get_product(sku)
            fields["product_name"] = getattr(product, "name", "") or sku
        except Exception:
            logger.warning("send_test: nome do produto não resolveu sku=%s", sku, exc_info=True)
            fields["product_name"] = sku

        try:
            from shopman.shop.handlers.campaign import _available_qty

            qty = _available_qty(sku)
            fields["available_qty"] = str(qty) if qty else ""
        except Exception:
            # Fica vazio: o teste mostra "(vazio)" e o gestor vê que a mensagem sairia
            # sem número, em vez de sair com um número inventado.
            logger.warning("send_test: quantidade não resolveu sku=%s", sku, exc_info=True)

        try:
            from shopman.shop.services import storefront_links

            fields["link"] = storefront_links.product_url(sku)
        except Exception:
            logger.warning("send_test: link do produto não resolveu sku=%s", sku, exc_info=True)
        return fields

    def handle(self, *args, **options):
        from shopman.shop.adapters import _external
        from shopman.shop.notifications import get_backend, notify

        phone = str(options["phone"]).strip()
        if not phone:
            raise CommandError("--phone é obrigatório.")
        if "," in phone or " " in phone:
            # Um telefone por execução, de propósito: este comando não é ferramenta de
            # disparo em lote, e aceitar lista o transformaria numa.
            raise CommandError("Um telefone por execução. Este comando não faz lote.")

        channel = options["channel"]
        body, source = self._resolve_body(options)
        link = ""
        # As MESMAS chaves que o caminho real manda. Um teste que mande menos prova só
        # que o transporte responde — não que o template aprovado renderiza.
        fields = self._template_fields(options)

        announcement_pk = options["announcement"]
        if announcement_pk:
            from shopman.shop.models import Announcement

            announcement = Announcement.objects.filter(pk=announcement_pk).first()
            if announcement is None:
                raise CommandError(f"Announcement {announcement_pk} não encontrado.")
            link = (announcement.content or {}).get("link", "") or ""

        adapter = get_backend(channel)
        if adapter is None:
            raise CommandError(
                f"O transporte '{channel}' não está registrado neste ambiente. "
                "Registrados: ver SHOPMAN_NOTIFICATION_ADAPTERS."
            )

        probe = getattr(adapter, "is_available", None)
        available = True if probe is None else bool(probe())

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("O que vai sair"))
        self.stdout.write(f"  telefone   : {phone}")
        self.stdout.write(f"  transporte : {channel}")
        self.stdout.write(f"  credencial : {'ok' if available else 'AUSENTE — não vai entregar'}")
        self.stdout.write(f"  texto ({source}): {body}")
        if link:
            self.stdout.write(f"  link       : {link}")
        self.stdout.write("  variáveis do template (viram campos no ManyChat):")
        for key, value in fields.items():
            shown = value if value else "(vazio — o template renderiza sem)"
            self.stdout.write(f"    {key} = {shown}")

        # A trava de DEBUG é o motivo mais comum de "mandei e não chegou". Dizer antes.
        if _external.inert(f"SHOPMAN_{channel.upper()}_ALLOW_IN_DEBUG"):
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "  ⚠️  A trava de adapters externos está FECHADA neste processo "
                "(DEBUG sem opt-in, ou seed suprimindo).\n"
                f"      O adapter vai logar e devolver sucesso SEM enviar nada.\n"
                f"      Para enviar de verdade daqui: "
                f"SHOPMAN_{channel.upper()}_ALLOW_IN_DEBUG=true"
            ))

        if channel == "manychat" and not phone.lstrip("+").isdigit():
            self.stdout.write(self.style.WARNING(
                "  ⚠️  ManyChat resolve subscriber por ID numérico; telefone não resolve "
                "sem resolver configurado. Provavelmente vai falhar."
            ))

        if not options["send"]:
            self.stdout.write("")
            self.stdout.write("Nada foi enviado. Repita com --send para enviar de verdade.")
            return

        self.stdout.write("")
        result = notify(
            event="announcement_published",
            recipient=phone,
            context={
                "body": body,
                "action_url": link or fields.get("link", ""),
                "cta": "Garanta o seu:",
                **fields,
            },
            backend=channel,
        )

        if getattr(result, "success", False):
            self.stdout.write(self.style.SUCCESS(
                f"  ✅ o adapter '{channel}' aceitou o envio (id: {result.message_id})."
            ))
            self.stdout.write(
                "     Aceito pelo provedor ≠ entregue no aparelho. Confira o celular; "
                "se não chegar, o log do provedor é a próxima parada."
            )
        else:
            self.stdout.write(self.style.ERROR(
                f"  ❌ o adapter '{channel}' recusou: {result.error}"
            ))

    def _resolve_body(self, options) -> tuple[str, str]:
        """O texto que vai sair, e de onde ele veio."""
        if options["body"]:
            return options["body"], "avulso"

        if options["announcement"]:
            from shopman.shop.models import Announcement

            announcement = Announcement.objects.filter(pk=options["announcement"]).first()
            if announcement is not None and announcement.body:
                return announcement.body, f"anúncio {announcement.pk}"

        return DEFAULT_BODY, "padrão"
