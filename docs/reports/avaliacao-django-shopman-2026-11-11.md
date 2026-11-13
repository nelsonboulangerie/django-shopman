# Avaliação técnica do Django Shopman

**11/11/2026 · Base `8830a72bf82670f03601be69457e77fcc61bebd6`**

O Shopman modela bem a operação da Nelson e está mais consistente sobre quem decide preço, estoque, estado do pedido e dinheiro. A fragilidade central está na recuperação de gestos que atravessam esses domínios. Prioridade para a virada: ensaiar a operação com interrupções e corrigir a gravação do custo da fornada antes de usar a margem por lote em decisões de mix.

## Escopo e evidência

O SHA da análise foi confirmado como o `main` no GitHub. Inspeção independente do código, dos contratos e dos testes versionados, com exclusão das alterações locais. As nove guardas da Constituição passaram com a baseline vigente, assim como os verificadores de registro e versões das superfícies. O modo estrito apontou as exceções registradas de ciclo de pedido, ledger e signals. Foram verificações estáticas. A suíte completa, o ambiente implantado e os fluxos com dispositivos e provedores reais ficaram sem verificação. A revisão independente no mesmo SHA registrou quatro testes de reprodução falhando: custo ausente após reenvio, divergência na soma em centavos, venda fora da janela e lote diário compartilhado. As tabelas por app registram características e cenários a verificar. [Commit](https://github.com/nelsonboulangerie/django-shopman/commit/8830a72bf82670f03601be69457e77fcc61bebd6) · [Guardas](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/docs/reference/guard-map.md)

## Achados prioritários e correções propostas

### 1. Fechamento pode confirmar a fornada sem custo histórico (P1)

**Evidência.** No fluxo do operador, o `atomic` externo protege contra queda do processo antes do commit. A baseline descreve corretamente esse fluxo. O receiver de custo captura exceções e deixa o fechamento prosseguir. O reenvio idempotente não reemite o signal, e a fachada recompõe estoque e vínculo com pedidos, mas não o custo. A revisão reproduziu pela fachada uma fornada fechada, com estoque realizado e sem snapshot mesmo após dois reenvios. [Fluxo do operador](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/backstage/services/production.py#L3125) · [Recuperação](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/services/production.py#L1054) · [Receiver](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/handlers/production_cost.py)

**Solução.** Capturar valores de custo ou lacunas na transação que confirma o fechamento. Se a materialização for assíncrona, gravar nessa mesma transação uma tarefa durável com os valores já capturados. Verificar também os pontos de entrada do Admin e da API do Craftsman. Reprocessar com o preço preferencial vigente em outra data altera o fato histórico.

**Aceite.** Testar pelo ponto de entrada do operador e pela fachada. Com falha na captura, o fechamento reverte. Com falha após captura durável, alterar o preço preferencial e reenviar duas vezes deve materializar um único snapshot com os valores originais, sem duplicar estoque ou vínculos. Lacunas reais ficam explícitas.

### 2. Margem por fornada mistura custo integral com receita parcial (P1 para uso gerencial)

**Evidência.** O período filtra a fornada e a venda. Uma fornada vendida integralmente no dia seguinte apareceu com −R$ 18 na janela de um dia e +R$ 82 na de dois dias. Atribuição depende de holds cumpridos e de origem única inferida de `Move.reason`. Sem atribuição, o cálculo usa receita zero e deduz o custo inteiro. O fechamento particionado do operador usa lotes por ordem. O escalar ou o fallback de partição pode usar lote diário compartilhado. O teste existente confirma a exclusão da receita ambígua e deixa a margem sem asserção. [Projeção](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/backstage/projections/bi_production.py#L168) · [Teste](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/backstage/tests/test_bi_v6.py#L397)

**Solução.** Suprimir a margem quando a atribuição for indeterminada, com cobertura e motivo visíveis. Persistir vínculo explícito entre saída da fornada, movimento e lote. Decidir se o relatório mede retorno acumulado da fornada até uma data de corte ou margem das unidades vendidas no período, com custo proporcional. Manter o indicador fora da QME até definir a leitura e validar a cobertura.

**Aceite.** Testar venda posterior, venda parcial, lote diário compartilhado, ausência de vínculo e devolução. Distinguir receita atribuída, saldo ainda sem venda e receita indeterminada. Reconciliar centavos com a venda canônica.

### 3. Custo congelado diverge do contrato de centavos (P2)

**Evidência.** Duas linhas de 0,6 centavo gravam 1 centavo cada e total de 1 centavo. Com custo exato de 2,5 centavos para duas unidades, o unitário sai 1 centavo a partir da soma decimal. Pelo contrato, o total gravado de 3 centavos produz unitário de 2 centavos. [Schema](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/docs/reference/data-schemas.md#L1986) · [Cálculo](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/shopman/shop/adapters/cost.py#L181)

**Solução.** Cumprir o contrato publicado. Se o total for arredondado uma única vez, distribuir o resíduo entre as linhas por regra determinística. Derivar o unitário do total gravado e preservar os snapshots existentes.

**Aceite.** Testar as duas identidades, soma das linhas igual ao total e unitário derivado do total, além de saída zero e custo com lacuna.

### 4. Código crítico concentrado nas bordas (P2 de manutenção)

**Evidência.** `backstage/api/operations.py` tem 7.246 linhas, `shop/services/pos.py` 6.767, `usePosSale.ts` 4.668, `order_queue.py` 3.598 e `finalizar.vue` 2.608. As contagens são verificadas. O risco de manutenção é uma avaliação da concentração de decisões, efeitos e recuperação nesses fluxos.

**Solução preferida.** Delimitar por gesto operacional. Começar com fechamento e recuperação de venda no PDV, depois recuperação da fornada. Caracterizar o comportamento dos pontos de entrada antes de extrair código. Preservar idempotência, contratos e propriedade das escritas.

**Aceite.** Cada gesto tem um ponto de entrada e resultados verificáveis no pedido, pagamento e estoque pertinentes. Venda mista, reenvio, recusa e falha parcial mantêm o comportamento esperado.

### 5. Promoção verifica identidade antes de verificar comportamento (P2, P1 na virada)

**Evidência.** O workflow reaproveita os manifests por digest, exige aprovação e comprova o SHA no ambiente. No modelo pós-go-live, o `plan` verifica ancestralidade e digests antes da promoção. O smoke funcional desta esteira roda depois, e o gate de migração citado exercita um banco vazio. PDV, Cozinha, Gestor, Produção e Central compartilham um grupo de deploy. [Promoção](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/.github/workflows/promote-release.yml) · [Grupos](https://github.com/nelsonboulangerie/django-shopman/blob/8830a72bf/surfaces/operator-router/groups.json)

**Solução preferida.** Ensaiar os mesmos digests em ambiente representativo e descartável antes da promoção, com configuração equivalente e integrações de teste. Incluir atualização do schema a partir da versão anterior. Preservar a validação de identidade e o smoke pós-promoção.

**Aceite.** Uma falha funcional ou de migração impede a promoção. O ensaio deixa evidência de versão, cenário, resultado e estado final dos ledgers.

## Acertos a preservar

- **Autoridade explícita.** Stockman decide a promessa e a reserva, Offerman responde pelo preço de lista, Orderman controla o ciclo do pedido e Payman registra o dinheiro. Os PRs [#2263](https://github.com/nelsonboulangerie/django-shopman/pull/2263) e [#2277](https://github.com/nelsonboulangerie/django-shopman/pull/2277) reduziram a divergência entre promessa da vitrine e reserva.
- **Modelo aderente ao chão de loja.** Comanda, pedido, pagamento e turno são distintos. A fornada preserva consumo, saída, qualidade e perda. Um SKU comprável e vendável compartilha unidade coerente e estoque.
- **Regressões arquiteturais detectáveis.** Guardas de dependência, dinheiro, ledger e projeções, além de registro e locks alinhados nas superfícies. A guarda de autoridade cobre as decisões cadastradas.
- **Release rastreável.** Construção única, promoção por digest e identidade verificável por componente. A [leitura do custo congelado pelo B.I.](https://github.com/nelsonboulangerie/django-shopman/pull/2272) já distingue ausência e incompletude do custo.

## Acertos e cenários a verificar por app

| Superfície | Acerto | Fragilidade e encaminhamento |
|---|---|---|
| PDV | Comanda, venda mista, custódia e fila idempotente. | Com a opção de venda offline desativada na configuração da loja, perder rede bloqueia a cobrança. Ensaiar recuperação de cobrança e conciliação fiscal. |
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
