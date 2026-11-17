"""iFood Review: listar, detalhar e responder avaliações pelo Gestor.

Os cenários são os do checklist de homologação do iFood (chamado 36323618), contra
um iFood falso que responde como a documentação do módulo Review: limite de página
50, ID inexistente 404, resposta só em ``NOT_REPLIED`` (409) e texto de 10 a 300
caracteres (400). O Shopman não repete essas regras: repassa o pedido e mostra a
recusa do iFood. Nenhuma chamada sai para a API real.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse

from shopman.backstage.projections.ifood_reviews import POLICY_URL, project_review
from shopman.shop.services import ifood_http, ifood_review

pytestmark = pytest.mark.django_db

MID = "f36a17d0-0000-0000-0000-000000000000"
BASE = f"/review/v2.0/merchants/{MID}"
ON = {"client_id": "cid", "client_secret": "sec", "merchant_id": MID}


class _Resp:
    def __init__(self, status: int, body=None):
        self.status_code = status
        self._body = body
        self.text = "" if body is None else str(body)
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        if self._body is None:
            raise ValueError("sem corpo")
        return self._body


def _review(rid: str, status: str = "NOT_REPLIED", **extra) -> dict:
    return {
        "id": rid,
        "status": status,
        "visibility": "PUBLIC",
        "version": "v2",
        "score": 3.0,
        "comment": "Pão chegou frio",
        "createdAt": "2026-11-18T13:30:00Z",
        "replies": [],
        "order": {"id": "o-" + rid, "shortId": "1234", "createdAt": "2026-11-18T12:00:00Z"},
        **extra,
    }


class FakeReview:
    """O módulo Review de mentira, com as recusas documentadas pelo iFood."""

    def __init__(self):
        self.reviews = {
            "r1": _review("r1", createdAt="2026-11-10T10:00:00Z"),
            "r2": _review("r2", createdAt="2026-11-18T10:00:00Z"),
            "r5": _review("r5", "PUBLISHED", score=5.0, comment="", createdAt="2026-11-01T10:00:00Z"),
        }
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, path, *, label, idempotent=False, **kwargs):
        self.calls.append((method, path, kwargs))
        if (method, path) == ("GET", f"{BASE}/reviews"):
            params = kwargs["params"]
            if int(params["pageSize"]) > 50:
                return _Resp(400, {"error": "pageSize must be <= 50", "status": 400})
            items = list(self.reviews.values())
            if params.get("dateFrom"):
                items = [r for r in items if r["createdAt"] >= params["dateFrom"][:10]]
            return _Resp(
                200,
                {"page": params["page"], "size": len(items), "reviews": items, "total": len(items), "pageCount": 1},
            )
        if method == "GET" and path == f"{BASE}/summary":
            return _Resp(200, {"totalReviewsCount": 3, "validReviewsCount": 2, "score": 3.7})
        if method == "GET" and path.startswith(f"{BASE}/reviews/"):
            rid = path.rsplit("/", 1)[1]
            if rid not in self.reviews:
                return _Resp(404, {"error": "Review not found", "status": 404})
            return _Resp(200, self.reviews[rid])
        if method == "POST" and path.endswith("/answers"):
            rid = path.split("/")[-2]
            text = kwargs["json"]["text"]
            if rid not in self.reviews:
                return _Resp(404, {"error": "Review not found", "status": 404})
            if not 10 <= len(text) <= 300:
                return _Resp(400, {"error": "text must be between 10 and 300 characters", "status": 400})
            if self.reviews[rid]["status"] != "NOT_REPLIED":
                return _Resp(409, {"error": "Review must have status NOT_REPLIED to receive an answer", "status": 409})
            self.reviews[rid]["status"] = "REPLIED"
            self.reviews[rid]["replies"] = [{"text": text, "from": "MERCHANT", "createdAt": "2026-11-19T12:00:00Z"}]
            return _Resp(201, {"createdAt": "2026-11-19T12:00:00Z", "reviewId": rid, "text": text})
        raise AssertionError(f"chamada inesperada ao iFood: {method} {path}")


@pytest.fixture
def fake(monkeypatch):
    fake = FakeReview()
    monkeypatch.setattr(ifood_http, "request", fake.request)
    return fake


@pytest.fixture
def operator(client):
    user = get_user_model().objects.create_user(username="gerente", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders"))
    client.force_login(user)
    return client


# ── Cenário 1: listar, filtrar por data, limite de página ─────────────────────


@override_settings(SHOPMAN_IFOOD=ON)
def test_lista_traz_os_campos_obrigatorios_e_a_paginacao(operator, fake):
    body = operator.get(reverse("api-backstage-ifood-reviews")).json()

    assert body["enabled"] is True
    assert body["policy_url"] == POLICY_URL
    assert (body["total"], body["page_count"], body["page"]) == (3, 1, 1)
    first = body["reviews"][0]
    for key in ("id", "status", "replies", "version", "visibility"):
        assert key in first
    assert first["status_label"] == "Aguardando resposta" and first["can_reply"] is True
    method, path, kwargs = fake.calls[0]
    assert (method, path) == ("GET", f"{BASE}/reviews")
    assert kwargs["params"]["addCount"] == "true" and kwargs["params"]["pageSize"] == 10


@override_settings(SHOPMAN_IFOOD=ON)
def test_filtro_por_data_vai_ao_ifood_com_fuso(operator, fake):
    body = operator.get(
        reverse("api-backstage-ifood-reviews"), {"date_from": "2026-11-15", "date_to": "2026-11-20"}
    ).json()

    params = fake.calls[0][2]["params"]
    assert params["dateFrom"].startswith("2026-11-15T00:00:00") and params["dateFrom"][-6] in "+-"
    assert params["dateTo"].startswith("2026-11-20T23:59:59")
    assert {r["id"] for r in body["reviews"]} == {"r2"}


@override_settings(SHOPMAN_IFOOD=ON)
def test_pagina_de_100_vai_ao_ifood_e_a_recusa_dele_volta_para_a_tela(operator, fake):
    resp = operator.get(reverse("api-backstage-ifood-reviews"), {"page_size": 100})

    assert fake.calls[0][2]["params"]["pageSize"] == 100
    assert resp.status_code == 400
    assert resp.json()["ifood_status"] == 400
    assert resp.json()["ifood_message"] == "pageSize must be <= 50"


@override_settings(SHOPMAN_IFOOD=ON)
def test_pagina_fora_de_1_a_100_nem_sai_daqui(operator, fake):
    resp = operator.get(reverse("api-backstage-ifood-reviews"), {"page_size": 500})

    assert resp.status_code == 400 and resp.json()["field"] == "page_size"
    assert fake.calls == []


# ── Cenário 2: detalhe e ID inexistente ───────────────────────────────────────


@override_settings(SHOPMAN_IFOOD=ON)
def test_detalhe_completo(operator, fake):
    fake.reviews["r1"].update(
        customerName="Ana",
        surveyId="s-1",
        questions=[
            {"id": "q", "type": "CHOICE", "title": "Do que você gostou?", "answers": [{"id": "a", "title": "Entrega"}]}
        ],
    )
    body = operator.get(reverse("api-backstage-ifood-review", args=["r1"])).json()

    assert body["customer_name"] == "Ana" and body["survey_id"] == "s-1"
    assert body["questions"] == [{"title": "Do que você gostou?", "kind": "CHOICE", "answers": ["Entrega"]}]
    assert body["order_short_id"] == "1234"


@override_settings(SHOPMAN_IFOOD=ON)
def test_id_inexistente_mostra_a_recusa_do_ifood(operator, fake):
    resp = operator.get(reverse("api-backstage-ifood-review", args=["00000000-0000-0000-0000-000000000000"]))

    assert resp.status_code == 404
    assert resp.json() == {
        "detail": "O iFood não encontrou esta avaliação.",
        "ifood_status": 404,
        "ifood_message": "Review not found",
    }


# ── Cenário 3: responder, PUBLISHED e texto inválido ──────────────────────────


@override_settings(SHOPMAN_IFOOD=ON)
def test_resposta_valida_vira_replied(operator, fake):
    text = "Obrigada pelo retorno! Vamos cuidar da temperatura na próxima entrega."
    resp = operator.post(
        reverse("api-backstage-ifood-review-reply", args=["r1"]), {"text": text}, content_type="application/json"
    )

    assert resp.status_code == 201
    assert resp.json() == {"review_id": "r1", "text": text, "created_at": "2026-11-19T12:00:00Z"}
    assert fake.calls[-1][2] == {"json": {"text": text}}
    detail = operator.get(reverse("api-backstage-ifood-review", args=["r1"])).json()
    assert detail["status"] == "REPLIED" and detail["can_reply"] is False
    assert detail["replies"][0]["author_label"] == "Loja"


@override_settings(SHOPMAN_IFOOD=ON)
def test_responder_publicada_mostra_o_409_do_ifood(operator, fake):
    resp = operator.post(
        reverse("api-backstage-ifood-review-reply", args=["r5"]),
        {"text": "Obrigada pela visita, volte sempre!"},
        content_type="application/json",
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "O iFood só aceita resposta em avaliação que está aguardando resposta."
    assert resp.json()["ifood_message"] == "Review must have status NOT_REPLIED to receive an answer"


@override_settings(SHOPMAN_IFOOD=ON)
def test_texto_curto_vai_ao_ifood_e_volta_o_400_dele(operator, fake):
    resp = operator.post(
        reverse("api-backstage-ifood-review-reply", args=["r2"]), {"text": "Obrigado"}, content_type="application/json"
    )

    assert [c[0] for c in fake.calls] == ["POST"]
    assert resp.status_code == 400
    assert resp.json()["ifood_message"] == "text must be between 10 and 300 characters"


@override_settings(SHOPMAN_IFOOD=ON)
def test_resposta_nao_e_repetida_quando_o_ifood_nao_responde(operator, monkeypatch):
    calls = []

    def _none(method, path, **kwargs):
        calls.append((method, kwargs.get("idempotent", False)))
        return None

    monkeypatch.setattr(ifood_http, "request", _none)
    resp = operator.post(
        reverse("api-backstage-ifood-review-reply", args=["r2"]),
        {"text": "Obrigada pelo retorno, vamos melhorar."},
        content_type="application/json",
    )

    assert resp.status_code == 502 and resp.json()["ifood_status"] == 0
    assert calls == [("POST", False)]


# ── Resumo, permissão e integração desligada ──────────────────────────────────


@override_settings(SHOPMAN_IFOOD=ON)
def test_resumo(operator, fake):
    body = operator.get(reverse("api-backstage-ifood-review-summary")).json()
    assert body == {"score": 3.7, "score_display": "3,7", "total_reviews": 3, "valid_reviews": 2}


@override_settings(SHOPMAN_IFOOD=ON)
def test_sem_permissao_nao_le(client, fake):
    client.force_login(get_user_model().objects.create_user(username="x", password="x", is_staff=True))
    assert client.get(reverse("api-backstage-ifood-reviews")).status_code == 403
    assert fake.calls == []


@override_settings(SHOPMAN_IFOOD={})
def test_integracao_desligada_nao_chama_o_ifood(operator, fake):
    assert operator.get(reverse("api-backstage-ifood-reviews")).json()["enabled"] is False
    assert operator.get(reverse("api-backstage-ifood-review", args=["r1"])).status_code == 503
    assert fake.calls == []


def test_mensagem_de_erro_nas_tres_formas_documentadas():
    assert ifood_review.ifood_error_message(_Resp(400, {"error": "pageSize must be <= 50", "status": 400})) == (
        "pageSize must be <= 50"
    )
    assert ifood_review.ifood_error_message(_Resp(400, {"errorType": "X", "errorMessage": "Invalid parameter"})) == (
        "Invalid parameter"
    )
    assert ifood_review.ifood_error_message(_Resp(403, {"error": {"code": "Forbidden", "message": "no"}})) == "no"


def test_nota_inteira_sai_sem_casa_decimal():
    assert project_review(_review("r", score=4.0)).score_display == "4"
    assert project_review(_review("r", score=4.5)).score_display == "4,5"
