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

#: Quanto tempo um parâmetro legal pode ficar sem alguém olhar.
#: teto de revisão humana. A catraca é trimestral porque consulta pública,
#: consolidação e norma local podem mudar antes de um aniversário; o worker
#: não repete alerta enquanto o anterior continuar pendente.
JANELA_DE_REVISAO_DIAS = 90


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
        fonte=(
            "https://anvisalegis.datalegis.net/action/ActionDatalegis.php?"
            "acao=abrirTextoAto&cod_menu=8542&cod_modulo=310&link=S&"
            "numeroAto=00000727&orgao=RDC/DC/ANVISA/MS&seqAto=002&"
            "tipo=RDC&valorAno=2022"
        ),
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
        fonte="https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2017/rdc0135_08_02_2017.pdf",
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
        fonte=(
            "https://anvisalegis.datalegis.net/action/ActionDatalegis.php?"
            "acao=abrirTextoAto&cod_menu=8542&cod_modulo=310&link=S&"
            "numeroAto=00000727&orgao=RDC/DC/ANVISA/MS&seqAto=002&"
            "tipo=RDC&valorAno=2022"
        ),
        urn="urn:lex:br:ministerio.saude;agencia.nacional.vigilancia.sanitaria:resolucao.diretoria.colegiada:2022-07-01;727",
        nota=(
            "⚠️ PENDENTE: a norma exige que esta declaração se baseie num "
            "**Programa de Controle de Alergênicos**. Não sei se a casa tem o "
            "programa formalizado — perguntado ao dono em 08/09/2026, sem resposta "
            "até aqui. Enquanto não houver, o aviso é honesto mas não está "
            "documentado como a norma pede."
        ),
    ),
    ParametroLegal(
        chave="etiqueta_interna_preparo_armazenado",
        norma="RDC 216/2004, itens 4.8.17, 4.8.18 e 4.9.1",
        valor=(
            "designação + data de preparo + prazo de validade; sob refrigeração a 4 °C ou menos, prazo máximo de 5 dias"
        ),
        conferido_em=date(2026, 9, 10),
        conferido_por="Codex (levantamento técnico; validação do responsável pendente)",
        fonte="https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2004/res0216_15_09_2004.html",
        urn=(
            "urn:lex:br:ministerio.saude;agencia.nacional.vigilancia.sanitaria:"
            "resolucao.diretoria.colegiada:2004-09-15;216"
        ),
        nota=(
            "Aplica-se a serviços de alimentação, inclusive padarias. A etiqueta "
            "de operação deste sistema é exclusivamente interna e não substitui "
            "rótulo de venda. Normas estaduais/municipais podem complementar a "
            "RDC; confirmar o enquadramento com a VISA local. Validade deve vir de "
            "ficha/política aprovada: nunca presumir D+1."
        ),
    ),
    ParametroLegal(
        chave="rotulo_embalado_para_venda",
        norma="RDC 727/2022, arts. 2º, 7º–8º e 28–32",
        valor=(
            "rótulo comercial próprio com denominação, ingredientes, conteúdo "
            "líquido, origem, lote, validade e conservação, além das regras "
            "específicas aplicáveis"
        ),
        conferido_em=date(2026, 9, 10),
        conferido_por="Codex (levantamento técnico; validação do responsável pendente)",
        fonte=(
            "https://anvisalegis.datalegis.net/action/ActionDatalegis.php?"
            "acao=abrirTextoAto&cod_menu=8542&cod_modulo=310&link=S&"
            "numeroAto=00000727&orgao=RDC/DC/ANVISA/MS&seqAto=002&"
            "tipo=RDC&valorAno=2022"
        ),
        urn="urn:lex:br:ministerio.saude;agencia.nacional.vigilancia.sanitaria:resolucao.diretoria.colegiada:2022-07-01;727",
        nota=(
            "Não reutilizar ficha/etiqueta de pesagem interna como rótulo de "
            "venda. Venda remota, entrega, outra loja/filial ou terceiro pedem "
            "enquadramento próprio. Conteúdo líquido é quantidade real com tara "
            "descontada, não o alvo teórico de produção."
        ),
    ),
    ParametroLegal(
        chave="rotulagem_nutricional_proprio_estabelecimento",
        norma="RDC 429/2020, arts. 4º e 18; IN 75/2020, Anexo I",
        valor=(
            "tabela nutricional voluntária e rotulagem frontal opcional somente "
            "nos enquadramentos específicos de preparo/fracionamento e venda no "
            "próprio estabelecimento"
        ),
        conferido_em=date(2026, 9, 10),
        conferido_por="Codex (levantamento técnico; validação do responsável pendente)",
        fonte=(
            "https://anvisalegis.datalegis.net/action/ActionDatalegis.php?"
            "acao=abrirTextoAto&cod_menu=9434&cod_modulo=310&"
            "numeroAto=00000429&orgao=RDC/DC/ANVISA/MS&seqAto=000&"
            "tipo=RDC&valorAno=2020"
        ),
        urn="urn:lex:br:ministerio.saude;agencia.nacional.vigilancia.sanitaria:resolucao.diretoria.colegiada:2020-10-08;429",
        nota=(
            "A dispensa não é geral e não elimina os demais campos da RDC "
            "727/2022 nem o dever de informação do CDC. Alegação nutricional, "
            "enriquecimento/restauração ou bioativos podem afastar a faculdade."
        ),
    ),
    ParametroLegal(
        chave="conteudo_liquido_produto_pre_medido",
        norma="Portaria Inmetro 249/2021",
        valor="conteúdo líquido é a quantidade real do produto, excluída a embalagem",
        conferido_em=date(2026, 9, 10),
        conferido_por="Codex (levantamento técnico; validação do responsável pendente)",
        fonte=(
            "https://anmlegis.datalegis.net/action/ActionDatalegis.php?"
            "acao=abrirTextoAto&cod_menu=6783&cod_modulo=405&link=S&"
            "numeroAto=00000249&orgao=INMETRO/ME&seqAto=000&"
            "tipo=POR&valorAno=2021"
        ),
        nota=(
            "O alvo arredondado da balança serve à operação e nunca deve ser "
            "apresentado como PESO LÍQUIDO. Um futuro rótulo comercial precisa "
            "receber medição real com tara descontada."
        ),
    ),
)


def vencidos(hoje: date | None = None) -> list[ParametroLegal]:
    """Os parâmetros que ninguém confere há mais de uma janela trimestral."""
    hoje = hoje or date.today()
    return [p for p in PARAMETROS if p.vencido_em(hoje)]
