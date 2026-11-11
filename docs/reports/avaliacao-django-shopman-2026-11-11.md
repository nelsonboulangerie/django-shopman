# Avaliação técnica do Django Shopman

**Versão 1.0 · 11/11/2026 · Base `8830a72bf82670f03601be69457e77fcc61bebd6`**

O Shopman modela bem a operação da Nelson e está mais consistente sobre quem decide preço, estoque, estado do pedido e dinheiro. A fragilidade central está na recuperação de gestos que atravessam esses domínios. Prioridade para a virada: ensaiar a operação com interrupções e corrigir a gravação do custo da fornada antes de usar a margem por lote em decisões de mix.

## Escopo e evidência

O SHA da análise foi confirmado como o `main` no GitHub. Inspeção independente do código, dos contratos e dos testes versionados, com exclusão das alterações locais. As nove guardas da Constituição passaram com a baseline vigente, assim como os verificadores de registro e versões das superfícies. O modo estrito apontou as exceções registradas de ciclo de pedido, ledger e signals. Foram verificações estáticas. A suíte completa, o ambiente implantado e os fluxos com dispositivos e provedores reais ficaram sem verificação. Os defeitos abaixo são demonstráveis pelo código. Os riscos descritos nas tabelas orientam a reavaliação, sem implicar incidentes observados. [Commit](https://github.com/nelsonboulangerie/django-shopman/commit/8830a72bf82670f03601be69457e77fcc61bebd6) · [Guardas](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/docs/reference/guard-map.md)

## Achados prioritários e correções propostas

### 1. Fechamento da fornada pode perder o custo histórico

**Evidência.** `CraftExecution.finish` emite `production_changed` após seu bloco `atomic` interno. O receiver de custo registra exceções em log. O reenvio idempotente deixa de emitir o signal novamente. A fachada recompõe estoque e vínculo com pedidos, porém não recompõe o custo. A baseline descreve o fechamento como escrita na mesma transação, uma garantia que o bloco interno do kernel por si só não entrega. [Execução](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/packages/craftsman/shopman/craftsman/services/execution.py#L655) · [Recuperação](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/services/production.py#L1054) · [Receiver](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/handlers/production_cost.py) · [Baseline](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/scripts/constitution-baseline.json)

**Solução preferida.** Capturar valores de custo ou lacunas na transação que confirma o fechamento, preservando a independência do Craftsman por meio da orquestração do Shop. Se o snapshot final for assíncrono, gravar na mesma transação uma tarefa durável com os valores já capturados. Corrigir a descrição da fronteira transacional na baseline.

**Aceite.** Interromper entre fechamento e materialização, alterar o custo preferencial e reenviar duas vezes. O snapshot deve aparecer uma vez com os valores originais. Lacunas reais ficam explícitas. O estoque e os vínculos não duplicam.

### 2. Margem por fornada mistura custo integral com receita parcial

**Evidência.** O período filtra tanto a data da fornada quanto a data da venda. Atribuição depende de holds cumpridos e de origem única inferida de texto em `Move.reason`. Sem receita atribuída, o cálculo usa zero e deduz o custo integral. Uma venda no dia seguinte, saldo ainda disponível e perda de rastreabilidade podem produzir o mesmo número. A UI já rotula a coluna como margem sobre a receita rastreada. [Projeção](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/backstage/projections/bi_production.py#L168) · [Tabela](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/surfaces/bi-nuxt/app/components/ProductionLots.vue#L71)

**Solução em duas etapas.** Primeiro, mostrar cobertura e suprimir a margem quando a atribuição for indeterminada. Depois, persistir vínculo explícito entre saída da fornada, movimento e lote de estoque. Definir se o relatório mede retorno acumulado da fornada até uma data de corte ou margem das unidades vendidas no período, com custo proporcional às saídas atribuídas. Até essa decisão e a validação da cobertura, manter a métrica fora da QME.

**Aceite.** Testar venda no dia seguinte, venda parcial, duas fornadas no mesmo lote diário, ausência de vínculo e devolução. Expor o que foi atribuído e o que permanece indeterminado. Reconciliar centavos com a venda canônica.

### 3. O custo congelado diverge do contrato de arredondamento

**Evidência.** O schema define `total_q` como soma das linhas e `unit_cost_q` a partir de `total_q`. O código arredonda linhas individualmente e calcula total e custo unitário a partir da soma decimal original. Duas linhas de 0,6 centavo gravam 1 centavo cada e total de 1 centavo. [Schema](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/docs/reference/data-schemas.md#L1986) · [Cálculo](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/adapters/cost.py#L181)

**Solução preferida.** Cumprir o contrato publicado. Se for necessário arredondar o agregado uma única vez, distribuir o resíduo entre as linhas com regra determinística e derivar o unitário do total gravado. Preservar snapshots existentes e explicitar a regra aplicável a cada versão, se necessário.

**Aceite.** Testar frações de centavo, saída zero e lacuna. Nas novas gravações completas, a soma das linhas deve bater com o total e o unitário deve seguir a regra publicada.

### 4. Código crítico concentrado nas bordas

**Evidência.** `backstage/api/operations.py` tem 7.246 linhas, `shop/services/pos.py` 6.767, `usePosSale.ts` 4.668, `order_queue.py` 3.598 e `finalizar.vue` 2.608. O risco vem da concentração de decisões, efeitos e recuperação nesses fluxos.

**Solução preferida.** Delimitar por gesto operacional. Começar com fechamento e recuperação de venda no PDV, depois recuperação da fornada. Caracterizar o comportamento dos pontos de entrada antes de extrair código. Preservar idempotência, contratos e propriedade das escritas.

**Aceite.** Cada gesto tem um ponto de entrada e resultados verificáveis no pedido, pagamento e estoque pertinentes. Venda mista, reenvio, recusa e falha parcial mantêm o comportamento esperado.

### 5. Promoção verifica identidade antes de verificar comportamento

**Evidência.** O workflow reaproveita os manifests por digest, exige aprovação e comprova o SHA no ambiente. No modelo pós-go-live, o `plan` verifica ancestralidade e digests antes da promoção. O smoke funcional desta esteira roda depois. PDV, Cozinha, Gestor, Produção e Central compartilham um grupo de deploy. [Promoção](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/.github/workflows/promote-release.yml) · [Grupos](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/surfaces/operator-router/groups.json)

**Solução preferida.** Ensaiar os mesmos digests em ambiente representativo e descartável antes da promoção, com configuração equivalente e integrações de teste. Incluir atualização do schema a partir da versão anterior. Preservar a validação de identidade e o smoke pós-promoção.

**Aceite.** Uma falha funcional ou de migração impede a promoção. O ensaio deixa evidência de versão, cenário, resultado e estado final dos ledgers.

## Acertos a preservar

- **Autoridade explícita.** Stockman decide a promessa e a reserva, Offerman responde pelo preço de lista, Orderman controla o ciclo do pedido e Payman registra o dinheiro. Os PRs [#2263](https://github.com/nelsonboulangerie/django-shopman/pull/2263) e [#2277](https://github.com/nelsonboulangerie/django-shopman/pull/2277) reduziram a divergência entre promessa da vitrine e reserva.
- **Modelo aderente ao chão de loja.** Comanda, pedido, pagamento e turno são distintos. A fornada preserva consumo, saída, qualidade e perda. Um SKU comprável e vendável compartilha unidade coerente e estoque.
- **Regressões arquiteturais detectáveis.** Guardas de dependência, dinheiro, ledger e projeções, além de registro e locks alinhados nas superfícies. A guarda de autoridade cobre as decisões cadastradas.
- **Release rastreável.** Construção única, promoção por digest e identidade verificável por componente. A [leitura do custo congelado pelo B.I.](https://github.com/nelsonboulangerie/django-shopman/pull/2272) já distingue ausência e incompletude do custo.

## Avaliação por app

| Superfície | Acerto | Fragilidade e encaminhamento |
|---|---|---|
| PDV | Comanda, venda mista, custódia e fila idempotente. | A venda offline desativada bloqueia cobrança sem rede. Ensaiar recuperação de cobrança e conciliação fiscal. |
| Loja online | Promessa considera saldo e fornada. | Checkout concentra estado. Testar combo, troca de data, reserva e retorno de pagamento no mesmo cenário. |
| Gestor de Pedidos | Fila dedicada e aceite sensível a encomenda e horário. | Projeção extensa e escopo de gestão amplo. Isolar ações da fila com contratos próprios. |
| Produção | Planejamento, mise en place, fechamento e qualidade. | Tornar recuperáveis as consequências do fechamento, inclusive o custo. |
| Cozinha / KDS | Estações, retirada e cancelamento visível no turno. | Ensaiar alteração ou cancelamento após encaminhamento com reconexão do quadro. |
| Compras | Conversões, custo preferencial e revenda pelo mesmo SKU. | Evidenciar insumo sem custo preferencial ou com unidade incompatível antes da fornada. |
| B.I. | Cobertura de medições, origem dos dados e custo congelado. | Expor cobertura da atribuição de vendas e adotar vínculo de origem explícito. |
| Marketing | Aprovação, idempotência e comprovante por tipo de publicação. | Ensaiar provedor que aceita a publicação e perde a resposta. Conferir reconciliação antes de reenviar. |
| Central | Acesso e pendências em um ponto único. | A Central pode cair junto com os apps do grupo. Ensaiar a comunicação de indisponibilidade pelo Status. |
| Status | Superfície externa ao grupo operacional. | Complementar liveness com sinais de operação degradada, conforme sondas disponíveis. |
| Kitchensink | Componentes compartilhados exercitados no navegador. | Validar também no consumidor, com teclado, cabeçalho e densidade reais. |
| Operator Kit e Router | BFF, SSE e interface reutilizados, grupos separados. | Mudanças comuns têm impacto amplo. Exercitar consumidores críticos antes de promover. |

| App Django ou pacote | Acerto | Fragilidade e encaminhamento |
|---|---|---|
| Shop | Orquestra domínios e provedores. | Dividir fluxos de POS, pagamento e fiscal por gesto e recuperação. |
| Backstage | Contratos de leitura e projeções protegidas contra escrita no kernel. | Reduzir concentração de endpoints em `operations.py`. |
| Storefront Django | Validação de pedido e política compartilhada de data. | Distinguir falha técnica de indisponibilidade, inclusive na expansão de combos. |
| Orderman | Commit, eventos e idempotência. | Tornar explícito e testar o contrato transacional da garantia de estoque em `order_changed`. |
| Stockman | Promessa, holds e movimentos com autoridade clara. | Manter identidade estruturada de origem para o consumidor financeiro. |
| Craftsman | Ledger de consumo, produção, qualidade e perda. | Verificar recuperação entre fechamento e realização de cada efeito obrigatório. |
| Offerman | Autoridade do preço de lista. | Exibir custo vivo com sua origem e distinguir do custo histórico. |
| Buyman | Custo por fornecedor e conversão para unidade de consumo. | Explicitar se o custo preferencial representa referência gerencial ou custo do insumo consumido. |
| Payman | Intents e transações por meio de pagamento. | Ensaiar captura e estorno com resposta externa incerta. |
| Cashman | Turno e livro-caixa append-only. | Conciliar custódia e transações do Payman, especialmente em venda mista. |
| Guestman | Contatos, identidades, merge e anonimização. | Exercitar fusão com colisão de identidades e conferir referências afetadas. |
| Doorman | Verbos explícitos para OTP, passkey e confiança do dispositivo. | Ensaiar entrega e limites de código com clientes atrás do mesmo IP, como em CGNAT. |
| Fiscalman | Classificação separada do provedor fiscal. | Provar emissão, retorno e contingência no fluxo completo do Shop. |
| Watchman | Registry de sondas e identidade de release. | Medir degradação funcional além da saúde do processo. |
| Refs | Referências tipadas, auditoria e rename. | Cobrir fontes de referências em JSON e texto que exigem registro ou validação. |
| Utils | Helpers compartilhados de dinheiro e unidades. | Testar a regra de arredondamento no contrato do fato que os usa. |

## Ordem de execução

1. **Ensaio de operação e promoção.** Abertura de caixa, venda mista, perda de rede, recuperação de cobrança, encomenda com fornada futura, cancelamento após envio à cozinha, fechamento e emissão fiscal. Conferir a tela do operador e o estado final dos ledgers.
2. **Custo e B.I.** Capturar o custo de forma recuperável, alinhar os centavos e declarar a cobertura antes de usar margem por fornada em decisão de mix.
3. **Manutenibilidade.** Extrair fechamento e recuperação de venda e de fornada após caracterizar seus contratos. Os resultados do ensaio orientam a ordem das demais extrações.
