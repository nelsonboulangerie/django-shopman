"""As permissões que um operador de produção REALMENTE tem nesta casa.

⚠️ Duas fixtures modelavam um operador com só ``backstage.operate_production`` — um
usuário que não existe em nenhum dos dois grupos seedados (Cozinha e Gerente têm as
colunas finas também). Enquanto a escrita não conferia a coluna, dava no mesmo. Com o
gate ligado, essas suítes passariam a medir o buraco em vez do operador.

Quem tem só o gate de superfície é o **grant customizado**, e é dele que o gate por
coluna protege — esse caso tem teste próprio, explícito, em vez de virar o padrão
acidental de toda a suíte.
"""

from __future__ import annotations

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

#: As colunas do quadro que uma escrita de produção pode tocar.
PRODUCTION_COLUMNS = ("planned", "started", "finished")


def surface_permission() -> Permission:
    """``backstage.operate_production`` — o gate grosso do chão."""
    from shopman.backstage.models import DayClosing

    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_production",
    )


def column_permissions() -> list[Permission]:
    """``shop.edit_production_{planned,started,finished}``."""
    from shopman.shop.models import Shop

    ct = ContentType.objects.get_for_model(Shop)
    return [
        Permission.objects.get(content_type=ct, codename=f"edit_production_{coluna}")
        for coluna in PRODUCTION_COLUMNS
    ]


def grant_production_operator(user):
    """Superfície MAIS colunas: o operador como a casa o define."""
    user.user_permissions.add(surface_permission(), *column_permissions())
    return type(user).objects.get(pk=user.pk)
