"""Gerente não tem permissão financeira. Ponto. A trava.

Dono, 21/11/2026, literal: "Isso, gerente basicamente NÃO tem permissões
financeiras. Ponto. O que teremos são exceções, extremamente pontuais, com regra
claríssima, que pode/deve ser testada/confrontada/questionada por guardrails ou
algo que o valha. Simples assim."

E sobre o B.I., no mesmo dia: "BI -> Só dono, só dono tem acesso!!! Gerente NÃO
deve ter acesso ao BI. Se for ter, um dia, será por exceção explícita, solicitada
previamente por mim, em pessoa."

Como a trava funciona:

1. :func:`_is_financial` reconhece toda permissão que toca dinheiro: o ``payman``
   inteiro, o ``cashman`` inteiro, o B.I. e os seus de-paras e o fechamento do
   dia. Permissão nova que caia nessas famílias entra na conta sozinha.
2. Cada permissão financeira que o grupo Gerente recebe do ``setup_groups`` tem de
   estar classificada numa de duas listas fechadas:

   - :data:`EXCEPTIONS`: exceção ao "nada financeiro", com a regra e a palavra do
     dono. Exceção nova só entra mudando esta lista, ou seja, revisada;
   - :data:`OPERATION_WITHOUT_AGGREGATE`: operação de balcão que ele precisa para
     trabalhar e que NÃO mostra valor somado (o fechamento cego, a assinatura do
     gerente num gesto). Cada entrada diz por que não soma, e os testes abaixo
     conferem o que é servido a ele.

   Permissão financeira fora das duas listas reprova.
3. O que é só do Dono (o B.I., a apuração do caixa, as cobranças) nunca chega ao
   Gerente, nem por classificação.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse

pytestmark = pytest.mark.django_db

#: Exceções ao "Gerente não tem permissão financeira". Cada uma: permissão →
#: (a regra, a palavra do dono). Hoje nenhuma. A primeira, estornar UM pedido
#: vendo só o valor dele, entra com o gesto que a usa (#2727, item 5).
EXCEPTIONS: dict[str, tuple[str, str]] = {}

#: Operação de balcão sem valor agregado. Não é exceção: é o trabalho dele, e
#: nenhuma destas telas mostra soma, total esperado ou lista de cobranças ao
#: Gerente (levantamento tela a tela de 21/11/2026, no PR que criou esta trava).
OPERATION_WITHOUT_AGGREGATE: dict[str, str] = {
    "backstage.perform_closing": (
        "Fecha o dia às cegas: conta o que sobrou e não vê o esperado "
        "(_blind_closing_data). No Admin, o registro do fechamento chega a ele "
        "sem o resumo do caixa (DayClosingAdmin.get_fields)."
    ),
    "backstage.view_dayclosing": (
        "A lista de fechamentos no Admin: data, quem fechou, itens e discrepâncias, sem valor."
    ),
    "cashman.adjust_shift": (
        "A assinatura do gerente num gesto (sangria, desconto, cancelamento): mostra o valor "
        "daquele gesto e mais nada. Não existe tela de ajuste com o esperado do turno."
    ),
    "cashman.manage_operators": "Operadores, PINs, crachás e postos. Nenhum valor.",
    "cashman.operate_pos": (
        "O PDV: vende, abre e fecha o turno contando às cegas (_cash_shift_result sem "
        "esperado nem diferença). As somas do período das encomendas ficam escondidas "
        "(show_money_sums=can_audit_cash); o relatório X/Z pede audit_shift."
    ),
    "cashman.view_terminal": "O cadastro dos terminais: configuração, sem valor de transação.",
    "cashman.add_terminal": "O cadastro dos terminais: configuração, sem valor de transação.",
    "cashman.change_terminal": "O cadastro dos terminais: configuração, sem valor de transação.",
}

#: Só do Dono: nem exceção, nem operação. Reprova se chegar ao Gerente ou a uma das listas.
OWNER_ONLY = frozenset({
    "backstage.view_bi",
    "backstage.view_dailysalesfact",
    "backstage.view_historicalsale",
    "backstage.view_historicalsaleitem",
    "backstage.view_biscenarioreport",
    "backstage.view_bialertevent",
    "backstage.view_bialertrule",
    "backstage.add_bialertrule",
    "backstage.change_bialertrule",
    "backstage.view_importbatch",
    "cashman.audit_shift",
    "payman.view_paymentintent",
    "payman.view_paymenttransaction",
    "payman.refund_paymentintent",
})

_BI_MODELS = (
    "bialertrule", "bialertevent", "biscenarioreport", "dailysalesfact", "historicalsale",
    "historicalsaleitem", "importbatch", "categoryalias", "productalias", "paymentmethodalias",
    "aliasbenchmarkreport",
)


def _is_financial(perm: str) -> bool:
    app, _, codename = perm.partition(".")
    if app in {"payman", "cashman"}:
        return True
    if app == "backstage":
        return (
            codename == "view_bi"
            or codename.endswith(_BI_MODELS)
            or "dayclosing" in codename
            or codename == "perform_closing"
        )
    # ``shop.view_reports`` são os relatórios da Produção: quantidade, perda e
    # qualidade, sem valor (conferido em 21/11/2026). Se ganharem dinheiro, entram aqui.
    return False


def _group_perms(name: str) -> set[str]:
    call_command("setup_groups")
    group = Group.objects.prefetch_related("permissions__content_type").get(name=name)
    return {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.all()}


def _user_in(username: str, *groups: str) -> User:
    call_command("setup_groups")
    user = User.objects.create_user(username, password="pw", is_staff=True)
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


def _gerente() -> User:
    return _user_in("gerente-trava", "Gerente")


# ── A classificação ──────────────────────────────────────────────────────────


def test_toda_permissao_financeira_do_gerente_esta_classificada():
    financial = {perm for perm in _group_perms("Gerente") if _is_financial(perm)}
    unclassified = financial - set(EXCEPTIONS) - set(OPERATION_WITHOUT_AGGREGATE)

    assert not unclassified, (
        f"O grupo Gerente recebeu permissão financeira sem classificação: {sorted(unclassified)}. "
        "Gerente não tem permissão financeira (dono, 21/11/2026). Tire a permissão do grupo "
        "no descritor da instância (config/instances/) ou, com a palavra do dono, declare a "
        "exceção em EXCEPTIONS."
    )


def test_o_que_e_so_do_dono_nunca_chega_ao_gerente():
    leaked = _group_perms("Gerente") & OWNER_ONLY
    assert not leaked, f"Só do Dono e concedido ao Gerente: {sorted(leaked)}"
    assert not (OWNER_ONLY & (set(EXCEPTIONS) | set(OPERATION_WITHOUT_AGGREGATE)))


def test_cada_excecao_tem_regra_e_palavra_do_dono():
    for perm, (rule, owner_word) in EXCEPTIONS.items():
        assert _is_financial(perm), f"{perm} não é financeira: não precisa de exceção"
        assert rule.strip() and owner_word.strip(), f"Exceção {perm} sem regra ou sem a palavra do dono"


def test_as_listas_nao_guardam_permissao_que_o_gerente_nao_tem():
    """Lista que guarda o que não existe mais vira lixo e esconde a próxima exceção."""
    granted = _group_perms("Gerente")
    stale = (set(EXCEPTIONS) | set(OPERATION_WITHOUT_AGGREGATE)) - granted
    assert not stale, f"Classificadas e não concedidas ao Gerente (tire da lista): {sorted(stale)}"


def test_o_bi_e_do_dono():
    assert {"backstage.view_bi", "backstage.view_dailysalesfact", "backstage.view_bialertrule"} <= _group_perms("Dono")


# ── O que é servido ao Gerente ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "url_name", ["api-backstage-bi-sales", "api-backstage-bi-cash", "api-backstage-bi-customers"],
)
def test_o_bi_responde_403_ao_gerente(client, url_name):
    client.force_login(_gerente())
    assert client.get(reverse(url_name)).status_code == 403


def test_a_central_nao_oferece_o_bi_ao_gerente():
    from shopman.backstage.permissions import can_view_bi

    assert can_view_bi(_gerente()) is False
    assert can_view_bi(_user_in("dono-bi", "Dono")) is True


def _closing():
    from shopman.backstage.models import DayClosing

    return DayClosing.objects.create(
        date=date(2026, 11, 20),
        closed_by=User.objects.create_user("quem-fechou", password="pw"),
        data={
            "items": [{"sku": "PAO", "qty_reported": 3}],
            "cash_shift_summary": {
                "totals": {"expected_amount_q": 51230, "difference_q": -200},
                "payment_method_totals": [{"method": "pix", "amount_q": 98000}],
            },
        },
    )


def _request_as(user: User):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_o_fechamento_no_admin_chega_ao_gerente_sem_o_resumo_do_caixa():
    """O registro do fechamento guarda o esperado, a quebra e o que entrou por forma
    de pagamento, e o Admin o mostrava a quem tem ``perform_closing``."""
    from shopman.backstage.models import DayClosing

    closing = _closing()
    model_admin = admin.site._registry[DayClosing]

    fields = model_admin.get_fields(_request_as(_gerente()), closing)
    shown = model_admin.operation_data_display(closing)

    assert "data" not in fields
    assert "operation_data_display" in fields
    assert "PAO" in shown
    for money in ("cash_shift_summary", "expected_amount_q", "difference_q", "payment_method_totals", "51230"):
        assert money not in shown


def test_quem_audita_caixa_ve_o_fechamento_inteiro():
    from shopman.backstage.models import DayClosing

    dono = _user_in("dono-trava", "Dono", "Gerente")
    assert "data" in admin.site._registry[DayClosing].get_fields(_request_as(dono), _closing())
