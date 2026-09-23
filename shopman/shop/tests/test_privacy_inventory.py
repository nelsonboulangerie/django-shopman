"""A trava que impede a política de privacidade de envelhecer em silêncio.

Em 23/09/2026 a varredura achou CINCO terceiros recebendo dado de cliente sem estarem
na lista que a página chamava de "a lista inteira" — entre eles um que recebia o IP do
titular em HTTP puro. Nenhum entrou por descuido de quem escreveu o adapter: entraram
por commits legítimos, meses depois de o texto ter sido escrito.

O defeito não era o texto: era **o texto ser uma cópia da verdade em vez de uma vista
dela**. Cópia não tem como saber que a verdade mudou.

Esta trava fecha o caminho pelo qual os cinco entraram: adapter que fala com a internet
precisa ter dono declarado em `shopman/shop/privacy_inventory.py` — ou constar da
isenção, com motivo escrito. Um adapter novo reprova aqui até alguém responder "o que
isto manda para fora?", que é exatamente a conversa que não aconteceu naquelas cinco
vezes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shopman.shop.privacy_inventory import (
    ADAPTERS_SEM_DADO_DE_CLIENTE,
    PROCESSORS,
    active_processors,
)

ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "adapters"

#: O sinal de que um módulo fala com a internet. Grosso de propósito: falso positivo
#: custa uma linha de isenção; falso negativo custa um operador não declarado.
FALA_COM_A_INTERNET = re.compile(r"requests\.|httpx\.|urlopen\(|https?://[a-z]", re.IGNORECASE)


def adapters_que_saem() -> set[str]:
    encontrados = set()
    for arquivo in ADAPTERS_DIR.glob("*.py"):
        if arquivo.name.startswith("_") or arquivo.name == "__init__.py":
            continue
        if FALA_COM_A_INTERNET.search(arquivo.read_text(encoding="utf-8")):
            encontrados.add(arquivo.stem)
    return encontrados


def test_todo_adapter_que_sai_tem_dono_declarado():
    reivindicados = {nome for processor in PROCESSORS for nome in processor.adapters}
    orfaos = adapters_que_saem() - reivindicados - set(ADAPTERS_SEM_DADO_DE_CLIENTE)

    assert not orfaos, (
        "Estes adapters falam com a internet e ninguém declarou o que eles mandam para "
        f"fora: {sorted(orfaos)}.\n"
        "Se mandam dado de cliente, declare um Processor em "
        "shopman/shop/privacy_inventory.py — a política passa a dizer, e o cliente "
        "passa a saber.\n"
        "Se não mandam, acrescente o módulo a ADAPTERS_SEM_DADO_DE_CLIENTE com o motivo."
    )


def test_isencao_nao_guarda_adapter_que_deixou_de_existir():
    # Isenção órfã é pior que ausência: ela afirma, para quem ler, que alguém conferiu.
    existentes = {arquivo.stem for arquivo in ADAPTERS_DIR.glob("*.py")}
    fantasmas = set(ADAPTERS_SEM_DADO_DE_CLIENTE) - existentes
    assert not fantasmas, f"Isenção para adapter que não existe mais: {sorted(fantasmas)}"


def test_adapter_reivindicado_existe():
    existentes = {arquivo.stem for arquivo in ADAPTERS_DIR.glob("*.py")}
    for processor in PROCESSORS:
        sumidos = set(processor.adapters) - existentes
        assert not sumidos, (
            f"O operador {processor.key} reivindica adapter que não existe: "
            f"{sorted(sumidos)}. Se a integração saiu, o operador sai da política junto."
        )


@pytest.mark.parametrize("processor", PROCESSORS, ids=lambda p: p.key)
def test_o_sinal_de_ligado_aponta_para_uma_setting_que_existe(processor, settings):
    """Sinal que aponta para setting inexistente é operador eternamente "desligado".

    É a falha mais traiçoeira deste desenho: renomear uma setting faria o operador
    sumir da política **sem nenhum erro**, e a página passaria a mentir por omissão —
    exatamente o defeito que este arquivo existe para impedir.
    """
    for sinal in processor.wired_by:
        tipo, _, alvo = sinal.partition(":")
        assert tipo == "setting", f"sinal desconhecido em {processor.key}: {sinal}"
        nome = alvo.partition("[")[0].strip()
        assert hasattr(settings, nome), (
            f"O operador {processor.key} diz depender da setting {nome}, que não existe. "
            "Se ela foi renomeada, ele está silenciosamente fora da política."
        )


def test_o_texto_do_cliente_nao_tem_jargao(settings):
    """`role` e `shares` são o que o cliente lê. Jargão aqui vira jargão na tela.

    A régua é `docs/reference/omotenashi-copy.md` §D7: o que o leitor não decifra, ele
    ignora — e numa política de privacidade ignorar é o pior resultado possível.
    """
    proibidas = ("gateway", "endpoint", "webhook", "API", "backend", "token", "payload")
    for processor in PROCESSORS:
        frase = f"{processor.role} {processor.shares}"
        achadas = [palavra for palavra in proibidas if palavra.lower() in frase.lower()]
        assert not achadas, f"jargão em {processor.key}: {achadas} — {frase}"


def test_active_processors_e_um_subconjunto_honesto():
    ativos = active_processors()
    assert set(ativos) <= set(PROCESSORS)
    # A loja não declara ao cliente um terceiro que este deployment não usa: seria
    # verdade no catálogo e mentira na vida dele.
    for processor in ativos:
        assert processor.wired_by, f"{processor.key} não tem como provar que está ligado"


@pytest.mark.parametrize("processor", PROCESSORS, ids=lambda p: p.key)
def test_o_sinal_de_ligado_realmente_liga(processor, settings):
    """Erro de digitação no caminho da setting esconde o operador para sempre.

    `test_..._aponta_para_uma_setting_que_existe` pega o rename; este pega o caminho
    errado dentro dela — `SHOPMAN_IFOOD[merchant]` em vez de `[merchant_id]` resolveria
    para `None` calado, e o operador nunca apareceria na política. É a mesma família do
    zero que não acende: a ausência não grita.
    """
    from shopman.shop.privacy_inventory import _setting_is_set

    sinal = processor.wired_by[0]
    alvo = sinal.partition(":")[2]
    nome, _, resto = alvo.partition("[")
    chaves = [parte.strip("[ ") for parte in resto.split("]") if parte.strip()]

    valor: object = "valor-de-teste"
    for chave in reversed(chaves):
        valor = {chave: valor}
    setattr(settings, nome.strip(), valor)

    assert _setting_is_set(alvo), (
        f"O sinal `{sinal}` do operador {processor.key} não resolve nem quando a setting "
        "está preenchida — o caminho dentro dela está errado, e ele ficaria fora da "
        "política em silêncio."
    )
