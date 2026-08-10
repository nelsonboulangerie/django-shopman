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

from django.core.management.base import BaseCommand, CommandError

#: Corpo padrão quando não se aponta um anúncio real.
DEFAULT_BODY = "Teste do Shopman: se você recebeu isto, o transporte está de pé."


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
            "--send",
            action="store_true",
            help="Envia DE VERDADE. Sem esta flag o comando só mostra o que sairia.",
        )

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
            context={"body": body, "action_url": link, "cta": "Garanta o seu:"},
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
