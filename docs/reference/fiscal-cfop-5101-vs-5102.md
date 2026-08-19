# CFOP 5101 × 5102 — decisão registrada: **5102**

> **Decisão do dono, 2026-08-19.** Fabricação própria emite **CFOP 5102**
> (interno) / **6102** (interestadual). Este documento era a pauta da pergunta;
> virou o registro da resposta, para que a próxima leitura encontre a razão junto
> do valor.
>
> Complementa [parametrização fiscal NFC-e](fiscal-parametrizacao-nfce.md) §2
> (tabela dos perfis) e §6 (pendências com o contador).

## A decisão

Para a venda de fabricação própria da padaria (pães, salgados, doces), a NFC-e
sai com **CFOP 5102** — venda de mercadoria adquirida ou recebida de terceiros —
e não 5101.

**Razão:**

1. **A Nelson fabrica o que vende, mas não é registrada como indústria.** O 5101
   é venda de produção do *estabelecimento industrial*; a condição é cadastral,
   não descritiva do processo de produção.
2. **Sob Simples Nacional (CRT-01) o CFOP não altera o imposto**, recolhido no
   DAS. O que o CFOP afeta é a escrituração e a coerência com o cadastro da
   atividade — e a coerência aponta para 5102.
3. É o que a [parametrização do contador](fiscal-parametrizacao-nfce.md) §2 já
   registrava: *"O contador classifica 'alimentação em geral, salgados, doces'
   como comercialização (5102/102), não produção própria (5101)."*

O perfil `own_production` cobre **fabricação própria + revenda comum** de
propósito (pães, salgados, doces, bebidas preparadas). Um CFOP único para os dois
é exatamente a simplificação que a decisão adota.

## Referência da tabela CFOP

| CFOP | Descrição |
|------|-----------|
| 5101 | Venda de produção do **estabelecimento** (o vendedor industrializou) |
| **5102** | Venda de mercadoria **adquirida ou recebida de terceiros** — **o nosso** |
| 5405 | Venda de mercadoria adquirida de terceiros, **sujeita a ST**, na condição de contribuinte substituído (perfil `resale`) |

Interestadual é a mesma família com prefixo 6 (6101/**6102**/6405).

## Uma voz — onde o 5102 está escrito

Antes da decisão, quatro lugares falavam sobre a mesma operação e três valores
diferentes apareciam. Hoje todos dizem 5102:

| Onde | O que diz |
|------|-----------|
| `packages/fiscalman/shopman/fiscalman/classification.py` — `OWN_PRODUCTION.cfop_internal` | `"5102"` / `"6102"` — **fonte executável**, é o que sai na nota |
| `packages/fiscalman/shopman/fiscalman/classification.py` — docstring de `FiscalProfile` | A decisão, com data, razão e esta referência |
| `packages/fiscalman/shopman/fiscalman/contrib/offerman/admin.py` — `help_text` de `fiscal_profile` | "Fabricação própria (**5102**/102)" — é o que o operador lê ao classificar |
| `config/settings.py` → `SHOPMAN_FOCUS_NFE["default_cfop_nfce"]` (env `FOCUS_NFE_NFCE_DEFAULT_CFOP`) | `"5102"` — fallback do adapter, mesmo valor do perfil |

As três vozes de runtime (dataclass, `help_text`, default do deployment) são
travadas por teste: `shopman/shop/tests/test_fiscal_admin_bridge.py`
::`test_every_cfop_voice_says_the_same_thing`. Divergiu, o teste quebra.

## O que falta: ratificação do contador

A decisão é do dono e **já está valendo no código**. A confirmação do escritório
contábil, quando vier, só precisa **ratificar** — não há nada esperando por ela
para o sistema emitir.

**Se o contador discordar** (ou seja, se ele apontar que a Nelson deve emitir
5101), o conserto é pequeno e está inteiro na tabela acima: trocar o valor no
perfil `own_production` (`cfop_internal`/`cfop_interstate`), no `help_text` do
Admin e no default do deployment, atualizar esta seção com a nova razão e a data,
e ajustar a linha da tabela de perfis em
[parametrização fiscal NFC-e](fiscal-parametrizacao-nfce.md) §2. Nenhuma migração,
nenhum dado por produto muda — o CFOP nunca foi gravado em `Product.metadata`,
vem sempre do perfil no momento da emissão. Notas já emitidas **não** se
corrigem sozinhas: quem decide o que fazer com elas é o contador.
