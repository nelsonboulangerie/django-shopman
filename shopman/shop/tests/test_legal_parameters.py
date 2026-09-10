"""Parâmetro que veio da LEI envelhece, e o repositório cobra.

A legislação brasileira de alimentos muda com frequência. Parâmetro copiado da
norma e nunca revisitado faz o sistema **ensinar o gestor a errar**: ele confia
na tela, a tela repete norma revogada, e a responsabilidade de não ter cumprido a
lei acaba recaindo sobre quem operou de boa-fé.

Não é hipótese. Até 08/09/2026 o código citava a **RDC 26/2015** como vigente —
revogada e consolidada na **RDC 727/2022**. O número errado estava em comentário,
docstring e mensagem de erro, todos escritos com confiança.

⚠️ Este teste falha pelo RELÓGIO, não por mudança de código. É de propósito: é a
única forma de a revisão acontecer sem depender de alguém lembrar. Quando ele
ficar vermelho, o conserto **não é mexer na data** — é ler a norma, confirmar (ou
corrigir) o valor, e então registrar a conferência.
"""

from __future__ import annotations

from datetime import date, timedelta

from shopman.shop.legal_parameters import (
    JANELA_DE_REVISAO_DIAS,
    PARAMETROS,
    ParametroLegal,
    vencidos,
)


def test_nenhum_parametro_legal_esta_vencido():
    """O CI lembra no lugar de alguém."""
    velhos = vencidos()
    assert not velhos, (
        "Parâmetro(s) de lei sem conferência há mais de "
        f"{JANELA_DE_REVISAO_DIAS} dias:\n"
        + "\n".join(f"  · {p.chave} ({p.norma}) — visto em {p.conferido_em}" for p in velhos)
        + "\n\nLeia a norma, confirme o valor e ATUALIZE `conferido_em`. "
        "Mexer só na data sem ler é o defeito que este teste existe para impedir."
    )


def test_todo_parametro_diz_de_onde_veio_e_quem_conferiu():
    """Sem norma e sem autor, o parâmetro é palpite com cara de lei."""
    for p in PARAMETROS:
        assert p.norma.strip(), f"{p.chave} não diz de qual norma veio"
        assert p.valor.strip(), f"{p.chave} não diz o que a norma define"
        assert p.conferido_por.strip(), f"{p.chave} não diz quem conferiu"


def test_a_janela_pega_o_vencido():
    """A catraca precisa medir o que promete — senão é decoração."""
    antigo = ParametroLegal(
        chave="x", norma="n", valor="v",
        conferido_em=date(2020, 1, 1), conferido_por="alguém",
    )
    assert antigo.vencido_em(date(2026, 1, 1))

    ontem = date.today() - timedelta(days=1)
    novo = ParametroLegal(
        chave="y", norma="n", valor="v",
        conferido_em=ontem, conferido_por="alguém",
    )
    assert not novo.vencido_em(date.today())


def test_a_lista_da_casa_cobre_o_que_o_sistema_usa():
    """Todo parâmetro legal que o código aplica precisa estar declarado aqui.

    Se um número da lei mora só no meio do código, ele não é revisado — e é
    exatamente esse o buraco que este módulo fecha.
    """
    chaves = {p.chave for p in PARAMETROS}
    esperadas = {
        "alergenos_declaracao_obrigatoria",
        "limiar_sem_lactose",
        "declaracao_gluten",
        "pode_conter_contaminacao_cruzada",
        "etiqueta_interna_preparo_armazenado",
        "rotulo_embalado_para_venda",
        "rotulagem_nutricional_proprio_estabelecimento",
        "conteudo_liquido_produto_pre_medido",
    }
    faltando = esperadas - chaves
    assert not faltando, f"parâmetro legal aplicado no código e não declarado: {faltando}"
