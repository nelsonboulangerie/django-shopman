# CFOP 5101 × 5102 — produção própria sai com **5101**

> **24/09/2026 — revisto.** A decisão de 19/08 (produção própria em 5102, "a
> Nelson não é registrada como indústria") foi revista na auditoria fiscal do
> alpha, com o dono mandando decidir por bom senso: o CFOP é tributação da
> operação e diz quem produziu o que se vende. **Produção própria → 5101**
> ("venda de produção do estabelecimento"); **revenda sem ST → 5102**; **revenda
> com ST → 5405**. Três perfis em `shopman/fiscalman/classification.py`
> (`own_production`, `resale`, `resale_tax_substitution`).
>
> Sob Simples Nacional (CRT-01) o CFOP não altera o imposto, recolhido no DAS.
> O 5101 está na lista de CFOPs aceitos na NFC-e (5101, 5102, 5103, 5104, 5115,
> 5405, 5656, 5667, 5933 — fora dela, rejeição 725):
> [TecnoSpeed](https://atendimento.tecnospeed.com.br/hc/pt-br/articles/360008266354-Rejei%C3%A7%C3%A3o-725-NFC-e-com-CFOP-inv%C3%A1lido),
> [Webmania](https://ajuda.webmaniabr.com/hc/pt-br/articles/4403755367437-Rejei%C3%A7%C3%A3o-725-NFC-e-com-CFOP-inv%C3%A1lido).
>
> ⚠️ A parametrização antiga do contador registrava "alimentação em geral,
> salgados, doces" como comercialização (5102/102). Se ele mantiver essa
> posição, a volta é um valor em `OWN_PRODUCTION` + o default do deployment +
> esta página (o teste `test_every_cfop_voice_says_the_same_thing` aponta as
> três vozes).

## Referência da tabela CFOP

| CFOP | Descrição |
|------|-----------|
| **5101** | Venda de produção do **estabelecimento** — o que a casa produz (`own_production`) |
| **5102** | Venda de mercadoria **adquirida ou recebida de terceiros** — revenda sem ST (`resale`) |
| 5405 | Venda de mercadoria adquirida de terceiros, **sujeita a ST**, na condição de contribuinte substituído (perfil `resale_tax_substitution`) |

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
