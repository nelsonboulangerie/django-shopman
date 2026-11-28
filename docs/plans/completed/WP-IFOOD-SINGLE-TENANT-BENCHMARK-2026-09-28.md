# WP — benchmark iFood single-tenant para planejamento do Storefront

> **Status:** BENCHMARK CONSOLIDADO — evidência até pós-entrega; implementação não autorizada
>
> **Data de corte:** 2026-09-28
>
> **Artefato canônico:**
> `docs/reports/IFOOD-SINGLE-TENANT-END-TO-END-BENCHMARK-2026-09-28.md`
>
> **Natureza:** Work Package documental de evidência e handoff
>
> **Escopo desta entrega:** pesquisa, síntese, limitações e prompt de planejamento
>
> **Fora desta entrega:** prioridade de produto, roadmap, código, teste de produto e deploy

## 1. Objetivo

Registrar um benchmark atual do iFood, especializado para uma boulangerie single-tenant, e
entregar evidência suficiente para uma futura sessão decidir o que — se algo — deve mudar no
Shopman.

O WP não transforma padrões do iFood em requisitos. Ele separa:

- observação direta do iFood Web;
- fontes oficiais e normativas;
- auditoria estática do Shopman;
- inferências para single-tenant;
- gaps comprovados;
- hipóteses que exigem medição, produto ou operação.

## 2. Resultado documental

O relatório canônico cobre:

- login e estabelecimento de sessão;
- descoberta, home, categorias e busca;
- página da loja, cardápio e produto;
- carrinho, mínimo, taxas e revisão;
- checkout, endereço, mapa, entrega, retirada e agenda;
- cupons, promoções e fidelidade;
- Pix, Crédito, Débito, VR, VA, dinheiro e maquininha;
- CPF/CNPJ e nota;
- confirmação, acompanhamento, suporte, reembolso e recompra;
- UX/UI, copy, feedback, performance percebida, acessibilidade e privacidade;
- omotenashi, erro, retorno e preservação de estado;
- jornada real Rap1000/Kibixinha e custos, sem replicar dados sensíveis desnecessários;
- filtro completo de mecanismos exclusivos de marketplace;
- comparação com o Shopman, preservando soluções maduras.

## 3. Método

### 3.1 Observação direta

- iFood Web, Chrome desktop, 28/09/2026.
- Sessão inicialmente deslogada, depois autenticada pelo próprio usuário.
- Endereço autorizado usado apenas para contextualizar cobertura e checkout.
- Loja Rap1000 Kibixinha aberta com ajuda do usuário quando a busca interna falhou.
- Primeira rodada levada até o CTA `Fazer pedido`, sem acioná-lo; uma rodada posterior,
  conduzida pelo usuário, concluiu um pedido Pix e permitiu observar tracking e entrega.
- Meios de pagamento explorados sem salvar cartão/benefício e sem registrar dado financeiro
  real neste documento.
- Valores sintéticos inválidos foram usados somente para observar validação; não foram
  submetidos. O pedido posterior usou os dados do próprio usuário, todos omitidos daqui.
- O relatório registra somente estados e transições; QR, código Pix, identificador do pedido,
  endereço, sessão e dados pessoais não foram versionados.

### 3.2 Pesquisa complementar

Foram usadas fontes do iFood, iFood Tech/Developer, App Store, Google Play, Apple HIG,
W3C/WCAG, Android e web.dev. Fontes secundárias entram somente como sinais de risco, com
essa qualificação explícita.

### 3.3 Auditoria Shopman

Leitura estática de rotas, componentes, contratos, projeções e testes. A auditoria original
foi feita em `7cc56f77d` e sintetizada em `664a57b93`; contratos e referências foram
revalidados em `origin/main` `e3880d89d` na consolidação R4.

### 3.4 Taxonomia

- `[OD]`: observação direta;
- `[MD]`: medição direta;
- `[FI]`: fonte primária;
- `[AS]`: auditoria Shopman;
- `[INF]`: inferência;
- `[HIP]`: hipótese ainda não comprovada.

## 4. Evidências centrais registradas

### Jornada e endereço

- Endereço antecede catálogo no iFood observado.
- Places converge para confirmação no mapa antes de número/complemento.
- Número encontrado é reaproveitado.
- Mapa falhou ao carregar tiles sem oferecer retry/fallback explícito.
- A evidência reforça o WP existente de confirmação visual, sem substituí-lo.

### Descoberta e produto

- Home usa endereço, busca, categorias, filtros e contexto.
- Busca/listagem falharam regionalmente sem uma ação de recuperação.
- Rap1000 exibiu prazo, taxa, mínimo, horário e meios aceitos antes da compra.
- Kibixinha tinha quantidade/comentário, mas não peso, alergênicos, estoque ou composição
  rica; o Shopman já possui essas informações.
- Shopman não possui variantes/modificadores selecionáveis no contrato atual.

### Carrinho, cupom e checkout

- Pedido mínimo foi explicado corretamente, excluindo frete.
- Carrinho e checkout mantiveram resumo financeiro editável.
- Cupom mostrou regras e desconto discriminado, mas o valor não mudou após alteração do
  subtotal; causa não determinada.
- iFood apresentou flashes transitórios incorretos em badge/contador/metadata.

### Pagamentos

- Na primeira rodada, Pix só criaria cobrança depois do CTA final, ainda não acionado.
- Na rodada posterior, o pedido Pix foi criado. Copiar o código pareceu adiantar a interface
  antes da confirmação financeira; isso é observação de UI a validar tecnicamente, não
  afirmação sobre o estado interno do iFood.
- O handoff móvel de pagamento exibiu “conexão não é privada”, risco concreto de confiança e
  continuidade; host, parâmetros e qualquer identificador foram omitidos.
- Widget externo ofereceu Crédito, Débito, Vale-refeição e Vale-alimentação.
- VR listou Ticket, VR Refeição, Alelo Refeição e Pluxee Refeição/Sodexo.
- Crédito/Débito/VR/VA reutilizaram formulário com cartão, apelido e CPF/CNPJ.
- Widget avisou pequena cobrança com devolução automática, sem valor/prazo/descritor.
- Não foi observado parcelamento; isso não prova ausência após cartão válido.
- Voltar preservou carrinho, endereço, cupom, taxas e total, mas perdeu a seleção de Pix sem
  aviso.
- Pagamento na entrega incluiu dinheiro, débito e crédito; troco foi resolvido antes do
  envio.
- CPF/CNPJ na nota mostrou erro com CTA ainda habilitado e switch técnico sem copy útil.

### Estado final seguro

- Kibixinha: R$ 18,00.
- Bolinho de Carne: R$ 18,00.
- Subtotal: R$ 36,00.
- Serviço: R$ 0,99.
- Entrega: R$ 14,00.
- Desconto: -R$ 6,75.
- Total: R$ 41,99.
- Esse foi o estado final da primeira rodada. Na rodada posterior, o pedido foi enviado,
  acompanhado até a entrega e observado novamente após refresh, sem registrar identificador,
  código de pagamento ou endereço.

## 5. Limitações

1. A observação foi majoritariamente no Web desktop. O celular participou do handoff de
   pagamento, mas o app nativo não foi auditado de ponta a ponta.
2. Conta, região, horário e experimentos podem alterar a UI.
3. Houve uma única observação transacional de pós-pedido; ela não mede prevalência nem
   explica a arquitetura interna.
4. Nenhum cartão válido foi cadastrado; não há conclusão sobre autorização, 3DS,
   parcelamento, recusa ou recuperação depois da submissão.
5. Não houve medição confiável de Core Web Vitals do iFood.
6. A auditoria Shopman foi estática; comportamento real precisa de execução própria.
7. Observação de uma sessão não mede prevalência nem impacto de conversão.
8. Fontes secundárias não sustentam requisitos.

## 6. Regras para usar o benchmark

1. Não copiar identidade visual, ilustração, voz, tokens ou composição do iFood.
2. Não importar mecanismo que exista apenas por multitenância.
3. Não degradar fonte canônica do Shopman para imitar uma interação.
4. Não inferir preço, estoque, promoção, zona, pagamento ou status no cliente.
5. Não promover hipótese a gap sem evidência local.
6. Não criar prioridade a partir de preferência estética.
7. Não duplicar o WP de mapa; usar o documento existente como autoridade dessa frente.
8. Não iniciar implementação sem owner, escopo, contrato, recuperação e métrica definidos.

## 7. Soluções maduras a preservar

- contrato `Action` server-driven;
- catálogo vivo separado do Continuum estrutural;
- carrinho otimista com fila/reconciliação/rollback;
- endereço estruturado único e cálculo de entrega no Core;
- checkout com revisão, idempotência e recibo em resultado desconhecido;
- pagamento e tracking na mesma projeção;
- SSE com fallback de polling;
- estados offline honestos;
- suporte, cancelamento e reorder condicionados a ações válidas;
- foco, teclado, live regions, reduced motion e safe areas existentes.

## 8. Inventário neutro para futura decisão

O relatório registra, sem ordem de prioridade:

- confirmação visual comum a GPS/Places;
- variantes/modificadores/complementos como eventual decisão de domínio;
- momento de autenticação;
- descoberta/aplicação de benefício;
- telemetry de busca/funil/Web Vitals;
- recentes, populares e personalização;
- comunicação ao voltar de widget financeiro;
- clareza de pré-autorização;
- meios contratados online/na entrega;
- política e validação de dados fiscais;
- capacidade real para ETA/mapa de entregador;
- reconciliação da especificação de rotas.

Itens dessa lista podem terminar como “não fazer”. Este WP não os ranqueia.

## 9. Entradas obrigatórias da futura sessão de planejamento

1. Este WP e o relatório canônico.
2. O WP base de confirmação visual e sua extensão de divergência:
   `docs/plans/WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md` e
   `docs/plans/WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md`.
3. `origin/main` atualizado e estado dos PRs/worktrees ativos.
4. Contratos atuais de carrinho, checkout, endereço, pagamento e tracking.
5. Dados disponíveis de RUM, funil, busca, suporte e operação.
6. Lista real de meios de pagamento e modalidades oferecidas pela Nelson.
7. Owners de produto, operação, checkout, pagamento, privacidade e acessibilidade.

## 10. Saída esperada da futura sessão

Uma proposta de planejamento — ainda sem implementação — que:

- confirme ou descarte cada hipótese com evidência;
- agrupe mudanças por problema/contrato, não por tela copiada;
- identifique dependências e trabalho em voo;
- preserve explicitamente as invariantes maduras;
- defina métricas de baseline e sucesso;
- separe UI, domínio, operação, legal/privacidade e observabilidade;
- evite planos concorrentes com o WP de mapa;
- apresente opções/trade-offs para decisões do owner;
- só atribua prioridade após impacto, risco, dependência e capacidade operacional serem
  discutidos.

## 11. Prompt para uma futura sessão de planejamento

```text
Planeje a evolução end-to-end do Shopman Storefront a partir de:

1. docs/reports/IFOOD-SINGLE-TENANT-END-TO-END-BENCHMARK-2026-09-28.md
2. docs/plans/WP-IFOOD-SINGLE-TENANT-BENCHMARK-2026-09-28.md
3. docs/plans/WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md
4. docs/plans/WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md
5. origin/main atualizado, contratos e trabalho em voo

Antes de propor qualquer mudança, valide no código e no Live o estado atual, leia os
contratos canônicos de carrinho, endereço, checkout, pagamento e tracking e levante os dados
de funil/RUM/operação disponíveis. Distinga observação, fonte, inferência, gap comprovado e
hipótese. Filtre completamente multitenância e não copie identidade, layout ou copy do
iFood.

Produza somente planejamento. Não implemente, não abra PR e não faça deploy. Preserve Action,
projeções server-driven, Continuum estrutural, reconciliação do carrinho, endereço estruturado,
cálculo de entrega no Core, checkout idempotente e pagamento/tracking canônicos. Para mapa,
complemente o WP existente; não crie plano concorrente.

Para cada problema confirmado, apresente: evidência, usuário afetado, contrato/fonte de
verdade, opções, trade-offs, dependências, estados de erro/retorno, privacidade, a11y,
performance, teste, métrica e rollback. Hipóteses sem evidência devem resultar em medição ou
pesquisa, não em feature. Inclua também a opção “não fazer”.

Somente depois de discutir impacto, risco, dependências e capacidade operacional com os
owners, proponha uma sequência. Registre decisões pendentes em vez de inventá-las.
```

## 12. Critérios de conclusão deste WP documental

- [x] Jornada login → pedido → tracking → pós-entrega documentada.
- [x] Métodos online/na entrega explorados com valores sintéticos; pedido real posterior
  sanitizado antes do registro.
- [x] Rap1000/Kibixinha e custos da primeira rodada registrados; pedido posterior descrito
  sem dados pessoais, financeiros ou identificadores.
- [x] Fontes e inferências separadas.
- [x] Multitenância filtrada.
- [x] Shopman comparado com soluções maduras preservadas.
- [x] Gaps comprovados separados de hipóteses.
- [x] Mapa encaminhado ao WP existente.
- [x] Nenhuma prioridade ou implementação definida.
- [x] Prompt de planejamento futuro incluído.
