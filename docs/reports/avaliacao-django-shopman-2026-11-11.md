# Avaliação técnica do Django Shopman

**11/11/2026 · Base `8830a72bf82670f03601be69457e77fcc61bebd6` · Revisão adversarial contra a mesma base, com reprodução**

O Shopman modela bem a operação da Nelson e está mais consistente sobre quem decide preço, estoque, estado do pedido e dinheiro. A fragilidade central está nos gestos que atravessam esses domínios, e o caso mais caro é o custo da fornada: a margem por lote que o B.I. publica hoje pode mostrar prejuízo integral para uma fornada vendida inteira. Prioridade antes de usar margem por lote em decisão de mix: suprimir a margem sem receita atribuída, capturar o custo no fechamento e alinhar os centavos ao contrato. Depois disso, ensaiar a operação e a promoção.

## Escopo e evidência

A avaliação original foi uma leitura estática do código, dos contratos e dos testes no SHA acima, com as nove guardas da Constituição e os verificadores de superfície passando. A revisão adversarial refez cada afirmação contra a mesma base e **escreveu um teste mínimo para cada defeito de código. Os quatro testes falham hoje** (`4 failed in 26.98s`). Ficaram sem verificação a suíte completa contra o ambiente implantado e os fluxos com dispositivos e provedores reais. Os riscos das tabelas por app orientam o ensaio e não descrevem incidentes observados.

| # | Achado | Veredito | Severidade |
|---|---|---|---|
| 1 | Fechamento da fornada pode perder o custo | Confirmado, com o mecanismo corrigido abaixo | P1 |
| 2 | Margem por fornada mistura custo integral com receita parcial | Confirmado; o caso do lote diário é mais estreito do que dizia a primeira leitura | P1 |
| 3 | Custo congelado diverge do contrato de arredondamento | Confirmado, e maior: o unitário também viola o contrato | P2 |
| 4 | Código crítico concentrado nas bordas | Contagens confirmadas; o risco é leitura de projeto | P2 |
| 5 | Promoção verifica identidade antes de comportamento | Confirmado | P2 hoje, P1 na virada |

## Achados prioritários e correções propostas

### 1. Fechamento da fornada pode perder o custo histórico

**Evidência.** `CraftExecution.finish` emite `production_changed` depois do seu `atomic` interno ([execution.py:681](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/packages/craftsman/shopman/craftsman/services/execution.py#L681)). O receiver do custo é um `resilient_receiver`: registra a exceção em log e segue ([production_cost.py:41](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/handlers/production_cost.py#L41)). O reenvio idempotente devolve a fornada antes de emitir o signal ([execution.py:352](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/packages/craftsman/shopman/craftsman/services/execution.py#L352)). A fachada do Shop recompõe estoque e vínculo com pedidos, mas não o custo ([production.py:1049](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/services/production.py#L1049)), e nenhum sweeper lê `cost_snapshot`.

**O que a revisão corrigiu.** No caminho do operador há um `atomic` externo ([backstage/services/production.py:3125](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/backstage/services/production.py#L3125)). Ali, se o processo cair, tudo é desfeito, e a baseline ("mesma transação") vale. O buraco real é outro: **uma exceção dentro do receiver é engolida**, e a fornada fecha com estoque gravado e sem custo, para sempre. Reprodução: depois do fechamento e de dois reenvios, o estoque está gravado e `cost_snapshot` continua ausente.

**O que a primeira leitura não viu.**
- Recompor o custo depois não devolve o valor original: `_line_unit_cost` lê o custo preferencial do momento da recomposição. Só a captura no próprio fechamento cumpre o ADR-023.
- O Admin do Craftsman ([craftsman/admin.py:60](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/packages/craftsman/shopman/craftsman/admin.py#L60)) e a API do Craftsman fecham fornada sem passar pela fachada do Shop: não recompõem nada e não gravam um lote por fornada.

**Solução preferida.** Capturar o custo (valores ou lacunas) dentro da transação do fechamento orquestrado pelo Shop, sem que o Craftsman passe a conhecer custo. Exceção ali grita ou vira lacuna explícita no snapshot, nunca log calado. Decidir se o fechamento pelo Admin e pela API do Craftsman continua existindo; se continuar, ele passa pela mesma orquestração.

**Aceite.** Forçar exceção no cálculo do custo: o fechamento falha ou grava lacuna com motivo. Reenviar duas vezes: o snapshot aparece uma vez, com os valores do instante do fechamento. Mudar o custo preferencial depois: o snapshot não muda. Estoque e vínculos não duplicam.

### 2. Margem por fornada mistura custo integral com receita parcial

**Evidência.** A receita vem só das vendas dentro da janela, e sem receita atribuída o cálculo usa zero e desconta o custo inteiro: `revenue_q = revenue.get(wo.ref, 0)` e `margin_q = revenue_q - total_q` ([bi_production.py:198-211](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/backstage/projections/bi_production.py#L198)). A atribuição depende de holds cumpridos e de origem única lida no texto de `Move.reason`.

**Reprodução.** Uma fornada de custo R$ 18,00 vendida inteira no dia seguinte por R$ 100,00 aparece com margem de **−R$ 18,00** na janela do dia e +R$ 82,00 na janela de dois dias. Num lote compartilhado, as duas fornadas saem com −R$ 18,00 cada.

**O que a revisão corrigiu.** "Duas fornadas no mesmo lote diário" é mais estreito do que parecia. O fechamento do operador grava um lote por fornada ([backstage/services/production.py:2092](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/backstage/services/production.py#L2092)). O lote diário só aparece no fechamento simples (Admin ou API do Craftsman) ou numa partição cuja soma não fecha ([contrib/stockman/handlers.py:973](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py#L973)). Mas toda fornada fechada por esse caminho aparece no B.I. com margem igual a menos o custo.

**O que a primeira leitura não viu.** Um teste do `main` consagra o defeito: `test_bi_v6.py::test_batch_margin_does_not_attribute_sales_from_a_shared_daily_batch` aceita receita zero sem exigir que a margem seja suprimida. O `cost_status` distingue custo ausente de incompleto, mas não existe status para receita não atribuída.

**Solução em duas etapas.** Primeiro, suprimir a margem quando a receita não estiver atribuída ou a fornada ainda tiver saldo, mostrar a cobertura e corrigir o teste que consagra o defeito. Depois, persistir o vínculo explícito entre saída da fornada, movimento e lote, e decidir o que a coluna mede: retorno acumulado da fornada até uma data de corte, ou margem das unidades vendidas no período com custo proporcional. Até lá, a margem por lote fica fora de decisão de mix.

**Aceite.** Venda no dia seguinte, venda parcial, lote compartilhado, ausência de vínculo e devolução: nenhum desses casos mostra margem negativa por falta de atribuição. O que foi atribuído e o que ficou indeterminado aparecem na tela. Os centavos reconciliam com a venda canônica.

### 3. O custo congelado diverge do contrato de arredondamento

**Evidência.** O contrato ([data-schemas.md:1986](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/docs/reference/data-schemas.md#L1986)) define `total_q` como a soma das linhas e `unit_cost_q` como `total_q` ÷ `output_quantity`. O código arredonda cada linha, mas calcula o total e o unitário a partir da soma decimal sem arredondar ([cost.py:204-218](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/adapters/cost.py#L204)).

**Reprodução.** Duas linhas de 0,6 centavo gravam `cost_q` 1 e 1, e `total_q` 1. A soma das linhas não bate com o total.

**O que a primeira leitura não viu.** O unitário também viola o contrato: com total decimal 2,5 e saída 2, o código grava 1 e o contrato manda 2 (`round(3 ÷ 2)`).

**Solução preferida.** Cumprir o contrato publicado: `total_q` é a soma dos `cost_q` das linhas, e `unit_cost_q` sai de `total_q`. Não há snapshot antigo a preservar: a chave nasceu em 11/11/2026 e nada foi produzido em operação real com ela.

**Aceite.** Frações de centavo, saída zero e lacuna. Em toda gravação completa, a soma das linhas é igual ao total, e o unitário segue a regra publicada.

### 4. Código crítico concentrado nas bordas

**Evidência.** As contagens conferem: `backstage/api/operations.py` tem 7.246 linhas, `shop/services/pos.py` 6.767, `usePosSale.ts` 4.668, `order_queue.py` 3.598 e `finalizar.vue` 2.608. O risco que se tira disso (decisões, efeitos e recuperação concentrados) é leitura de projeto, não defeito demonstrado.

**Solução preferida.** Delimitar por gesto operacional, depois do ensaio, que diz por onde começar. Caracterizar o comportamento de cada ponto de entrada antes de extrair código. Preservar a idempotência, os contratos e o dono de cada escrita.

**Aceite.** Cada gesto tem um ponto de entrada e resultados verificáveis no pedido, no pagamento e no estoque. Venda mista, reenvio, recusa e falha parcial mantêm o comportamento.

### 5. Promoção verifica identidade antes de verificar comportamento

**Evidência.** O `plan` de [promote-release.yml](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/.github/workflows/promote-release.yml) confere ancestralidade e digests, e o smoke funcional só roda depois do deploy. O `make test-migrations` migra a partir do banco vazio ([runtime-gate.yml:147-158](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/.github/workflows/runtime-gate.yml#L147)); nada testa a migração a partir da versão anterior. PDV, Cozinha, Gestor, Produção e Central dividem o grupo `operator-floor` ([groups.json](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/surfaces/operator-router/groups.json)).

**Solução preferida.** Ensaiar os mesmos digests num ambiente descartável, com configuração equivalente e integrações de teste, incluindo migração a partir do schema anterior. Manter a validação de identidade e o smoke depois da promoção.

**Aceite.** Uma falha funcional ou de migração impede a promoção. O ensaio deixa evidência de versão, cenário, resultado e estado final dos ledgers.

## Acertos a preservar

- **Autoridade explícita.** O Stockman decide a promessa e a reserva, o Offerman responde pelo preço de lista, o Orderman controla o ciclo do pedido e o Payman registra o dinheiro. Os PRs [#2263](https://github.com/nelsonboulangerie/django-shopman/pull/2263) e [#2277](https://github.com/nelsonboulangerie/django-shopman/pull/2277) tiraram as leituras paralelas da promessa.
- **Modelo aderente ao chão de loja.** Comanda, pedido, pagamento e turno são coisas distintas. A fornada preserva consumo, saída, qualidade e perda. O SKU comprável e vendável tem uma unidade e um estoque.
- **Regressões arquiteturais detectáveis.** Guardas de dependência, dinheiro, ledger e projeções, mais registro e versões alinhados nas superfícies. A guarda de autoridade cobre as decisões cadastradas.
- **Release rastreável.** Construção única, promoção por digest e identidade verificável por componente. A [leitura do custo congelado pelo B.I.](https://github.com/nelsonboulangerie/django-shopman/pull/2272) distingue custo ausente de incompleto; falta distinguir receita não atribuída (achado 2).

## Avaliação por app

Só as linhas que afirmam um fato foram reconferidas. As demais são recomendações de ensaio e seguem como estavam.

| Superfície | Acerto | Fragilidade e encaminhamento |
|---|---|---|
| PDV | Comanda, venda mista, custódia e fila idempotente. | Sem rede, a venda para quando a loja deixa a venda offline desligada. É chave da loja (`Shop.pos_offline_sale_enabled`), desligada no seed: escolha de configuração, não defeito. Decidir o valor de produção e ensaiar recuperação de cobrança e conciliação fiscal. O recibo do navegador recalculava desconto em R$ como percentual; a correção está no [#2284](https://github.com/nelsonboulangerie/django-shopman/pull/2284). |
| Loja online | A promessa considera saldo e fornada. | O checkout concentra estado. Testar combo, troca de data, reserva e retorno de pagamento no mesmo cenário. |
| Gestor de Pedidos | Fila dedicada e aceite sensível a encomenda e horário. | Projeção extensa e escopo de gestão amplo. Isolar as ações da fila com contratos próprios. |
| Produção | Planejamento, mise en place, fechamento e qualidade. | Tornar recuperáveis as consequências do fechamento, inclusive o custo (achado 1). |
| Cozinha / KDS | Estações, retirada e cancelamento visível no turno. | Ensaiar alteração ou cancelamento depois do envio, com reconexão do quadro. |
| Compras | Conversões, custo preferencial e revenda pelo mesmo SKU. | Mostrar insumo sem custo preferencial ou com unidade incompatível antes da fornada. |
| B.I. | Cobertura das medições, origem dos dados e custo congelado. | Margem por lote sem receita atribuída (achado 2). Mostrar a cobertura e adotar vínculo de origem explícito. |
| Marketing | Aprovação, idempotência e comprovante por tipo de publicação. | Ensaiar provedor que aceita a publicação e perde a resposta. Conferir a reconciliação antes de reenviar. |
| Central | Acesso e pendências num ponto só. | Mora no grupo `operator-floor` e cai junto com ele. Ensaiar o aviso de indisponibilidade pelo Status. |
| Status | Fora do grupo operacional. | Complementar a liveness com sinais de operação degradada, conforme as sondas disponíveis. |
| Kitchensink | Componentes compartilhados exercitados no navegador. | Validar também no consumidor, com teclado, cabeçalho e densidade reais. |
| Operator Kit e Router | BFF, SSE e interface reutilizados, grupos separados. | Mudança comum tem impacto amplo. Exercitar os consumidores críticos antes de promover. |

| App Django ou pacote | Acerto | Fragilidade e encaminhamento |
|---|---|---|
| Shop | Orquestra domínios e provedores. | Dividir os fluxos de POS, pagamento e fiscal por gesto e recuperação. |
| Backstage | Contratos de leitura e projeções protegidas contra escrita no kernel. | Reduzir a concentração de endpoints em `operations.py`. |
| Storefront Django | Validação de pedido e política compartilhada de data. | Distinguir falha técnica de indisponibilidade, inclusive na expansão de combos. |
| Orderman | Commit, eventos e idempotência. | O contrato transacional de `order_changed` é exceção declarada (ADR-025 §6, baseline da Constituição). Falta o teste que prova o desfazer do pedido sem estoque. |
| Stockman | Promessa, holds e movimentos com autoridade clara. | Gravar a origem estruturada do movimento, que hoje o B.I. lê do texto de `Move.reason`. |
| Craftsman | Ledger de consumo, produção, qualidade e perda. | O fechamento pelo Admin e pela API não passa pela orquestração do Shop (achados 1 e 2). |
| Offerman | Autoridade do preço de lista. | Mostrar o custo vivo com a origem dele, separado do custo histórico. |
| Buyman | Custo por fornecedor e conversão para a unidade de consumo. | Dizer se o custo preferencial é referência gerencial ou custo do insumo consumido. |
| Payman | Intents e transações por meio de pagamento. | Ensaiar captura e estorno com resposta externa incerta. |
| Cashman | Turno e livro-caixa append-only. | Conciliar a custódia com as transações do Payman, principalmente em venda mista. |
| Guestman | Contatos, identidades, merge e anonimização. | Exercitar fusão com colisão de identidades e conferir as referências afetadas. |
| Doorman | Verbos explícitos para OTP, passkey e confiança do dispositivo. | Ensaiar entrega e limites de código com clientes atrás do mesmo IP, como em CGNAT. |
| Fiscalman | Classificação separada do provedor fiscal. | Provar emissão, retorno e contingência no fluxo completo do Shop. |
| Watchman | Registry de sondas e identidade de release. | Medir degradação funcional além da saúde do processo. |
| Refs | Referências tipadas, auditoria e rename. | Cobrir as referências guardadas em JSON e texto que pedem registro ou validação. |
| Utils | Helpers compartilhados de dinheiro e unidades. | Testar a regra de arredondamento no contrato de cada fato que os usa (achado 3). |

## Ordem de execução

A revisão inverteu as duas primeiras etapas: o número enganoso já está na tela, e o ensaio não o tira de lá.

1. **Margem do B.I.** Suprimir a margem sem receita atribuída, mostrar a cobertura e corrigir o teste que consagra o defeito (achado 2, primeira etapa). É barato e tira do ar um prejuízo que não existe.
2. **Custo da fornada.** Capturar o snapshot na transação do fechamento, com falha explícita (achado 1), e alinhar os centavos ao contrato (achado 3). Decidir o destino do fechamento pelo Admin e pela API do Craftsman.
3. **Ensaio de operação e promoção.** Abertura de caixa, venda mista, perda de rede, recuperação de cobrança, encomenda com fornada futura, cancelamento depois do envio à cozinha, fechamento e emissão fiscal, com migração a partir do schema anterior. Conferir a tela do operador e o estado final dos ledgers.
4. **Manutenibilidade.** Extrair o fechamento e a recuperação de venda e de fornada depois de caracterizar os contratos deles, na ordem que o ensaio indicar.
5. **Vínculo explícito de origem** (achado 2, segunda etapa) e a decisão do dono sobre o que a margem por lote mede.

## Histórico

- **11/11/2026, avaliação original:** leitura estática no SHA base ([PR #2281](https://github.com/nelsonboulangerie/django-shopman/pull/2281), commit `45dd52301`).
- **11/11/2026, revisão adversarial:** cada afirmação refeita contra a mesma base. Defeitos 1 a 3 reproduzidos por teste. Os mecanismos dos achados 1 e 2 foram corrigidos e os pontos cegos acrescentados. A ordem de execução foi revista. O selo "Versão 1.0" saiu: relatório se identifica por data e assunto, e as versões ficam no histórico do git.
