"""A nota fiscal da loja online chega DIGITAL: na página do pedido.

Decisão do dono (25/09/2026): a loja online não imprime nem pede e-mail. A NFC-e
autorizada aparece no acompanhamento (``/pedido/<ref>``) com o link da DANFE e
a chave de acesso, só depois de existir; cancelada, some o link.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

KEY = "41250912345678000199650010000001231000001234"


def _tracking(client, ref):
    resp = client.get(f"/api/v1/tracking/{ref}/")
    assert resp.status_code == 200, resp.content
    return resp.json()


def _authorize(order, **extra):
    order.data = {
        **(order.data or {}),
        "nfce_access_key": KEY,
        "nfce_number": 123,
        "nfce_danfe_url": "https://api.focusnfe.com.br/notas_fiscais_consumidor/NFe123.html",
        "nfce_qrcode_url": "https://www.fazenda.pr.gov.br/nfce/qrcode?p=123",
        **extra,
    }
    order.save(update_fields=["data"])


def test_sem_nota_a_pagina_nao_mostra_nada(client, order):
    assert _tracking(client, order.ref)["fiscal_note"] is None


def test_nota_autorizada_aparece_com_link_e_chave(client, order, settings):
    settings.SHOPMAN_FOCUS_NFE = {"environment": "producao"}
    _authorize(order)
    note = _tracking(client, order.ref)["fiscal_note"]
    assert note["title"] == "Nota fiscal"
    assert note["number_display"] == "NFC-e nº 123"
    assert note["url"] == "https://api.focusnfe.com.br/notas_fiscais_consumidor/NFe123.html"
    assert note["link_label"] == "Abrir a nota fiscal"
    assert note["access_key_display"] == " ".join(KEY[i : i + 4] for i in range(0, 44, 4))
    assert note["note"] == ""


def test_sem_danfe_o_link_e_a_consulta_da_sefaz(client, order, settings):
    settings.SHOPMAN_FOCUS_NFE = {"environment": "producao"}
    _authorize(order, nfce_danfe_url="")
    assert _tracking(client, order.ref)["fiscal_note"]["url"] == "https://www.fazenda.pr.gov.br/nfce/qrcode?p=123"


def test_nota_de_homologacao_diz_que_nao_vale(client, order, settings):
    settings.SHOPMAN_FOCUS_NFE = {"environment": "homologacao"}
    _authorize(order)
    assert _tracking(client, order.ref)["fiscal_note"]["note"] == "Nota de teste, sem valor fiscal."


def test_nota_cancelada_nao_oferece_o_link(client, order):
    _authorize(order, nfce_cancelled=True)
    note = _tracking(client, order.ref)["fiscal_note"]
    assert note["url"] == ""
    assert note["note"] == "Esta nota foi cancelada e não vale mais."
