# EXCELÊNCIA-PRODUCAO: revisão de excelência do app Produção

Siga `docs/coordination/ROUNDS/EXCELENCIA-base.md` (objetivo, lentes, método, entrega e
limites). Este arquivo diz só o que é da Produção. Entregue em
`docs/plans/EXCELENCIA-PRODUCAO-PLANO.md`.

Compromisso: DEV-2026-079.

"Produção" aqui é o app das fornadas (`surfaces/production-nuxt`, `prod.`), nunca o ambiente
de deploy.

**Ênfase: a fornada é a fonte da promessa.** Tudo o que a loja, o PDV e o Gestor prometem
sobre pão nasce do que a Produção planeja, abre e confirma. A maior parte do esforço vai para
a cadeia Planejado → Produzido → Concluído e para o que ela diz aos outros apps, sem abandonar
o resto.

## Perímetro (onde os WPs podem escrever)

- `surfaces/production-nuxt/`, todas as páginas: `/` (o dia), `/plan`, `/mise-en-place`,
  `/board`, `/close`, `/quality`, `/reports`, `/timers` e `/recipes`;
- o que só a Produção consome no backstage: `projections/production.py`,
  `services/production.py` e as APIs `api/_production_*.py` e `api/production_freshness.py`.

## Fronteiras (registrar, não mexer)

- O Core em `packages/craftsman` (receitas, WorkOrders, `craft.suggest`, `craft.needs`) e
  `packages/stockman` (lotes, validade, ledger). Mudança ali só com a prova escrita de que o
  Core não resolve, e nunca neste plano.
- `shop/production_lifecycle.py` e os services do `shop` que leem a fornada para prometer:
  disponibilidade, `product_promise`, encomenda.
- O B.I. (`projections/bi_production.py`, `bi-nuxt`): a Produção grava, o B.I. lê. Registre o
  que falta gravar, não o que falta mostrar.
- O Compras (insumos, falta de material) e o Catálogo (ficha, validade, "feito na hora",
  ADR-040).
- A Cozinha (KDS), que monta o pedido com produto já em estoque. Preparo de pedido não é
  WorkOrder.
- O `operator-kit/`.

## Papéis

- Quem opera o chão com PIN, do grupo Produção.
- O Gerente.
- O Dono, só no que é dele (relatórios com valor agregado).
- O cliente, pela loja, e a Caixa, pelo PDV, para criar a demanda e as encomendas que a
  fornada precisa honrar.
- Nunca o superusuário.

## Jornadas pela UI

1. **A véspera**: abrir o Planejamento de amanhã, ler a sugestão e o porquê dela, ajustar e
   confirmar. Inclua sábado planejado na sexta, a volta de feriado e um dia fechado.
2. **A madrugada**: mise en place, abrir o lote, timers do forno, confirmar o produzido
   ("Quanto foi produzido?") e mandar à Expedição, até virar estoque real.
3. **A fornada que muda**: rendimento diferente do planejado, lote cancelado, lote que atrasa,
   falta de insumo na abertura e no fim.
4. **A encomenda que depende da fornada**: o cliente encomenda pela loja e a Caixa pelo PDV,
   para uma data com lote e para uma data sem lote (o "pedido à Produção" que o PDV já cria,
   WP-E3). Confira o que a Produção vê, quando vê e o que pode fazer; e o que acontece com a
   encomenda paga quando o lote dela é cancelado (o P0 do Gestor).
5. **Qualidade e perda**: conferência, perda com motivo (ADR-017) e etiqueta interna
   (ADR-028).
6. **O fechamento do dia**: `/close`, sobra que vira "Ontem", lote aberto na virada do dia, e o
   que fica gravado de verdade para o B.I. (carimbo por etapa, `soldout_at`, rendimento).
7. **O painel `/board`** num tablet e numa TV, de relance, a dois metros.
8. **Receitas**: criar, revisar e comparar versões; a receita sem insumo cadastrado.

Faça tudo em tablet (o uso principal do chão), em 375 px e em 1366 px.

## Histórico (não refaça)

- Memórias `project_production_excellence_plan`, `project_producao_continuar_unico_e_timers_opcionais`,
  `project_timers_e_kds_decisoes_18_09`, `feedback_production_vs_sales`,
  `feedback_production_steps_must_have_timestamps`, `feedback_sobra_de_hoje_nao_lastreia_encomenda`,
  `feedback_margem_da_fornada_fecha_na_validade` e `project_bi_axis_is_production_planning`.
- `docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` e a pasta
  `docs/plans/production-irrepressible-excellence-execution/`.
- `docs/plans/completed/PRODUCTION-EXCELLENCE-PLAN.md`, `FASE4-PRODUCAO-FOURNIL-PLAN.md` e
  `AVAILABILITY-SALE-PRODUCTION-PLAN.md`.
- `docs/plans/backstage-app-audits-2026-08-29/WP-05-producao.md` e
  a rodada `docs/coordination/ROUNDS/V4-PROD-producao-v4.md`.
- `docs/plans/PRODUCTION-FORECAST-BOARD-PLAN.md`,
  `docs/plans/WP-PRODUCTION-DATA-QUALITY-AND-LEGACY-RECOVERY-2026-09-29.md` e
  `docs/reference/processo-das-massas-proposta-2026-09-05.md`.
- ADR-007, ADR-017, ADR-028 e ADR-040.
- A decisão do dono de 16/11 sobre encomenda acima do plano e sem plano (`DECISIONS.md`,
  #2557, #2559) e o `EXCELENCIA-GESTOR-PLANO.md` (lote cancelado × encomenda paga).
- As issues `ficou-de-fora` abertas da Produção (#2385 a #2391, #2420). Leia antes de propor:
  o plano diz, para cada uma, se a absorve num WP, se ela continua como está ou se deve fechar
  como `not planned`.
- Os PRs recentes de 1024 px e do lote cancelado pela matriz (#2957, #2959, #2966).

## Foco

- **A fornada é a verdade da promessa**: o que a Produção planeja, abre, cancela e confirma
  chega à loja, ao PDV e ao Gestor sem atraso e sem tradução. Nenhuma tela de venda promete o
  que a fornada não sustenta, e a Produção sabe, antes de assar, o que já está prometido.
- **O chão não para**: mãos sujas, luvas, tablet na bancada. Um toque, número grande, nada que
  dependa de digitar. Se não obrigar vira adereço, se obrigar engessa.
- **O que fica gravado é verdade para o B.I.**: rendimento, horário de cada passo, falta e
  sobra, sem sobrescrever o passado. Derivar do dado que o cadastro já tem (validade, preparo,
  horário), nunca perguntar.

## Benchmarks

Galley e meez (receita e escala), Apicbase e MarketMan (produção e estoque de insumo),
FlexiBake e BakeSmart (padaria de produção), o planejamento de produção do Toast e do Square
for Restaurants, e Hotplate (pré-venda por fornada).

## Pilha isolada

- Django em `:8090`, banco `shopman_exc_producao`.
- Produção em `:3195`, loja em `:3190`, PDV em `:3192`, Gestor em `:3194`.
- Nenhuma outra porta.
