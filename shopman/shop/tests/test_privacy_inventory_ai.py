"""`/privacidade` declara quem recebe a mensagem do cliente para um modelo ler.

Em 16/11/2026 o dono trocou a Anthropic pelo Jev (TypeSafe) com a DeepSeek na leitura
das mensagens (D-040), e autorizou a mensagem redigida a ir aos dois desde que eles
apareçam na política. A página só declarava a Anthropic, e por um sinal de `settings`
(a chave liga-desliga da Concierge) que não diz nada sobre para onde o texto vai.

Estes testes provam que o operador de IA agora sai do mesmo lugar que decide o tráfego
(`ai.resolve` sobre as `AIConnection` e as rotas da loja), e que conexão liberada para
mensagem de cliente sem operador declarado reprova com o nome dela.
"""

from __future__ import annotations

import pytest

from shopman.shop.models import AIConnection, AIProtocol, Shop
from shopman.shop.privacy_inventory import (
    _AGENT_SHARES,
    AI_PROCESSORS,
    active_ai_processors,
    active_processors,
    undeclared_ai_connections,
)

NOMES_DE_IA = ("Anthropic", "DeepSeek", "TypeSafe")


@pytest.fixture(autouse=True)
def _sem_conexoes(db):
    AIConnection.objects.all().delete()
    _rotas({})


def _conexao(ref, *, name="", base_url="", protocol=AIProtocol.ANTHROPIC, liberada=True, ativa=True):
    connection = AIConnection(
        ref=ref,
        name=name or ref,
        protocol=protocol,
        base_url=base_url,
        model="jev-latest" if protocol == AIProtocol.JEV else "deepseek-flash",
        customer_text_approved=liberada,
        is_active=ativa,
    )
    connection.set_api_key(f"chave-{ref}")
    connection.save()
    return connection


def _rotas(routes):
    shop = Shop.objects.first() or Shop.objects.create(name="Loja")
    shop.ai_routes = routes
    shop.save()


def _por_nome():
    return {processor.name: processor for processor in active_ai_processors()}


def _texto_da_pagina():
    return " ".join(f"{p.name} {p.role} {p.shares}" for p in active_processors())


# ── A trava ──────────────────────────────────────────────────────────────


def _assert_toda_conexao_liberada_tem_operador():
    orfas = undeclared_ai_connections()
    assert not orfas, (
        "Estas conexões de IA estão liberadas para receber mensagem de cliente e o "
        f"provedor delas não tem operador declarado: {list(orfas)}.\n"
        "Declare o provedor em AI_PROCESSORS (shopman/shop/privacy_inventory.py), "
        "para /privacidade dizer ao cliente quem recebe a mensagem dele, ou desmarque "
        "'pode receber mensagem de cliente' na conexão."
    )


def test_toda_conexao_liberada_tem_operador_declarado():
    _assert_toda_conexao_liberada_tem_operador()


def test_conexao_liberada_sem_operador_declarado_reprova_com_o_nome():
    _conexao("barato", name="Modelo Barato", base_url="https://api.provedor-novo.example/anthropic")

    with pytest.raises(AssertionError, match="Modelo Barato"):
        _assert_toda_conexao_liberada_tem_operador()


def test_so_conta_conexao_ativa_e_liberada():
    _conexao("rascunho", base_url="https://api.provedor-novo.example", liberada=False)
    _conexao("desligada", base_url="https://api.provedor-novo.example", ativa=False)

    assert undeclared_ai_connections() == ()


@pytest.mark.parametrize(
    # Não é `base_url`: o pytest-base-url reserva o nome.
    ("protocol", "endereco", "esperado"),
    [
        (AIProtocol.ANTHROPIC, "", "anthropic"),
        (AIProtocol.ANTHROPIC, "https://api.anthropic.com", "anthropic"),
        # DeepSeek falando o formato Anthropic continua sendo DeepSeek: quem recebe o
        # texto é o dono do endereço.
        (AIProtocol.ANTHROPIC, "https://api.deepseek.com/anthropic", "deepseek"),
        (AIProtocol.JEV, "", "typesafe"),
        (AIProtocol.JEV, "https://api.typesafe.ai/v1/systemone", "typesafe"),
    ],
)
def test_o_provedor_sai_do_endereco_da_conexao(protocol, endereco, esperado):
    _conexao("unica", protocol=protocol, base_url=endereco)

    assert [processor.key for processor in active_ai_processors()] == [esperado]
    assert undeclared_ai_connections() == ()


def test_dominio_parecido_nao_passa_por_declarado():
    _conexao("falsa", name="Imitação", base_url="https://deepseek.com.provedor-novo.example")

    assert any("Imitação" in orfa for orfa in undeclared_ai_connections())


# ── A página ─────────────────────────────────────────────────────────────


def test_deepseek_e_typesafe_so_aparecem_quando_uma_rota_de_texto_de_cliente_aponta():
    _conexao("deepseek", name="DeepSeek da casa", base_url="https://api.deepseek.com/anthropic")
    _conexao("anthropic-catalogo", liberada=False)
    _conexao("jev", protocol=AIProtocol.JEV)
    _conexao("jev-placar", protocol=AIProtocol.JEV, liberada=False)

    # Liberadas, mas nenhuma rota de texto de cliente aponta para elas.
    _rotas(
        {
            "default": {"connection": "anthropic-catalogo"},
            "copy": {"connection": "deepseek"},
            "decision": {"connection": "jev-placar"},
        }
    )
    assert active_ai_processors() == ()

    _rotas(
        {
            "default": {"connection": "anthropic-catalogo"},
            "intents": {"connection": "deepseek"},
            "decision": {"connection": "jev-placar"},
        }
    )
    assert list(_por_nome()) == ["DeepSeek"]

    _rotas(
        {
            "default": {"connection": "anthropic-catalogo"},
            "intents": {"connection": "deepseek"},
            "decision": {"connection": "jev"},
        }
    )
    assert list(_por_nome()) == ["DeepSeek", "TypeSafe"]
    pagina = _texto_da_pagina()
    assert "DeepSeek" in pagina and "TypeSafe" in pagina
    assert "Anthropic" not in pagina


def test_sem_conexao_liberada_a_pagina_nao_cita_nenhuma_ia():
    assert not any(nome in _texto_da_pagina() for nome in NOMES_DE_IA)

    _conexao("deepseek", base_url="https://api.deepseek.com/anthropic", liberada=False)
    _conexao("jev", protocol=AIProtocol.JEV, liberada=False)
    _rotas(
        {
            "concierge": {"connection": "deepseek"},
            "intents": {"connection": "deepseek"},
            "triage": {"connection": "deepseek"},
            "decision": {"connection": "jev"},
        }
    )

    assert active_ai_processors() == ()
    assert not any(nome in _texto_da_pagina() for nome in NOMES_DE_IA)


def test_conexao_sem_chave_nao_aparece():
    # Sem chave a porta não manda nada; a página não declara quem não recebe.
    connection = _conexao("deepseek", base_url="https://api.deepseek.com/anthropic")
    connection.set_api_key("")
    connection.save()

    assert active_ai_processors() == ()


def test_a_conexao_unica_do_formato_conta_como_rota():
    """Sem rota, a porta usa a única conexão ativa do formato (`ai._route`). Então uma
    DeepSeek sozinha recebe também o laço do agente, e a frase é a larga: a página
    segue a porta, não o nome da rota."""
    _conexao("deepseek", base_url="https://api.deepseek.com/anthropic")

    assert _por_nome()["DeepSeek"].shares == _AGENT_SHARES


def test_conexao_nao_declarada_aparece_pelo_nome_em_vez_de_sumir():
    """Falhar gritando: omitir da página quem recebe a mensagem é a mentira que o
    inventário existe para impedir. A trava acima reprova; a página, enquanto isso,
    não esconde."""
    _conexao("barato", name="Modelo Barato", base_url="https://api.provedor-novo.example/anthropic")
    _rotas({"intents": {"connection": "barato"}})

    assert list(_por_nome()) == ["Modelo Barato"]


# ── O que a frase promete ────────────────────────────────────────────────


def test_quem_le_a_mensagem_recebe_a_frase_da_mensagem_redigida():
    _conexao("deepseek", base_url="https://api.deepseek.com/anthropic")
    _conexao("anthropic-catalogo", liberada=False)
    _rotas({"default": {"connection": "anthropic-catalogo"}, "intents": {"connection": "deepseek"}})

    shares = _por_nome()["DeepSeek"].shares
    for tirado in ("documento", "telefone", "e-mail", "endereço", "cartão", "saúde"):
        assert tirado in shares


def test_o_laco_do_agente_nao_promete_menos_do_que_a_anthropic_declarava():
    """O laço antigo da Concierge (propósito `concierge`) manda nome e endereço de
    entrega. Enquanto ele existir, quem recebe essa rota recebe a frase larga."""
    _conexao("anthropic")
    _rotas({"concierge": {"connection": "anthropic"}, "intents": {"connection": "anthropic"}})

    anthropic = _por_nome()["Anthropic"]
    assert anthropic.shares == _AGENT_SHARES
    assert "nome" in anthropic.shares and "endereço da entrega" in anthropic.shares


def test_frases_de_ia_sem_travessao_nem_jargao():
    _conexao("anthropic")
    _conexao("deepseek", base_url="https://api.deepseek.com/anthropic")
    _conexao("jev", protocol=AIProtocol.JEV)
    _rotas(
        {
            "concierge": {"connection": "anthropic"},
            "intents": {"connection": "deepseek"},
            "decision": {"connection": "jev"},
        }
    )
    processors = active_ai_processors()
    assert {processor.key for processor in processors} == {p.key for p in AI_PROCESSORS}

    proibidas = ("gateway", "endpoint", "webhook", "api", "backend", "token", "payload", "prompt")
    for processor in processors:
        frase = f"{processor.role} {processor.shares}"
        assert "—" not in frase and "–" not in frase, frase
        achadas = [palavra for palavra in proibidas if palavra in frase.lower().split()]
        assert not achadas, f"jargão em {processor.key}: {achadas}: {frase}"
