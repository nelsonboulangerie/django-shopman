"""Canonical backstage permission predicates.

Single source for "can this operator do X" across the whole backstage
surface: Unfold admin-console pages, the dedicated KDS/POS views, the
sidebar navigation, and the REST API gate. Every predicate takes a
``user`` — the common denominator — so admin pages (``request.user``),
views, and services share one implementation instead of copying the rules.

Grants flow through Django's permission system; doorman wires operator
PIN/role credentials onto Groups, whose permissions these checks read.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False))


def is_superuser(user) -> bool:
    return bool(getattr(user, "is_superuser", False))


def can_manage_orders(user) -> bool:
    return is_superuser(user) or user.has_perm("shop.manage_orders")


#: Quem EXPEDE (SUITE-UX §15/§16: uma Saída só, no Gestor). A Saída morava na
#: Cozinha e era operada com ``backstage.operate_kds``; ao mudar para a coluna
#: Saída do Gestor, quem a operava continua operando, e só ela: avançar a saída
#: (Entregar, Despachar), desfazer dentro da janela, "Pronto" da estação sem tela
#: e devolver um ticket à cozinha. Aceitar, recusar, cancelar, troco, maquininha,
#: iFood e o resto do Gestor seguem em ``shop.manage_orders``. Nenhuma permissão
#: nova: o conjunto de quem pode expedir é exatamente o de antes.
EXPEDITE_PERMISSION = "backstage.operate_kds"

#: As duas portas do quadro do Gestor: quem gerencia pedidos e quem só expede.
ORDER_BOARD_PERMISSIONS = ("shop.manage_orders", EXPEDITE_PERMISSION)


def can_expedite(user) -> bool:
    """Opera a coluna Saída do Gestor (gerencia pedidos ou expede)."""
    return bool(user) and (can_manage_orders(user) or user.has_perm(EXPEDITE_PERMISSION))


def expedites_only(user) -> bool:
    """Opera só a Saída: expede, mas não gerencia pedidos."""
    return bool(user) and not can_manage_orders(user) and user.has_perm(EXPEDITE_PERMISSION)


#: Separador da permissão de SUPERFÍCIE com alternativas (``a|b``): a primeira é a
#: capability da própria superfície (a chave da trava dela); as demais também
#: deixam a pessoa entrar. O Gestor pede ``shop.manage_orders|backstage.operate_kds``.
SURFACE_PERM_SEPARATOR = "|"


def surface_perm_codes(perm) -> tuple[str, ...]:
    """As permissões de uma superfície, na ordem (a primeira é a chave da trava)."""
    return tuple(code.strip() for code in str(perm or "").split(SURFACE_PERM_SEPARATOR) if code.strip())


def has_surface_perm(user, perm) -> bool:
    """A pessoa tem alguma das permissões da superfície (vazio = nenhuma exigida)."""
    codes = surface_perm_codes(perm)
    return not codes or any(user.has_perm(code) for code in codes)


def can_access_production(user) -> bool:
    if is_superuser(user) or user.has_perm("shop.manage_production"):
        return True
    try:
        from shopman.backstage.projections.production import resolve_production_access

        return resolve_production_access(user).can_access_board
    except Exception:
        logger.warning("backstage_production_access_failed", exc_info=True)
        return False


def can_view_bi(user) -> bool:
    """B.I. (ADR-021): leitura analítica cross-suite — persona de gestão."""
    return is_superuser(user) or user.has_perm("backstage.view_bi")


def can_view_production_reports(user) -> bool:
    return (
        is_superuser(user)
        or user.has_perm("backstage.view_production_reports")
        or user.has_perm("shop.manage_production")
    )


def can_close_day(user) -> bool:
    return is_superuser(user) or user.has_perm("backstage.perform_closing")


def can_operate_pos(user) -> bool:
    return is_superuser(user) or user.has_perm("cashman.operate_pos")


#: A permissão da apuração. O B.I. de caixa (quebra por operador) a exige ALÉM
#: de ``view_bi`` — decisão do dono, 19/08/2026; a permissão mora no ``cashman``.
CASH_AUDIT_PERMISSION = "cashman.audit_shift"


def can_audit_cash(user) -> bool:
    """Quem pode ver a APURAÇÃO do caixa: esperado, contado, diferença.

    Não é quem opera. O balconista abre o turno, vende, faz sangria e fecha
    contando às cegas — e nada disso exige saber quanto *deveria* haver na
    gaveta. Quem sabe o esperado não conta às cegas: confere um gabarito, e o
    fechamento cego perde a única coisa que ele existe para pegar.

    O gerente também não tem: ``setup_groups`` dá a ele ``operate_pos``,
    ``adjust_shift`` e ``manage_operators``, e **não** ``audit_shift``. Ele
    opera, autoriza exceção e fecha o turno; a apuração é de quem audita.

    ⚠️ A permissão existia desde o começo e ninguém a consultava — as telas
    mostravam a apuração para qualquer um com ``operate_pos``. Este predicado é
    onde ela passa a valer.
    """
    return is_superuser(user) or user.has_perm(CASH_AUDIT_PERMISSION)


def can_operate_kds(user) -> bool:
    return is_superuser(user) or user.has_perm("backstage.operate_kds")


def can_operate_production(user) -> bool:
    """Coarse operator gate for the dedicated production app (``prod.``).

    Sibling of ``operate_pos``/``operate_kds``: a single surface-entry grant for
    the floor + planning app, granted to the Cozinha/Gerente groups. The
    fine-grained column control (``resolve_production_access`` / the
    ``*_production_*`` perms on ``shop.shop``) keeps governing the Admin console
    and is intentionally left untouched.
    """
    return is_superuser(user) or user.has_perm("backstage.operate_production")


def can_operate_purchase(user) -> bool:
    """Gate do app Compras (``compras.``): reposição, custos e recebimento."""
    return is_superuser(user) or user.has_perm("backstage.operate_purchase")


def can_manage_campaigns(user) -> bool:
    """Gate do app Campanha (marketing operacional).

    Deliberadamente separado de ``can_manage_orders``: quem cuida da fila de
    pedidos não é necessariamente quem decide o que a padaria publica
    (FOMO-MARKETING-SPECS §8).
    """
    return (
        is_superuser(user)
        or user.has_perm("shop.view_marketing")
        # Janela de migração: só decide se o app aparece. O backend de cada
        # mutação não herda esta compatibilidade.
        or user.has_perm("shop.manage_campaigns")
    )


def can_view_operator_kitchen_sink(user) -> bool:
    """Gate do app Catálogo do operador: a porta do app e o tile da Central."""
    return is_superuser(user) or user.has_perm("backstage.view_operator_kitchen_sink")


def can_view_operator_alerts(user) -> bool:
    return is_staff(user) and (
        is_superuser(user)
        or can_manage_orders(user)
        or can_access_production(user)
        or can_operate_pos(user)
        or can_audit_cash(user)
        or can_operate_kds(user)
        or can_operate_production(user)
        or can_operate_purchase(user)
    )
