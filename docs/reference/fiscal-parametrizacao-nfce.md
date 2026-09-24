# Parametrização fiscal — NFC-e (Nelson, Simples Nacional / SEFA-PR)

> Fonte: orientação do escritório contábil ("PROCEDIMENTO E PARAMETRIZAÇÃO", SEFA-PR) +
> decisões do projeto. Registrado/destilado em 2026-06-29. Referência canônica da configuração
> fiscal; a implementação vive no plano [FISCALMAN-PLAN](../plans/FISCALMAN-PLAN.md) e na persona
> `shopman.fiscalman`. **Validar os NCMs com o contador antes da emissão real.** O caso 5102-vs-5101 está
> decidido (5102, 2026-08-19) — ver [CFOP 5101 × 5102](fiscal-cfop-5101-vs-5102.md).

## 1. Regime

- **Simples Nacional — CRT-01.** Documento emitido: **NFC-e (modelo 65)**, intraestadual (PR).
- NF-e (modelo 55) interestadual: fora de escopo hoje (venda a consumidor de outro estado é rara).

## 2. Perfis fiscais (o perfil responde só: tem ST ou não)

Os parâmetros que dependem da operação vivem em 2 perfis nomeados (`shopman/fiscalman/classification.py`);
por produto guarda-se `profile` + `ncm` + `cest` + `unit` (em `Product.metadata["fiscal"]`).

| Perfil | Aplica a | CSOSN | CFOP interno | CFOP interest. | Origem | PIS CST | COFINS CST |
|---|---|---|---|---|---|---|---|
| `standard` (sem ST) | o que a casa faz (pães, salgados, doces, bebidas preparadas, caixas presente) e a revenda fora da ST do PR (queijo, manteiga, azeite, geleia, picles, presunto cru, chá em folhas) | **102** | **5102** | 6102 | 0 | **99** | **99** |
| `tax_substitution` (com ST) | revenda sujeita a ST no PR: refrigerantes, água, mostarda preparada, cremes de queijo (requeijão e similares) | **500** | **5405** | 6405 | 0 | **99** | **99** |

**O CEST é atributo do produto, não do perfil** (decisão do dono, 24/09/2026). Ele identifica a
mercadoria no catálogo de segmentos do Conv. ICMS 142/2018 e não define tributação — quem define é
o CSOSN/CFOP do perfil. É aceito em qualquer perfil, vai na NFC-e sempre que presente, é
obrigatório só com ST, e o sistema o confere contra o NCM pela tabela do Anexo
(`fiscalman/cest_table.py`) como **aviso**, nunca bloqueio.

- O contador classifica "alimentação em geral, salgados, doces" como **comercialização (5102/102)**,
  não produção própria (5101). Sob Simples o CFOP não altera o imposto (recolhido no DAS).
- Revenda: usar o **NCM da nota fiscal de compra** do produto. CEST obrigatório (7 dígitos) por item.
- **CEST na revenda sem ST (24/09/2026).** O Conv. ICMS 142/2018 (cl. 20ª, I; cl. 3ª estende ao
  Simples) manda informar o CEST do item listado nos Anexos II a XXVI "ainda que a operação não
  esteja sujeita ao regime de substituição tributária"
  ([CV142_18](https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18)); o RICMS/PR
  repete no Anexo X, art. 1º, §§ 1º e 5º. A SEFAZ não rejeita CSOSN 102 sem CEST (a rejeição 806 é
  só para CST/CSOSN de ST), mas a obrigação existe — daí o CEST valer em qualquer perfil.
- **O que está na ST do PR** (RICMS/PR, Anexo IX, art. 118): mostarda preparada 2103.30.21
  (17.038.00), condimentos 2103.90.21/.91 (17.035.00), requeijão e similares (17.023.00). Saíram em
  1º/11/2019 (Decreto 2.673/2019): azeite, geleias/doces (2007), picles (2001). Fora: queijos 0406,
  manteiga, presunto cru.
- **Decidido pela prática da casa (dono, 24/09/2026)** — a planilha de produtos do Yooga mostra o que
  o contador já aplicava: mostardas e cremes Pomerode com ST (500/5405), creme de queijo 17.023.00.
  Berinjela e churrasquinho: a casa usava 2103.90.99 + 17.092.00, incoerente com o Anexo; fica a
  correção (berinjela 2005.99.00 + 17.092.00; churrasquinho sem CEST). O que sobrar, **a próxima
  NF-e de compra confirma**: o recebimento compara NCM/CEST/ST do fornecedor com o cadastro e avisa.
- **Produção própria:** 1905.90.90 → 17.062.00 (a casa já usava), 1905.90.10 → 17.060.00 ("outros
  pães de forma" — ⚠️ a casa emitia as baguetes no 1905.90.90), 2005.99.00 → 17.092.00. Bebida
  preparada no balcão (2202.99.00) segue sem CEST: o Anexo descreve o industrializado pronto para
  beber, e não é isso que a casa vende. Tabela em `apply_fiscal_ncm.HOUSE_CEST_BY_NCM`.
- A tabela por item mora em `config/management/commands/apply_grocery_catalog.py` (`GROCERY`,
  `SEED_RESALE_FISCAL`, `FISCAL_NOTES`).

## 3. NCM por produto (catálogo atual — todos não-ST)

> Propostos por análise; **validar com o contador**. Sob Simples a NCM importa para conformidade/ST.

| Grupo | NCM | Itens |
|---|---|---|
| Pães | `19059010` | baguetes, batard, fendu, ciabatta, focaccias, pão de forma, challah, brioches, campagne… |
| Folhados/doces | `19059090` | croissant, pain au chocolat, chausson, bichon, cornet, melon pan, madeleine… |
| Salgados/pratos | `19059090` ⚠️ | deli, hotdog, croque, quiches, tartines — *ou* `21069090` (decisão do contador) |
| Café (espresso) | `21011110` | espresso, espresso duplo |
| Café c/ leite | `21011200` | cappuccino, latte |
| Chocolate quente | `18069000` | chocolate quente |
| Chá | `09024000` | chá earl grey |
| Suco | `20091200` | suco de laranja (espremido na hora) |

## 4. Setup de conta / SEFAZ (obrigatório p/ go-live — **não é código nosso**)

Vive no painel do **Focus NFe** e/ou na **SEFA-PR**, configurado por Pablo/contador:

- [ ] **Credenciamento** como emissor NFC-e (mod. 65) na SEFA-PR — NPF.101/2014 (conf. NPF.063/2012).
- [ ] **CSC** (Código de Segurança do Contribuinte) gerado na SEFA-PR — homologação **e** produção.
      No Focus NFe vive na conta, não no nosso payload. Credencial de go-live além de `FOCUS_NFE_TOKEN`/CNPJ.
- [ ] **CRT-01** (Simples) configurado na conta Focus NFe (por CNPJ).
- [ ] **Imposto aproximado** (Lei 12.741/12, IBPT "De Olho no Imposto") habilitado na conta Focus NFe —
      ele preenche automaticamente por NCM. Obrigatório na NFC-e.

## 5. Obrigações operacionais (rotina do usuário/contábil)

- **Cancelamento:** só dentro de **24h** da autorização **e** se a mercadoria não circulou (PR).
- **SPED Fiscal mensal (XML):** entregar ao escritório contábil após a última nota do mês, com
  compras, vendas e estoque + documentos.
- Manter **estoque** e **compras** alimentados no sistema (entrada de mercadorias ao receber).

## 6. Pendências de validação com o contador

- [ ] NCMs da tabela (esp. salgados/tartines `19059090` vs `21069090`; café `2101.x`).
- [x] CFOP `5102`: **decidido pelo dono em 2026-08-19** e já valendo no código (a Nelson
      fabrica o que vende mas não é registrada como **indústria**, e sob Simples o CFOP não
      altera o DAS). Falta só a **ratificação** do contador — nada espera por ela para emitir.
      Razão, vozes alinhadas e o que muda se ele discordar:
      [CFOP 5101 × 5102](fiscal-cfop-5101-vs-5102.md).
- [ ] Quais itens de revenda (ST) entram, e seus NCM/CEST.
