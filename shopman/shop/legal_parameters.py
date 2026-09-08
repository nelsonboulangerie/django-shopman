"""Parâmetros do sistema que vêm da LEI — e a data em que alguém conferiu.

## Por que este módulo existe

A legislação brasileira de alimentos muda com frequência. Quando um parâmetro do
sistema copia a lei e ninguém revisita, o sistema passa a **ensinar o gestor a
errar**: ele confia na tela, a tela repete uma norma revogada, e a
responsabilidade de não ter seguido a lei acaba recaindo sobre quem operou de
boa-fé.

Já aconteceu aqui: até 08/09/2026 o código citava a **RDC 26/2015** como norma
vigente de alérgenos. Ela havia sido **revogada** e consolidada na **RDC
727/2022**. O número errado estava em comentário, em docstring e em mensagem de
erro — todos escritos com confiança.

Por isso a regra da casa passa a ser: **parâmetro que vem da lei declara de qual
norma veio e quando foi conferido.** O CI cobra a revisão; não depende de alguém
lembrar.

## Como usar

Ao conferir uma norma — mesmo que nada tenha mudado — atualize `conferido_em` e
`conferido_por`. "Conferi e continua valendo" é informação, e é ela que a
catraca mede.

Ao descobrir que a norma mudou, atualize `norma`, o valor, e **escreva o que
mudou** em `nota`. O histórico importa mais que o valor atual.

⚠️ Isto NÃO é aconselhamento jurídico e não substitui a leitura da norma. É um
lembrete com data, para que ninguém confie num número velho por esquecimento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Quanto tempo um parâmetro legal pode ficar sem alguém olhar. Um ano é o
#: intervalo em que a ANVISA costuma publicar revisão relevante de rotulagem —
#: e é curto o bastante para a conferência caber numa tarde, em vez de virar
#: projeto.
JANELA_DE_REVISAO_DIAS = 365


@dataclass(frozen=True)
class ParametroLegal:
    """Um número ou regra que a lei define, e o rastro de quem o conferiu."""

    chave: str
    norma: str
    valor: str
    conferido_em: date
    conferido_por: str
    #: Onde LER a norma. É o que transforma "confira" em "clique e leia" para
    #: quem tem a responsabilidade e não mexe em código.
    fonte: str = ""
    #: Identificador persistente do LexML, quando a norma tem um. Serve para
    #: rastrear substituição no futuro — ver a nota sobre automação no topo.
    urn: str = ""
    nota: str = ""

    def vencido_em(self, hoje: date) -> bool:
        return (hoje - self.conferido_em).days > JANELA_DE_REVISAO_DIAS


PARAMETROS: tuple[ParametroLegal, ...] = (
    ParametroLegal(
        chave="alergenos_declaracao_obrigatoria",
        norma="RDC 727/2022 (consolidou a RDC 26/2015, revogada)",
        valor="19 alimentos/grupos de declaração obrigatória + látex natural",
        conferido_em=date(2026, 9, 8),
        conferido_por="Pablo",
        fonte="https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2015/rdc0026_26_06_2015.pdf",
        urn="urn:lex:br:ministerio.saude;agencia.nacional.vigilancia.sanitaria:resolucao.diretoria.colegiada:2022-07-01;727",
        nota=(
            "⚠️ A RDC 26/2015 foi REVOGADA e consolidada na 727/2022 sem mudança "
            "de mérito. O código citava a revogada até 08/09/2026. A lista da casa "
            "é SUPERCONJUNTO da norma: inclui `mostarda` (obrigatória na UE, não no "
            "Brasil) e `pimenta-do-reino` (nenhuma norma lista; a casa usa e já "
            "houve reação). Superconjunto erra para o lado seguro."
        ),
    ),
    ParametroLegal(
        chave="limiar_sem_lactose",
        norma="RDC 135/2017",
        valor="< 100 mg/100 g para 'zero lactose' / 'sem lactose' / 'não contém lactose'",
        conferido_em=date(2026, 9, 8),
        conferido_por="Pablo",
        fonte="https://www.legisweb.com.br/legislacao/?id=337142",
        urn="urn:lex:br:ministerio.saude;agencia.nacional.vigilancia.sanitaria:resolucao.diretoria.colegiada:2017-02-08;135",
        nota=(
            "Entre 100 mg e 1 g/100 g: 'baixo teor de lactose'. Acima de 100 mg: "
            "'contém lactose'. Produto sem ingrediente lácteo está em zero — a "
            "afirmação é sobre COMPOSIÇÃO e é verificável pela ficha."
        ),
    ),
    ParametroLegal(
        chave="declaracao_gluten",
        norma="Lei 10.674/2003",
        valor="'contém glúten' / 'não contém glúten' obrigatório para alimento industrializado",
        conferido_em=date(2026, 9, 8),
        conferido_por="Pablo",
        fonte="https://www.planalto.gov.br/ccivil_03/leis/2003/l10.674.htm",
        urn="urn:lex:br:federal:lei:2003-05-16;10.674",
        nota=(
            "A obrigação é dirigida a INDÚSTRIA alimentícia; a AGU firmou que não "
            "se estende a estabelecimento não industrial que vende direto ao "
            "consumidor. A casa não afirma ausência de glúten em produto nenhum: "
            "não há segregação e não se pretende ter (decisão do dono, 08/09/2026). "
            "O que existe é a declaração POSITIVA de que pode conter."
        ),
    ),
    ParametroLegal(
        chave="pode_conter_contaminacao_cruzada",
        norma="RDC 727/2022",
        valor="'Alérgicos: Pode conter …' quando não se pode garantir ausência",
        conferido_em=date(2026, 9, 8),
        conferido_por="Pablo",
        fonte="https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2015/rdc0026_26_06_2015.pdf",
        urn="urn:lex:br:ministerio.saude;agencia.nacional.vigilancia.sanitaria:resolucao.diretoria.colegiada:2022-07-01;727",
        nota=(
            "⚠️ PENDENTE: a norma exige que esta declaração se baseie num "
            "**Programa de Controle de Alergênicos**. Não sei se a casa tem o "
            "programa formalizado — perguntado ao dono em 08/09/2026, sem resposta "
            "até aqui. Enquanto não houver, o aviso é honesto mas não está "
            "documentado como a norma pede."
        ),
    ),
)


def vencidos(hoje: date | None = None) -> list[ParametroLegal]:
    """Os parâmetros que ninguém confere há mais de um ano."""
    hoje = hoje or date.today()
    return [p for p in PARAMETROS if p.vencido_em(hoje)]
