"""O comprovante de sangria: papel que aponta para a verdade.

O comprovante existe porque a política de PIN nasceu de "sangria sem
testemunha". Papel sem vínculo com o registro seria só papel. O registro é a
linha ``cash_out``/``cash_in`` do livro do turno (``cashman.Entry``); o que
aconteceu com o papel é outra linha (``receipt_result``) apontando para ela.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift, Terminal

from shopman.backstage.services.pos import receipt_result_for
from shopman.backstage.services.receipt_escpos import COLUMNS, ENCODING, cash_movement_receipt
from shopman.backstage.services.receipt_verify import (
    InvalidReceiptCode,
    code_for,
    entry_id_from,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def movimento():
    user = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    admin = get_user_model().objects.create_user(username="admin", password="x", is_staff=True)
    shift = cash.open_shift(operator=user, terminal=Terminal.default(), float_q=10000)
    return cash.record(
        Entry.Kind.CASH_OUT,
        shift=shift,
        operator=user,
        approved_by=admin,
        amount_q=-15000,
        reason="Retirada para o cofre",
    )


# ── O registro do que aconteceu com o papel ───────────────────────────────


def test_o_movimento_nasce_SEM_confirmacao_de_impressao(movimento):
    """⚠️ Assumir 'impresso' sem confirmação transforma papel que faltou em
    papel que alguém escondeu — o oposto do que o comprovante existe para fazer.

    Quem imprime é o navegador do balcão, e ele pode fechar antes de confirmar.
    Sem ``receipt_result`` filho, o estado é "sem confirmação".
    """
    assert receipt_result_for(movimento) is None


def test_os_tres_resultados_do_papel_existem():
    from shopman.backstage.services.pos import _receipt_result_statuses

    assert set(_receipt_result_statuses()) == {"printed", "failed", "skipped"}


# ── O código de conferência ───────────────────────────────────────────────


def test_o_codigo_resolve_para_o_movimento(movimento):
    assert entry_id_from(code_for(movimento.pk)) == movimento.pk


def test_codigo_inventado_NAO_resolve():
    """Sem assinatura, bastaria escrever 'SG-999' num papel qualquer."""
    with pytest.raises(InvalidReceiptCode):
        entry_id_from("SG-999-AAAAAAAA")


def test_codigo_de_outro_movimento_nao_serve_para_este(movimento):
    """Trocar o número no papel tem que quebrar a assinatura."""
    codigo = code_for(movimento.pk)
    adulterado = codigo.replace(f"-{movimento.pk}-", f"-{movimento.pk + 1}-")
    with pytest.raises(InvalidReceiptCode):
        entry_id_from(adulterado)


@pytest.mark.parametrize("lixo", ["", "SG", "SG-1", "XX-1-AAAAAAAA", "SG-abc-AAAAAAAA", None])
def test_codigo_malformado_nao_explode_feio(lixo):
    with pytest.raises(InvalidReceiptCode):
        entry_id_from(lixo)


def test_o_codigo_evita_caracteres_que_se_confundem(movimento):
    """Quem digita o código quando o QR não lê não deve tropeçar em I × 1."""
    assinatura = code_for(movimento.pk).split("-")[2]
    assert not set(assinatura) & set("IO")


# ── O papel ───────────────────────────────────────────────────────────────


def _texto(bytes_do_papel: bytes) -> str:
    return bytes_do_papel.decode(ENCODING, "replace")


def test_o_papel_traz_valor_operador_e_quem_autorizou(movimento):
    papel = _texto(cash_movement_receipt(movimento, verify_code="SG-1-XXXXXXXX", verify_url="https://x/y"))

    assert "150,00" in papel
    assert "marina" in papel
    # Retirada tem DUAS assinaturas; o papel mostra as duas.
    assert "admin" in papel
    assert "Retirada para o cofre" in papel


def test_o_papel_traz_o_codigo_e_o_QR(movimento):
    papel = cash_movement_receipt(movimento, verify_code="SG-1-XXXXXXXX", verify_url="https://x/verificar")

    assert "SG-1-XXXXXXXX".encode(ENCODING) in papel
    assert b"https://x/verificar" in papel
    assert bytes([0x1D, 0x28, 0x6B]) in papel, "faltou o comando de QR"


def test_o_papel_impoe_a_tabela_de_acento(movimento):
    """CP860 é IMPOSTA, não descoberta — o balcão provou que a impressora obedece.

    Sem impor, o acento depende do que veio de fábrica ou de quem mexeu antes.
    """
    papel = cash_movement_receipt(movimento, verify_code="X", verify_url="u")
    assert bytes([0x1B, ord("t"), 3]) in papel
    assert papel.startswith(bytes([0x1B, ord("@")])), "sem reset, herda estado do job anterior"


def test_a_segunda_via_sai_MARCADA(movimento):
    """Sem a marca, dois papéis idênticos circulam e a 2ª via passa por original."""
    original = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u"))
    segunda = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u", reprint=True))

    assert "2a VIA" not in original
    assert "2a VIA" in segunda


def _com_motivo(movimento, reason: str):
    """A linha do livro é imutável: um motivo diferente é outra linha."""
    return cash.record(
        Entry.Kind.CASH_OUT,
        shift=movimento.shift,
        operator=movimento.operator,
        approved_by=movimento.approved_by,
        amount_q=movimento.amount_q,
        reason=reason,
    )


def test_nenhuma_linha_passa_da_largura_do_papel(movimento):
    movimento = _com_motivo(movimento, "Retirada " * 30)  # motivo gigante, digitado sem dó
    papel = _texto(cash_movement_receipt(movimento, verify_code="SG-1-XXXXXXXX", verify_url="https://x/y"))

    for linha in papel.splitlines():
        limpa = "".join(c for c in linha if c.isprintable())
        assert len(limpa) <= COLUMNS, f"linha estourou {COLUMNS} colunas: {limpa!r}"


def test_motivo_vazio_nao_deixa_o_papel_mudo(movimento):
    movimento = _com_motivo(movimento, "")
    papel = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u"))
    assert "Motivo:" in papel


def test_o_que_a_tabela_nao_tem_vira_equivalente_e_nao_lixo(movimento):
    """Travessão, aspas curvas e reticências viram "?" na CP860.

    O operador digita (ou o celular põe sozinho) e o motivo da sangria sairia
    corrompido, parecendo defeito da impressora.
    """
    movimento = _com_motivo(movimento, "Cofre — “fim de turno” … valor à parte")
    papel = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u"))

    assert "?" not in papel, "algum caractere não foi traduzido e virou lixo"
    assert "Cofre - " in papel
    assert '"fim de turno"' in papel
    assert "..." in papel
    # Acento de verdade CONTINUA saindo — a tradução não pode achatar português.
    assert "à parte" in papel


# ── O caminho pelo servidor ───────────────────────────────────────────────


def _grant(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))


@pytest.fixture
def operador_logado(client, movimento):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    user = movimento.shift.opened_by
    _grant(user)
    client.force_login(user)
    return client, movimento


def test_o_servidor_entrega_os_bytes_prontos(operador_logado, settings):
    """A tela relaia; ela não sabe compor ESC/POS nem precisa saber."""
    import base64

    from django.urls import reverse

    settings.SHOPMAN_ADMIN_HOST = "admin.boulangerie.com.br"
    client, movimento = operador_logado

    response = client.get(reverse("api-backstage-pos-cash-receipt", args=[movimento.pk]))

    assert response.status_code == 200
    corpo = response.json()
    papel = base64.b64decode(corpo["payload_b64"])
    assert papel.startswith(bytes([0x1B, 0x40]))
    assert corpo["verify_code"].startswith("SG-")
    # O QR aponta para o host canônico do Admin, não para constante inventada.
    assert b"https://admin.boulangerie.com.br/admin/cash/receipt/" in papel


def test_sem_host_de_admin_o_QR_leva_so_o_codigo(operador_logado, settings):
    """Melhor o código sozinho do que um endereço que não existe."""
    import base64

    from django.urls import reverse

    settings.SHOPMAN_ADMIN_HOST = ""
    client, movimento = operador_logado

    papel = base64.b64decode(
        client.get(reverse("api-backstage-pos-cash-receipt", args=[movimento.pk])).json()["payload_b64"]
    )
    assert b"https://" not in papel


def test_comprovante_de_movimento_de_OUTRA_GAVETA_e_recusado(operador_logado):
    """Ninguém tira comprovante de caixa alheio — e alheio é outra GAVETA.

    Era "outro turno", quando o turno era da pessoa. Num balcão que se reveza
    dentro de um turno só, esse filtro recusaria a segunda via de uma sangria
    que a colega lançou meia hora antes, na mesma gaveta. O que continua
    valendo é a fronteira física: o balcão não imprime o papel do totem.
    """
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    client, _ = operador_logado
    outro = get_user_model().objects.create_user(username="outro", password="x", is_staff=True)
    outro_shift = cash.open_shift(operator=outro, terminal=Terminal.objects.create(ref="pdv-2"), float_q=0)
    alheio = cash.record(Entry.Kind.CASH_IN, shift=outro_shift, operator=outro, amount_q=100)

    # Pedido a partir do BALCÃO (pdv-main): o movimento é do pdv-2.
    response = client.get(
        reverse("api-backstage-pos-cash-receipt", args=[alheio.pk]),
        {"terminal_ref": Terminal.default().ref},
    )
    assert response.status_code == 400

    # E a MESMA gaveta entrega — senão "recusa" poderia ser só quebra.
    ok = client.get(
        reverse("api-backstage-pos-cash-receipt", args=[alheio.pk]),
        {"terminal_ref": "pdv-2"},
    )
    assert ok.status_code == 200, ok.content


def test_o_balcao_registra_que_imprimiu(operador_logado):
    from django.urls import reverse

    client, movimento = operador_logado
    response = client.post(
        reverse("api-backstage-pos-cash-receipt", args=[movimento.pk]),
        data={"status": "printed"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["receipt_status"] == "printed"
    resultado = receipt_result_for(movimento)
    assert resultado.kind == Entry.Kind.RECEIPT_RESULT
    assert resultado.parent_id == movimento.pk
    assert resultado.payload["status"] == "printed"


def test_o_balcao_registra_a_FALHA_com_o_motivo(operador_logado):
    """Falha sem motivo obriga alguém a adivinhar depois."""
    from django.urls import reverse

    client, movimento = operador_logado
    client.post(
        reverse("api-backstage-pos-cash-receipt", args=[movimento.pk]),
        data={"status": "failed", "detail": "O agente da estação não está rodando."},
        content_type="application/json",
    )

    resultado = receipt_result_for(movimento)
    assert resultado.payload["status"] == "failed"
    assert "não está rodando" in resultado.payload["detail"]


def test_impresso_NAO_volta_atras(operador_logado):
    """Se já saiu papel uma vez, saiu. Regredir apagaria a testemunha."""
    from django.urls import reverse

    client, movimento = operador_logado
    url = reverse("api-backstage-pos-cash-receipt", args=[movimento.pk])
    client.post(url, data={"status": "printed"}, content_type="application/json")
    client.post(url, data={"status": "failed", "detail": "erro"}, content_type="application/json")

    assert receipt_result_for(movimento).payload["status"] == "printed"
    # E não nasce linha nova depois do "impresso": o livro não recebe regressão.
    assert movimento.children.filter(kind=Entry.Kind.RECEIPT_RESULT).count() == 1


def test_status_invalido_e_recusado(operador_logado):
    from django.urls import reverse

    client, movimento = operador_logado
    for ruim in ("", "pending", "qualquer"):
        response = client.post(
            reverse("api-backstage-pos-cash-receipt", args=[movimento.pk]),
            data={"status": ruim},
            content_type="application/json",
        )
        assert response.status_code == 400, ruim


def test_o_valor_sai_em_corpo_duplo(movimento):
    """O único dado que se lê de longe no maço de filipetas.

    Quem confere o caixa no fim do dia tem um punhado de papéis na mão e precisa
    somar. Valor do mesmo tamanho de "Turno #7" some no meio do resto, e a
    conferência vira caça ao tesouro — o motivo de existir o comprovante é
    justamente ela ser rápida.
    """
    from shopman.backstage.services.receipt_escpos import cash_movement_receipt

    papel = cash_movement_receipt(movimento, verify_code="SG-1-AAAAAAAA", verify_url="https://x/y")

    # `GS ! 0x11` liga largura e altura dobradas; `GS ! 0x00` volta ao normal.
    liga = bytes([0x1D, ord("!"), 0x11])
    desliga = bytes([0x1D, ord("!"), 0x00])
    assert liga in papel, "o valor precisa sair em corpo duplo"
    assert papel.index(liga) < papel.index(b"R$ 150,00") < papel.index(desliga), (
        "o corpo duplo tem que envolver o VALOR, não outra linha"
    )
    # Sem o desliga, todo o resto do papel sairia gigante — o modo é de estado.
    assert papel.count(liga) == papel.count(desliga) == 1


def test_o_valor_sai_com_sinal(movimento):
    """`+`/`−` no próprio número: quem soma o maço não lê o cabeçalho de cada um."""
    from shopman.backstage.services.receipt_escpos import cash_movement_receipt

    saida = cash_movement_receipt(movimento, verify_code="X", verify_url="https://x/y")
    assert b"- R$ 150,00" in saida

    suprimento = cash.record(Entry.Kind.CASH_IN, shift=movimento.shift, operator=movimento.operator, amount_q=15000)
    entrada = cash_movement_receipt(suprimento, verify_code="X", verify_url="https://x/y")
    assert b"+ R$ 150,00" in entrada


def test_o_qr_sai_centralizado_e_devolve_o_alinhamento(movimento):
    """Encostado à esquerda, com meio papel vazio ao lado, parece defeito.

    ⚠️ `ESC a` é modo de ESTADO: sem o retorno a 0, todo o resto do papel sairia
    centralizado — inclusive a linha final, que é âncora visual do rodapé.
    """
    from shopman.backstage.services.receipt_escpos import cash_movement_receipt

    papel = cash_movement_receipt(movimento, verify_code="X", verify_url="https://x/y")
    centraliza = bytes([0x1B, ord("a"), 1])
    esquerda = bytes([0x1B, ord("a"), 0])

    assert centraliza in papel
    assert papel.index(centraliza) < papel.index(esquerda), "tem que voltar DEPOIS do QR"
    assert papel.count(centraliza) == papel.count(esquerda) == 1


def test_as_duas_assinaturas_ficam_na_mesma_linha(movimento):
    """Quem lança e quem autoriza são um par; separá-las rebaixa a segunda.

    A autorização do gerente é a substância da retirada, não um detalhe do
    cabeçalho — na mesma linha, quem confere lê a dupla de uma vez.
    """
    from shopman.backstage.services.receipt_escpos import cash_movement_receipt

    papel = cash_movement_receipt(movimento, verify_code="X", verify_url="https://x/y")
    # O separador sai como "-": a CP860 não tem o ponto médio, e a tabela de
    # transliteração o converte em vez de deixar virar "?" no papel.
    assert b"marina - autorizado por admin" in papel


def test_sem_autorizador_a_linha_nao_inventa_sufixo(movimento):
    """Suprimento não tem segunda assinatura — e o papel não finge que tem."""
    from shopman.backstage.services.receipt_escpos import cash_movement_receipt

    suprimento = cash.record(Entry.Kind.CASH_IN, shift=movimento.shift, operator=movimento.operator, amount_q=15000)
    papel = cash_movement_receipt(suprimento, verify_code="X", verify_url="https://x/y")
    assert b"autorizado por" not in papel


def test_o_valor_fica_emoldurado_entre_tracos(movimento):
    """Cercado de branco entre duas réguas, o olho acha antes de procurar."""
    from shopman.backstage.services.receipt_escpos import cash_movement_receipt

    papel = cash_movement_receipt(movimento, verify_code="X", verify_url="https://x/y")
    regua = ("-" * 48).encode("cp860")
    valor = papel.index(b"- R$ 150,00")
    antes = papel.rindex(regua, 0, valor)
    depois = papel.index(regua, valor)
    assert antes < valor < depois, "o valor tem que estar ENTRE duas réguas"
