"""`/privacidade` declara quem recebe a mensagem do cliente para um modelo ler.

Em 16/11/2026 o dono trocou a Anthropic pelo Jev (TypeSafe) com a DeepSeek na leitura
das mensagens (D-040), e autorizou a mensagem redigida a ir aos dois desde que eles
apareçam na política. A página só declarava a Anthropic, e por um sinal de `settings`
(a chave liga-desliga da Concierge) que não diz nada sobre para onde o texto vai.

Estes testes provam que o operador de IA sai do mesmo lugar que decide o tráfego
(`ai.resolve` sobre as `AIConnection` e as rotas da loja), que conexão liberada sem
operador declarado reprova com o nome dela, e que a frase de cada caminho é a que o
código de fato monta (a segunda metade: montar o pedido real e conferir).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.models import AIConnection, AIProtocol, Shop
from shopman.shop.privacy_inventory import (
    AI_PROCESSORS,
    AI_USES,
    _customer_text_purposes,
    active_ai_processors,
    active_processors,
    ai_role_and_shares,
    undeclared_ai_connections,
)

NOMES_DE_IA = ("Anthropic", "DeepSeek", "TypeSafe")
USOS = {use.purpose: use for use in AI_USES}


@pytest.fixture(autouse=True)
def _sem_conexoes(db, settings):
    AIConnection.objects.all().delete()
    _rotas({})
    # A Concierge atendendo com as chaves de fábrica (`config/settings.py`).
    settings.SHOPMAN_CONCIERGE = {
        **(getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}),
        "enabled": True,
        "operation_mode": "assist",
        "triage_with_model": True,
    }


def _concierge(settings, **chaves):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, **chaves}


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


def _deepseek_e_jev():
    """DeepSeek e Jev liberados; o resto do formato Anthropic vai para uma não liberada."""
    _conexao("deepseek", name="DeepSeek da casa", base_url="https://api.deepseek.com/anthropic")
    _conexao("anthropic-catalogo", liberada=False)
    _conexao("jev", protocol=AIProtocol.JEV)
    _conexao("jev-placar", protocol=AIProtocol.JEV, liberada=False)


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


def test_todo_proposito_de_texto_de_cliente_tem_frase():
    sem_frase = set(_customer_text_purposes()) - set(USOS)
    assert not sem_frase, (
        f"Estes propósitos levam mensagem de cliente e não têm AIUse: {sorted(sem_frase)}. "
        "Sem frase, /privacidade não sabe dizer o que sai por eles."
    )


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
    _deepseek_e_jev()

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


def test_conexao_nao_declarada_aparece_pelo_nome_em_vez_de_sumir():
    """Falhar gritando: omitir da página quem recebe a mensagem é a mentira que o
    inventário existe para impedir. A trava acima reprova; a página, enquanto isso,
    não esconde."""
    _conexao("barato", name="Modelo Barato", base_url="https://api.provedor-novo.example/anthropic")
    _rotas({"intents": {"connection": "barato"}})

    assert "Modelo Barato" in _por_nome()


# ── Cada caminho só conta quando roda ────────────────────────────────────


def test_concierge_desligada_so_o_jev_continua_declarado(settings):
    """A sombra do Jev roda com a Concierge observando; a leitura e a triagem, não."""
    _deepseek_e_jev()
    _rotas(
        {
            "default": {"connection": "deepseek"},
            "labeling": {"connection": "anthropic-catalogo"},
            "decision": {"connection": "jev"},
        }
    )
    assert list(_por_nome()) == ["DeepSeek", "TypeSafe"]

    _concierge(settings, operation_mode="observe")

    assert list(_por_nome()) == ["TypeSafe"]


def test_o_laco_e_a_triagem_por_modelo_nao_mandam_nada(settings):
    """WP-08: o laço do agente e a triagem por modelo de texto saíram; a rota sozinha não declara nada."""
    _deepseek_e_jev()
    _rotas(
        {
            "default": {"connection": "anthropic-catalogo"},
            "concierge": {"connection": "deepseek"},
            "triage": {"connection": "deepseek"},
        }
    )

    assert active_ai_processors() == ()
    assert not {"concierge", "triage"} & set(USOS)
    assert not {"concierge", "triage"} & set(_customer_text_purposes())


# ── A frase é a que o código monta ───────────────────────────────────────
#
# A frase dos leitores (Jev, pré-rótulo e leitura de partes) é a do dono (16/11/2026):
# "Nome, documento, e-mail, telefone, endereço, pagamento, alergia ou doença que você
# escrever não são enviados". Os testes abaixo mandam uma fala com tudo isso pelo caminho
# de verdade e conferem o que chega ao provedor falso.
#
# ⚠️ Dois deles reprovam até o WP-03 do CONCIERGE-PLANO-DE-ACAO entrar, e é de propósito:
# são o contrato que ele cumpre (a leitura de partes sai redigida; o nome que o cliente
# escreve sai do texto). O PR deste inventário espera o WP-03 em rascunho.

FALA = (
    "Oi, aqui é a Maria Souza. Meu CPF é 123.456.789-09, o e-mail é maria@exemplo.com, o "
    "telefone (43) 99876-5432, moro na Rua das Flores, 120, tenho diabetes e sou alérgica "
    "a castanha. Tem croissant?"
)
TRECHOS_SEM_NOME = (
    "123.456.789-09",
    "maria@exemplo.com",
    "99876-5432",
    "Rua das Flores",
    "diabetes",
    "castanha",
)
TRECHOS_PESSOAIS = ("Maria", *TRECHOS_SEM_NOME)


def _jev_recebe(fala):
    from shopman.storefront.concierge import triage
    from shopman.storefront.concierge.intent_benchmark import Prediction

    enviado = []

    class JevFalso:
        def scores(self, sample, categories):
            enviado.append(sample.text)
            return Prediction(intents={})

    triage.jev_scores(fala, contender=JevFalso())
    assert enviado
    return enviado[0]


def _leitura_recebe(fala, nota=""):
    from shopman.storefront.concierge import intents

    pedidos = []

    class Mensagens:
        def create(self, **pedido):
            pedidos.append(pedido)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"acts": []}')])

    intents.read_with_model(fala, memory_note=nota, client=SimpleNamespace(messages=Mensagens()))
    assert pedidos
    return str(pedidos[0]["messages"])


def _sem(trechos, enviado, quem):
    for trecho in trechos:
        assert trecho not in enviado, (
            f"{quem} recebeu {trecho!r}, e /privacidade diz que nome, documento, e-mail, "
            "telefone, endereço, pagamento, alergia ou doença escritos na mensagem não são "
            "enviados."
        )


def test_o_jev_nao_recebe_documento_contato_endereco_nem_saude():
    assert USOS["decision"].redacts is True and USOS["decision"].keeps_profile is True
    enviado = _jev_recebe(FALA)
    assert "croissant" in enviado
    _sem(TRECHOS_SEM_NOME, enviado, "O Jev")


def test_o_jev_nao_recebe_o_nome_que_o_cliente_escreve():
    """Contrato do WP-03: o nome que o cliente escreve ("aqui é a Maria") sai do texto.
    Reprova até ele entrar."""
    _sem(("Maria", "Souza"), _jev_recebe(FALA), "O Jev")


def test_a_leitura_nao_recebe_dado_pessoal():
    """Contrato do WP-03: a leitura de partes manda o texto redigido, e a nota de estado
    não leva o número do pedido. Reprova até ele entrar; hoje a fala sai como veio."""
    assert USOS["intents"].redacts is True
    _conexao("deepseek", base_url="https://api.deepseek.com/anthropic")
    enviado = _leitura_recebe(FALA, nota="Pedido aberto do cliente: pedido ABC123 (novo).")
    assert "croissant" in enviado
    _sem((*TRECHOS_PESSOAIS, "ABC123"), enviado, "A leitura de partes")


# ── O texto que o cliente lê ─────────────────────────────────────────────


def test_a_frase_dos_leitores_e_a_do_dono():
    for purposes in ({"decision"}, {"intents"}, {"labeling"}, {"decision", "intents", "labeling"}):
        role, shares = ai_role_and_shares(purposes)
        assert role == "ajuda o atendimento automático do WhatsApp a entender a sua mensagem"
        assert shares == (
            "só o texto da sua mensagem. Nome, documento, e-mail, telefone, endereço, "
            "pagamento, alergia ou doença que você escrever não são enviados: a loja apaga "
            "tudo isso do texto antes"
        )
        # "Anonimizado" promete, na LGPD, que não dá para saber quem é: não é o que a loja faz.
        assert "anonimiz" not in shares


def test_o_que_nao_vai_vem_logo_depois_do_so():
    """Decisão do dono (16/11): o cliente lê primeiro o limite e o que NÃO vai."""
    for purposes in ({"decision"}, {"intents"}):
        _role, shares = ai_role_and_shares(purposes)
        frases = shares.split(". ")
        assert frases[0].startswith("só "), shares
        assert "não vão" in frases[1] or "não são enviados" in frases[1], shares


def test_frases_de_ia_sem_travessao_nem_jargao():
    _conexao("anthropic", liberada=True)
    _conexao("deepseek", base_url="https://api.deepseek.com/anthropic")
    _conexao("jev", protocol=AIProtocol.JEV)
    _rotas(
        {
            "default": {"connection": "anthropic"},
            "intents": {"connection": "deepseek"},
            "decision": {"connection": "jev"},
        }
    )
    processors = active_ai_processors()
    assert {processor.key for processor in processors} == {p.key for p in AI_PROCESSORS}

    proibidas = ("gateway", "endpoint", "webhook", "api", "backend", "token", "payload", "prompt", "modelo")
    combinacoes = [{use.purpose} for use in AI_USES] + [{use.purpose for use in AI_USES}]
    frases = [f"{p.role} {p.shares}" for p in processors] + [" ".join(ai_role_and_shares(c)) for c in combinacoes]
    for frase in frases:
        assert "—" not in frase and "–" not in frase, frase
        achadas = [palavra for palavra in proibidas if palavra in frase.lower().replace(",", " ").split()]
        assert not achadas, f"jargão: {achadas}: {frase}"
