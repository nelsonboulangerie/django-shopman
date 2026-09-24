"""Aplica o NCM revisado das bebidas preparadas (WP-CATALOGO-PUBLICAVEL).

Usage::

    python manage.py apply_fiscal_ncm            # só mostra o que mudaria
    python manage.py apply_fiscal_ncm --apply    # grava

**Por que existe.** O catálogo do alpha declarava, na NFC-e, códigos que
descrevem outra coisa — e cinco bebidas caíam no *default* do seed, que é
``19059090``: **produto de padaria**. Um Caffè Latte declarado como pão não é
um detalhe de cadastro; é o que sai impresso na nota.

**O raciocínio, em uma linha.** O capítulo 22 da NCM é o das **bebidas prontas
para consumo**; o 21.01 e o 21.06 são das **preparações que servem para fazer
bebida** (pó solúvel, extrato, concentrado). O que a casa entrega no balcão é a
bebida pronta — então o endereço é o 22, e dentro dele o ``2202.99.00``
("outras bebidas não alcoólicas"), que a posição 2202 define como tudo que não
é água aromatizada/adoçada nem suco da posição 20.09.

**O que este comando NÃO decide**, e está escrito produto a produto:

- **O CEST fica vazio.** Os CEST que existem para o ``2202.99.00``
  (``17.113.00`` bebidas prontas à base de chá, ``17.114.00`` à base de café,
  ``17.115.00`` à base de leite ou cacau) descrevem o **industrializado pronto
  para beber** que circula com substituição tributária. O que a casa prepara no
  balcão não é esse produto, e preencher um CEST ali declararia uma ST que não
  existe. Quem confirma é o contador.
- **As duas sodas da casa são a pergunta que tem dinheiro dentro.** O
  ``2202.10.00`` descreve literalmente o que elas são (água gaseificada
  aromatizada e adoçada) — e é **o único código da posição 2202 alcançado pelo
  Imposto Seletivo** (LC 214/2025, Anexo XVII), a partir de 2027. O
  ``2202.99.00`` fica de fora do IS. Os dois são defensáveis, e a escolha não é
  minha: a tabela mantém o ``2202.10.00`` que já estava lá e marca a pergunta.

Revisão feita em 23/09/2026 a pedido do dono ("revise você; o contador só
revisa depois"). Fontes no relatório
``docs/reference/ncm-bebidas-preparadas.md``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

#: (sku, NCM revisado, o que o código de hoje realmente descreve).
#: Só bebida PREPARADA na casa. Revenda de industrializado não entra aqui: o
#: NCM dela vem da NF-e do fornecedor.
NCM_REVISADO: tuple[tuple[str, str, str], ...] = (
    # ── Café: o que se entrega é a bebida, não o pó ──────────────────────────
    ("SP", "22029900", "21011110 é café SOLÚVEL — pó, não a xícara"),
    ("COAD", "22029900", "21011110 é café SOLÚVEL — pó, não a xícara"),
    ("CAP", "22029900", "21011200 é preparação à base de extrato de café"),
    ("CAPMO", "22029900", "21011200 é preparação à base de extrato de café"),
    ("FRAP", "22029900", "21011200 é preparação à base de extrato de café"),
    ("VIEN", "22029900", "21011200 é preparação à base de extrato de café"),
    ("SPMC", "22029900", "19059090 é PRODUTO DE PADARIA (caía no default)"),
    ("CAFL", "22029900", "19059090 é PRODUTO DE PADARIA (caía no default)"),
    ("MOCHA", "22029900", "19059090 é PRODUTO DE PADARIA (caía no default)"),
    # Sai do catálogo por decisão dele; enquanto existe, é bebida como as outras.
    ("CE", "22029900", "21011200 é preparação à base de extrato de café"),
    # ── Leite e cacau ────────────────────────────────────────────────────────
    ("CHOQ", "22029900", "19059090 é PRODUTO DE PADARIA (caía no default)"),
    # ── Chá: o que se entrega é a infusão, não a folha ───────────────────────
    ("CHBLU", "22029900", "09024000 é folha de chá preto a granel, acima de 3 kg"),
    ("CHCAM", "22029900", "09024000 é folha de chá preto a granel, acima de 3 kg"),
    ("CHROU", "22029900", "09024000 é folha de chá preto a granel, acima de 3 kg"),
    ("CHSOP", "22029900", "09024000 é folha de chá preto a granel, acima de 3 kg"),
    ("SFTCH", "22029900", "09024000 é folha de chá preto a granel, acima de 3 kg"),
    ("CHHIB", "22029900", "19059090 é PRODUTO DE PADARIA (caía no default)"),
    ("CTFV", "22029900", "19059090 é PRODUTO DE PADARIA (caía no default)"),
    # ── A soda da casa (decisão dele, 23/09) ─────────────────────────────────
    # Ele leu certo: "a soda cai em preparação de balcão". E o argumento é mais
    # forte do que parecia — o Imposto Seletivo sobre bebida açucarada só
    # alcança o que está em EMBALAGEM PRIMÁRIA, "aquela em contato direto com o
    # produto e destinada ao consumidor final" (LC 214/2025, art. 409, §1º, V).
    # Soda tirada na torneira e servida no copo não tem embalagem primária, e o
    # IS não a alcança em NCM nenhum. Sem esse peso na balança, sobra a
    # classificação pura — e o que o cliente leva é a mesma bebida preparada que
    # as outras dezessete.
    ("SDLA", "22029900", "22021000 é o código do refrigerante em embalagem"),
)

#: CEST de quem a casa faz, pelo NCM (Anexo XVII do Conv. ICMS 142/2018; a
#: lei manda informá-lo mesmo sem ST, e o CEST não muda a tributação). É a
#: prática da casa — a planilha de produtos do Yooga já saía com 17.062.00 nos
#: pães de 1905.90.90 —, conferida contra o Anexo em 24/09/2026:
#:
#: - 1905.90.90 → 17.062.00 "Outros pães, exceto o classificado no CEST
#:   17.062.03" (pães, folhados, doces, salgados de forno, caixas presente);
#: - 1905.90.10 → 17.060.00 "Outros pães de forma" — ⚠️ o seed põe baguetes e
#:   ciabattas no 1905.90.10; a casa as emitia no 1905.90.90 (17.062.00). Fica
#:   o CEST que o Anexo dá ao NCM de hoje; se o NCM mudar, o CEST acompanha;
#: - 2005.99.00 → 17.092.00 (Ratatouille, Tapenade: hortícolas preparados).
#:
#: As bebidas preparadas (2202.99.00) ficam SEM CEST de propósito — ver AVISOS.
#: Só preenche CEST vazio: CEST já escrito é curadoria de alguém.
HOUSE_CEST_BY_NCM: dict[str, str] = {
    "19059090": "1706200",
    "19059010": "1706000",
    "20059900": "1709200",
}


#: O que o comando repete toda vez, para não virar silêncio. Não é pergunta
#: pendente: é o contorno da decisão, que muda se a casa mudar de prática.
AVISOS: tuple[str, ...] = (
    "CEST vazio (decisão dele, 23/09): os CEST do 2202.99.00 — 17.113.00 chá, "
    "17.114.00 café, 17.115.00 leite/cacau — descrevem o INDUSTRIALIZADO pronto "
    "para beber, que circula com substituição tributária. O que a casa prepara "
    "no balcão não é esse produto, e o perfil do catálogo é o sem ST.",
    "⚠️ O dia em que a casa ENGARRAFAR a soda para vender, a conta muda: aí há "
    "embalagem primária destinada ao consumidor final, o NCM passa a ser o "
    "2202.10.00 e a casa vira FABRICANTE de bebida açucarada — contribuinte do "
    "Imposto Seletivo na primeira operação, sem crédito a aproveitar. Servida no "
    "copo, nada disso acontece.",
)


def house_cest_for(ncm: str) -> str:
    return HOUSE_CEST_BY_NCM.get(ncm, "")


def fill_house_cest() -> list[tuple[str, str, str]]:
    """Grava o CEST pelo NCM onde ele está vazio. Devolve ``(sku, ncm, cest)``."""
    from shopman.offerman.models import Product

    filled: list[tuple[str, str, str]] = []
    for product in Product.objects.filter(metadata__fiscal__ncm__in=list(HOUSE_CEST_BY_NCM)).order_by("sku"):
        metadata = dict(product.metadata or {})
        fiscal = dict(metadata.get("fiscal") or {})
        if fiscal.get("cest"):
            continue
        cest = house_cest_for(fiscal.get("ncm") or "")
        fiscal["cest"] = cest
        metadata["fiscal"] = fiscal
        product.metadata = metadata
        product.save(update_fields=["metadata"])
        filled.append((product.sku, fiscal["ncm"], cest))
    return filled


class Command(BaseCommand):
    help = "Aplica o NCM revisado das bebidas preparadas (aguarda revisão do contador)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando só mostra o que mudaria.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import Product

        apply = options["apply"]
        out = self.stdout

        produtos = {
            p.sku: p
            for p in Product.objects.filter(sku__in=[s for s, _n, _p in NCM_REVISADO])
        }

        trocas: list[tuple[str, str, str, str, str]] = []
        ausentes: list[str] = []
        cests: list[tuple[str, str, str]] = []
        with transaction.atomic():
            for sku, ncm, porque in NCM_REVISADO:
                produto = produtos.get(sku)
                if produto is None:
                    ausentes.append(sku)
                    continue
                metadata = produto.metadata if isinstance(produto.metadata, dict) else {}
                fiscal = metadata.get("fiscal") if isinstance(metadata.get("fiscal"), dict) else {}
                atual = (fiscal.get("ncm") or "").strip()
                if atual == ncm:
                    continue
                metadata = {**metadata, "fiscal": {**fiscal, "ncm": ncm}}
                produto.metadata = metadata
                produto.save(update_fields=["metadata"])
                trocas.append((sku, produto.name, atual or "(vazio)", ncm, porque))
            cests = fill_house_cest()
            if not apply:
                transaction.set_rollback(True)

        verbo = "Feito" if apply else "Faria"
        if trocas:
            out.write(self.style.SUCCESS(f"\n{verbo}: {len(trocas)} NCM revisado(s)."))
            for sku, nome, atual, ncm, porque in trocas:
                out.write(f"  {sku:8s} {nome[:32]:32s} {atual} → {ncm}")
                out.write(f"           {porque}")
        else:
            out.write(self.style.SUCCESS("\nNada a revisar: todos já estão no NCM revisado."))

        if cests:
            out.write(self.style.SUCCESS(f"\n{verbo}: CEST em {len(cests)} produto(s) da casa."))
            for sku, ncm, cest in cests:
                out.write(f"  {sku:8s} NCM {ncm} → CEST {cest}")

        if ausentes:
            out.write(f"\n{len(ausentes)} fora do catálogo deste banco: {', '.join(sorted(ausentes))}")

        for aviso in AVISOS:
            out.write(self.style.WARNING(f"\n{aviso}"))

        if not apply:
            out.write(self.style.WARNING("\n(ensaio: nada gravado. Para gravar: --apply)"))
