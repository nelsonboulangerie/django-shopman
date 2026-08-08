"""As strings persistidas do rename — o que busca-e-substitui no código não alcança.

O rename da 0029 mexe em classes e tabelas. Estas seis coisas vivem em **linhas de
banco** e continuariam apontando para o nome antigo, silenciosamente:

1. permissões (`auth_permission.codename`) — renomeadas, nunca recriadas, para
   preservar o ID e portanto as concessões a grupos e usuários. É a armadilha que
   a ADR-011 §Negativas nomeou: permissão do Django depende de content type, e
   apagar-e-criar faz o grupo perder o acesso em silêncio;
2. `Directive.topic` — `broadcast.post`/`broadcast.notify` viram
   `announcement.publish`/`announcement.notify`; sem isto, directive pendente na
   fila nunca encontraria handler;
3. `Directive.dedupe_key` — o prefixo `broadcast:` vira `announcement:`. Há
   unique parcial sobre esta coluna, então a chave é semântica, não decoração;
4. `UserNotification.category` — `broadcast` vira `campaign`;
5. `UserNotification.action_url` — `/broadcast/posts/N/` vira
   `/campaign/announcements/N/`. **Estes links já foram enviados a celulares**, e
   a superfície tem a rota antiga como redirect (`nuxt.config.ts`), que continua
   valendo para o que já saiu;
6. `UserNotification.action_data` — a chave `broadcast_post_id` vira
   `announcement_id`.

O topic e a categoria usam valores exatos; o dedupe_key e o action_url usam
prefixo, porque carregam o pk no meio.

Refs ADR-020 §1, plano F2.
"""

from __future__ import annotations

from django.db import migrations

# (modelo antigo, modelo novo) — para as permissões default do Django.
MODEL_RENAMES = [
    ("posttemplate", "announcementtemplate"),
    ("broadcastrule", "campaign"),
    ("broadcastpost", "announcement"),
]
DEFAULT_ACTIONS = ("add", "change", "delete", "view")

TOPIC_RENAMES = [
    ("broadcast.post", "announcement.publish"),
    ("broadcast.notify", "announcement.notify"),
]


def forward(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Directive = apps.get_model("orderman", "Directive")
    UserNotification = apps.get_model("shop", "UserNotification")

    # 1. Permissões — renomeia, não recria. IDs preservados = grupos intactos.
    for old_model, new_model in MODEL_RENAMES:
        for action in DEFAULT_ACTIONS:
            Permission.objects.filter(codename=f"{action}_{old_model}").update(
                codename=f"{action}_{new_model}"
            )
    Permission.objects.filter(codename="manage_broadcast").update(
        codename="manage_campaigns", name="Pode revisar e publicar campanhas"
    )

    # 2. Topics de Directive — valor exato.
    for old_topic, new_topic in TOPIC_RENAMES:
        Directive.objects.filter(topic=old_topic).update(topic=new_topic)

    # 3. dedupe_key — prefixo (carrega o pk no meio).
    for directive in Directive.objects.filter(dedupe_key__startswith="broadcast:").iterator():
        directive.dedupe_key = "announcement:" + directive.dedupe_key[len("broadcast:") :]
        directive.save(update_fields=["dedupe_key"])

    # 4/5/6. Notificações do operador.
    UserNotification.objects.filter(category="broadcast").update(category="campaign")
    for note in UserNotification.objects.filter(
        action_url__startswith="/broadcast/posts/"
    ).iterator():
        note.action_url = "/campaign/announcements/" + note.action_url[len("/broadcast/posts/") :]
        note.save(update_fields=["action_url"])
    for note in UserNotification.objects.filter(
        action_data__has_key="broadcast_post_id"
    ).iterator():
        data = dict(note.action_data or {})
        data["announcement_id"] = data.pop("broadcast_post_id")
        note.action_data = data
        note.save(update_fields=["action_data"])


def backward(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Directive = apps.get_model("orderman", "Directive")
    UserNotification = apps.get_model("shop", "UserNotification")

    for old_model, new_model in MODEL_RENAMES:
        for action in DEFAULT_ACTIONS:
            Permission.objects.filter(codename=f"{action}_{new_model}").update(
                codename=f"{action}_{old_model}"
            )
    Permission.objects.filter(codename="manage_campaigns").update(
        codename="manage_broadcast", name="Pode revisar e publicar posts de broadcast"
    )

    for old_topic, new_topic in TOPIC_RENAMES:
        Directive.objects.filter(topic=new_topic).update(topic=old_topic)

    for directive in Directive.objects.filter(dedupe_key__startswith="announcement:").iterator():
        directive.dedupe_key = "broadcast:" + directive.dedupe_key[len("announcement:") :]
        directive.save(update_fields=["dedupe_key"])

    UserNotification.objects.filter(category="campaign").update(category="broadcast")
    for note in UserNotification.objects.filter(
        action_url__startswith="/campaign/announcements/"
    ).iterator():
        note.action_url = "/broadcast/posts/" + note.action_url[len("/campaign/announcements/") :]
        note.save(update_fields=["action_url"])
    for note in UserNotification.objects.filter(action_data__has_key="announcement_id").iterator():
        data = dict(note.action_data or {})
        data["broadcast_post_id"] = data.pop("announcement_id")
        note.action_data = data
        note.save(update_fields=["action_data"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0029_campaign_rename"),
        ("auth", "0001_initial"),
        ("orderman", "0001_initial"),
    ]

    operations = [migrations.RunPython(forward, backward)]
