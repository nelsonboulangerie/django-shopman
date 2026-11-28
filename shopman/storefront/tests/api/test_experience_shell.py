"""OC-20: a versão da loja chega pelo shell, e só a quem o servidor escolheu.

- X13: a variante muda apresentação, nunca preço, disponibilidade, sacola ou
  promessa. Para as mesmas entradas, o shell e o catálogo de A e B são iguais,
  campo ``experience`` à parte.
- X14: a variante não vaza entre visitantes. Resposta fora do padrão é
  ``private, no-store``, e a requisição com sessão nunca cai na gêmea pública de
  ``public_cache.py`` (``carries_credentials`` recusa o cookie).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import RuleConfig
from shopman.shop.policies.experience import EXPERIENCE_RULE_PATH
from shopman.storefront.api.public_cache import PUBLIC_EDGE_CACHE_CONTROL, carries_credentials
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

PRIVATE_SHELL = "/api/v1/storefront/shell/"
PUBLIC_SHELL = "/api/v1/storefront/public/shell/"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _experiment(*, internal: list[str] | None = None, generation: int = 1) -> RuleConfig:
    return RuleConfig.objects.create(
        ref="experience.para-quando",
        rule_path=EXPERIENCE_RULE_PATH,
        label="Para quando primeiro",
        params={
            "ref": "para-quando",
            "surface": "storefront",
            "variants": ["a", "b"],
            "default": "a",
            "cohorts": {"internal": internal or []},
            "allocation": {"b": 0},
            "owner": "Engenharia",
            "hypothesis": "Perguntar o dia antes da lista reduz a sacola recusada.",
            "metrics": ["sacola_recusada"],
            "remove_after": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "generation": generation,
        },
    )


def _customer_client(ref: str = "CLI-EXP", *, customer: Customer | None = None) -> tuple[Client, Customer]:
    from shopman.doorman import get_or_create_user_for_customer

    from shopman.storefront.tests.identity_fakes import make_identity_view

    if customer is None:
        customer = Customer.objects.create(ref=ref, first_name="Joyce", phone="+5543999990088")
    info = make_identity_view(
        subject_id=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True
    )
    user, _ = get_or_create_user_for_customer(info)
    client = Client()
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return client, customer


def _without_experience(body: dict) -> dict:
    shell = dict(body["shell"])
    shell.pop("experience")
    # O selo da equipe (DEV-2026-096) é apresentação de quem está na coorte, e só dela.
    shell.pop("team_preview", None)
    return {**body, "shell": shell}


def test_shell_without_experiments_carries_an_empty_list():
    _seed_surface()
    body = Client().get(PRIVATE_SHELL).json()
    assert body["shell"]["experience"] == []


def test_internal_customer_gets_b_privately_and_keeps_it_on_reload():
    _seed_surface()
    client, customer = _customer_client()
    _experiment(internal=[customer.ref])

    first = client.get(PRIVATE_SHELL)
    again = client.get(PRIVATE_SHELL)

    assert first.status_code == 200
    assert first.json()["shell"]["experience"] == [{"ref": "para-quando", "variant": "b"}]
    assert again.json()["shell"]["experience"] == first.json()["shell"]["experience"]
    assert first["Cache-Control"] == "private, no-store"
    assert again["Cache-Control"] == "private, no-store"
    # Coorte, motivo, dono e prazo nunca chegam à loja.
    raw = first.content.decode()
    for leaked in ("internal", "cohort", "Engenharia", "remove_after"):
        assert leaked not in raw


def test_login_records_the_variant_and_the_session_keeps_it():
    """A aderência nasce no ``login()`` (sinal ``user_logged_in``), não no GET."""
    from shopman.shop.services.experience import SESSION_KEY

    _seed_surface()
    customer = Customer.objects.create(ref="CLI-EXP", first_name="Joyce", phone="+5543999990088")
    rule = _experiment(internal=[customer.ref])
    client, _ = _customer_client(customer=customer)

    assert client.session[SESSION_KEY] == {"para-quando": {"variant": "b", "generation": 1}}
    assert client.get(PRIVATE_SHELL).json()["shell"]["experience"][0]["variant"] == "b"

    # Saiu da coorte no meio da sessão: esta sessão segue na versão com que entrou.
    rule.params = {**rule.params, "cohorts": {"internal": []}}
    rule.save()
    assert client.get(PRIVATE_SHELL).json()["shell"]["experience"][0]["variant"] == "b"

    # A geração nova reatribui na próxima requisição.
    rule.params = {**rule.params, "generation": 2}
    rule.save()
    assert client.get(PRIVATE_SHELL).json()["shell"]["experience"][0]["variant"] == "a"


def test_customer_outside_the_cohort_sees_the_default():
    _seed_surface()
    client, _ = _customer_client()
    _experiment(internal=["OUTRO-CLIENTE"])

    body = client.get(PRIVATE_SHELL).json()

    assert body["shell"]["experience"] == [{"ref": "para-quando", "variant": "a"}]


def test_x14_session_request_never_reaches_the_public_twin():
    """A atribuição exige sessão; quem carrega sessão é recusado na gêmea pública."""
    _seed_surface()
    client, customer = _customer_client()
    _experiment(internal=[customer.ref])

    private = client.get(PRIVATE_SHELL)
    assert private.json()["shell"]["experience"][0]["variant"] == "b"

    twin = client.get(PUBLIC_SHELL)

    assert twin.status_code == 400
    assert twin["Cache-Control"] == "private, no-store"
    assert "experience" not in twin.json()

    # A cerca é o cookie: a mesma requisição do cliente carrega credencial.
    request = twin.wsgi_request
    assert carries_credentials(request)


def test_x14_team_member_marked_in_the_register_gets_b_privately():
    """A equipe entra pelo próprio cadastro (decisão do dono, 24/11) e a resposta B é privada."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    from shopman.shop.services.experience import TEAM_OPERATOR_KEY

    _seed_surface()
    fran = get_user_model().objects.create_user(username="fran", is_staff=True)
    fran.groups.add(Group.objects.get_or_create(name="Caixa")[0])
    customer = Customer.objects.create(
        ref="CLI-FRAN", first_name="Fran", phone="+5543999990089", metadata={TEAM_OPERATOR_KEY: fran.pk}
    )
    client, _ = _customer_client(customer=customer)
    _experiment(internal=[])

    private = client.get(PRIVATE_SHELL)

    assert private.json()["shell"]["experience"] == [{"ref": "para-quando", "variant": "b"}]
    assert private["Cache-Control"] == "private, no-store"
    assert client.get(PUBLIC_SHELL).status_code == 400
    assert Client().get(PUBLIC_SHELL).json()["shell"]["experience"] == [{"ref": "para-quando", "variant": "a"}]


def test_x14_public_twin_only_ever_serves_the_default():
    _seed_surface()
    _, customer = _customer_client()
    _experiment(internal=[customer.ref])

    anonymous = Client()
    twin = anonymous.get(PUBLIC_SHELL)

    assert twin.status_code == 200
    assert twin["Cache-Control"] == PUBLIC_EDGE_CACHE_CONTROL
    assert not twin.cookies, "a gêmea pública não abre sessão para resolver versão"
    assert twin.json()["shell"]["experience"] == [{"ref": "para-quando", "variant": "a"}]


def test_x13_contract_is_the_same_for_a_and_b_except_the_experience_field():
    """Mesmas entradas (cliente, sacola, catálogo, relógio): só ``experience`` muda."""
    _seed_surface(stock_qty=Decimal("20"))
    client, customer = _customer_client()
    rule = _experiment(internal=[])

    shell_a = client.get(PRIVATE_SHELL).json()
    catalog_a = client.get("/api/v1/storefront/catalog/").json()
    product_a = client.get("/api/v1/storefront/products/PAO-FRANCES/").json()

    # Muda só a coorte (e a geração, que descarta a aderência da sessão).
    rule.params = {**rule.params, "cohorts": {"internal": [customer.ref]}, "generation": 2}
    rule.save()

    shell_b = client.get(PRIVATE_SHELL).json()
    catalog_b = client.get("/api/v1/storefront/catalog/").json()
    product_b = client.get("/api/v1/storefront/products/PAO-FRANCES/").json()

    assert shell_a["shell"]["experience"] == [{"ref": "para-quando", "variant": "a"}]
    assert shell_b["shell"]["experience"] == [{"ref": "para-quando", "variant": "b"}]
    assert _without_experience(shell_a) == _without_experience(shell_b)
    assert catalog_a == catalog_b
    assert product_a == product_b


def test_kill_switch_removes_the_experiment_from_the_shell():
    _seed_surface()
    client, customer = _customer_client()
    rule = _experiment(internal=[customer.ref])
    assert client.get(PRIVATE_SHELL).json()["shell"]["experience"][0]["variant"] == "b"

    rule.enabled = False
    rule.save()

    assert client.get(PRIVATE_SHELL).json()["shell"]["experience"] == []


# ── selo da versão de teste da equipe (DEV-2026-096) ─────────────────────────

OPT_OUT = "/api/v1/storefront/experience/opt-out/"


def _team_customer(username: str = "fran", ref: str = "CLI-FRAN") -> Customer:
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    from shopman.shop.services.experience import TEAM_OPERATOR_KEY

    operator = get_user_model().objects.create_user(username=username, is_staff=True)
    operator.groups.add(Group.objects.get_or_create(name="Caixa")[0])
    return Customer.objects.create(
        ref=ref, first_name="Fran", phone="+5543999990089", metadata={TEAM_OPERATOR_KEY: operator.pk}
    )


def _three_experiments() -> None:
    for ref in ("cardapio-dia-primeiro", "home-recompra-no-topo", "duvida-no-ponto"):
        RuleConfig.objects.create(
            ref=f"experience.{ref}",
            rule_path=EXPERIENCE_RULE_PATH,
            label=ref,
            params={
                "ref": ref,
                "surface": "storefront",
                "variants": ["a", "b"],
                "default": "a",
                "cohorts": {"internal": []},
                "allocation": {"b": 0},
                "owner": "Engenharia",
                "hypothesis": "Hipótese do teste.",
                "remove_after": (timezone.localdate() + timedelta(days=30)).isoformat(),
            },
        )


def test_team_member_gets_the_seal_in_plain_words():
    _seed_surface()
    client, _ = _customer_client(customer=_team_customer())
    _three_experiments()

    response = client.get(PRIVATE_SHELL)
    seal = response.json()["shell"]["team_preview"]

    assert seal == {
        "opted_out": False,
        "message": (
            "Você está vendo a versão de teste da equipe: escolher o dia antes de montar a "
            "sacola, dúvidas respondidas na sacola e repetir o último pedido no topo do início."
        ),
        "features": [
            "escolher o dia antes de montar a sacola",
            "dúvidas respondidas na sacola",
            "repetir o último pedido no topo do início",
        ],
        "action_label": "Ver a versão de sempre",
    }
    assert response["Cache-Control"] == "private, no-store"
    # Sem códigos: nem ref de experimento nem letra de variante no selo.
    for code in ("cardapio-dia-primeiro", "home-recompra-no-topo", "duvida-no-ponto", "B1", "B2"):
        assert code not in str(seal)


def test_allow_list_of_the_internal_cohort_also_gets_the_seal():
    _seed_surface()
    client, customer = _customer_client()
    _experiment(internal=[customer.ref])

    seal = client.get(PRIVATE_SHELL).json()["shell"]["team_preview"]

    assert seal["features"] == ["uma novidade em teste"]
    assert seal["opted_out"] is False


def test_common_customer_and_anonymous_never_get_the_field():
    _seed_surface()
    client, _ = _customer_client()
    _experiment(internal=["OUTRO-CLIENTE"])

    assert "team_preview" not in client.get(PRIVATE_SHELL).json()["shell"]
    assert "team_preview" not in Client().get(PRIVATE_SHELL).json()["shell"]
    assert "team_preview" not in Client().get(PUBLIC_SHELL).json()["shell"]


def test_pilot_is_not_the_team_and_gets_no_seal():
    _seed_surface()
    client, customer = _customer_client()
    rule = _experiment(internal=[])
    rule.params = {**rule.params, "cohorts": {"internal": [], "pilot": [customer.ref]}}
    rule.save()

    shell = client.get(PRIVATE_SHELL).json()["shell"]

    assert shell["experience"] == [{"ref": "para-quando", "variant": "b"}]
    assert "team_preview" not in shell


def test_see_the_usual_version_then_back_to_the_test_version():
    from shopman.shop.services.experience import OPT_OUT_KEY

    _seed_surface()
    client, _ = _customer_client(customer=_team_customer())
    _three_experiments()
    assert all(item["variant"] == "b" for item in client.get(PRIVATE_SHELL).json()["shell"]["experience"])

    opted = client.post(OPT_OUT)
    assert opted.status_code == 200
    assert opted.json() == {"opted_out": True}
    assert opted["Cache-Control"] == "private, no-store"
    assert client.session[OPT_OUT_KEY] is True

    usual = client.get(PRIVATE_SHELL)
    shell = usual.json()["shell"]
    assert all(item["variant"] == "a" for item in shell["experience"])
    assert shell["team_preview"]["opted_out"] is True
    assert shell["team_preview"]["action_label"] == "Voltar à versão de teste"
    assert shell["team_preview"]["message"] == (
        "Você está vendo a versão de sempre, sem as novidades em teste da equipe."
    )
    # Tudo no padrão, e ainda assim é de alguém: o selo não vai para cache nenhum.
    assert usual["Cache-Control"] == "private, no-store"

    back = client.delete(OPT_OUT)
    assert back.json() == {"opted_out": False}
    shell = client.get(PRIVATE_SHELL).json()["shell"]
    assert all(item["variant"] == "b" for item in shell["experience"])
    assert shell["team_preview"]["opted_out"] is False
    assert OPT_OUT_KEY not in client.session


def test_opt_out_lasts_until_logout():
    from shopman.shop.services.experience import OPT_OUT_KEY

    _seed_surface()
    client, _ = _customer_client(customer=_team_customer())
    _three_experiments()
    client.post(OPT_OUT)
    assert client.session[OPT_OUT_KEY] is True

    client.post("/api/v1/auth/logout/")

    assert OPT_OUT_KEY not in client.session


def test_opt_out_needs_an_identified_customer():
    _seed_surface()
    response = Client().post(OPT_OUT)
    assert response.status_code == 401
    assert response["Cache-Control"] == "private, no-store"
