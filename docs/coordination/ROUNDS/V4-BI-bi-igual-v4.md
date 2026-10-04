# V4-BI: o B.I. igual à prévia v4

- **id:** V4-BI
- **branch:** claude/v4-bi
- **PR:** #1456
- **estado:** PR aberto, auto-merge ligado (o dono autorizou merge direto nesta onda)
- **início (UTC):** 2026-10-04

## Objetivo
Onda "tudo igual à v4" (ordem do dono, 04/10). O B.I. (`surfaces/bi-nuxt`) veste a camada visual da
suíte (UX-KIT-V1/V2, modelo: Gestor) e a forma LEITURA da prévia `bi-sobra.jpg`: título é a pergunta,
logo abaixo a resposta em uma frase, números com a comparação, quadros para aprofundar.

## O que entrou
**Leitura nova "Sobrou ou faltou?" (Produção, a tela da prévia):** projeção
`shopman/backstage/projections/bi_over_short.py` + `GET /api/v1/backstage/bi/over-short/?day=`
(`backstage.view_bi`). Por produto do dia: fez (realizado dos lotes fechados), vendeu (vendas
conciliadas do B.I.), acabou às (a venda em que o vendido alcançou o feito), vendas perdidas estimadas
(a régua da sugestão do Craftsman: ritmo até acabar, estendido ao fechamento, teto 2×), veredito
faltou/sobrou/na medida, típico e histórico dos últimos 4 dias iguais (mesma régua de dia confiável da
sugestão), lotes e vendas por hora. Sem tabela nova, sem migração, sem chave JSON nova.

**Visual:** `data-suite="v3"`; `BiNav` (rail da suíte com as oito leituras e os ícones da prévia, Avisos no
pé; barra do polegar no celular) no lugar do `BiTopBar`; `OperatorPageHeader` em todas as telas com a
pergunta como título; "A resposta" e os cartões de número da prévia; tabela da prévia (etiqueta cheia,
barra fez × vendeu com tracejado e traço do típico, "Ver lotes e vendas" que abre no lugar); gráficos no
latão da suíte com o traço de comparação na cor do texto.

**Kit (aditivo, atrás de `suite:`):** `OperatorPeriodPicker` vira um controle só (‹ · botão · ›) dentro de
`data-suite="v3"`, como o período da prévia. Afeta também o Histórico do Gestor (já está na suíte).
`guardrails.appBar.test.ts`: o B.I. sai da lista da barra de seções e entra na do rail da suíte.

## Função (não regride)
Todas as leituras, a janela de análise na URL (agora no cabeçalho de cada tela; na Produção, no quadro
"Como foram os lotes no período?"), cenários salvos do Explorar (#1446), aproveitamento do #1439,
tempo de forno, Projeção com o próprio período, Cenários com IA. Novos: Copiar link (⋯), Avisos,
teclas `[` `]` `/` na Produção.

## Fechamento às cegas
O Caixa do B.I. já exigia `cashman.audit_shift`, que só o grupo Dono concede: é a "auditoria do Dono"
onde a decisão §15 permite o número. O cabeçalho agora diz isso. Se o dono quiser só % e veredito também
ali, falta o esperado por turno na leitura do B.I.

## O que a prévia mostra e o B.I. não calcula (dado que falta)
- "R$ de custo" da sobra: não existe CostBackend (`OFFERMAN["COST_BACKEND"] = None`); o cálculo está
  pronto e acende quando houver custo.
- "iFood, Meta e Google indisponíveis às 10:40 (automático)": não há registro de quando cada canal tirou
  o produto do ar.
- "'Me avise' do site: 5 clientes": mora no storefront (`StockAlertSubscription`); o backstage não o importa.
- "Abrir os 44 pedidos": o Gestor não filtra pedidos por produto e dia.
- "Sem 3º lote: o plano dizia 44": o planejado do dia não viaja na leitura.
- "Levar ao plano" (o porquê ao lado da sugestão): é do app de Produção; aqui o botão abre o Planejamento
  do próximo dia igual. Achado: `OrderingDemandBackend` nunca preenche `soldout_at`, então a sugestão não
  corrige a falta; a hora que este PR deriva poderia alimentá-la (Core, outra frente).

## Prova visual
`scratchpad/ux/v4-bi/index.html` da sessão coordenadora (+ `img/`).
