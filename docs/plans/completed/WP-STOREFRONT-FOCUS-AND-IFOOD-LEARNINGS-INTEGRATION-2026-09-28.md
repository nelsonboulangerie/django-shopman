# WP-STOREFRONT-FOCUS-AND-IFOOD-LEARNINGS-INTEGRATION — Foco Inteligente e aprendizado iFood

- **Data:** 2026-09-28
- **Estado:** pronto para execução autônoma
- **Prioridade:** P1 de UX; pode avançar em paralelo às frentes operacionais

## 1. Objetivo

Resgatar os dois commits locais do Foco Inteligente do Storefront e integrar, sem contradição ou perda de evidência, os três documentos de benchmark e planejamento produzidos na observação do iFood:

- branch `codex/storefront-focus-ruler-20260928`, commits `d055d522d` e `c28c98bd3`, oito arquivos, 163 adições e 22 remoções, 20 commits atrás do `main` na auditoria;
- `WP-IFOOD-SINGLE-TENANT-BENCHMARK-2026-09-28.md` e o relatório canônico correspondente;
- `WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md`;
- `WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md`.

O WP entrega código de foco recuperado e documentação consolidada. Ele não implementa mapa nem divergência geográfica.

## 2. Princípios

- Observação direta, relato do usuário, auditoria do Shopman e inferência precisam continuar rotulados separadamente.
- Não copiar identidade visual ou texto proprietário do iFood; extrair padrões de interação e escrever copy própria.
- Mobile não pode ser declarado “coberto” quando a observação ocorreu majoritariamente no browser desktop e o pagamento foi concluído no celular sem instrumentação completa.
- O foco deve servir à tarefa atual sem sequestrar teclado, leitor de tela ou rolagem escolhida pelo usuário.
- Mapa e localização são opt-in, minimizam coordenadas e nunca bloqueiam checkout por falso positivo.

## 3. Dependências e paralelismo

- Pode ser executado em paralelo aos WPs de Encomendas e Marketing, pois o ownership é Storefront + quatro documentos dedicados.
- O merge deve usar o `main` estabilizado e resolver mudanças posteriores em `tailwind.css`, `entrar.vue`, `finalizar.vue` e `useNextFocus.ts`.
- A parte documental não depende da parte de código e pode virar PR separado; ambas pertencem ao mesmo WP e ao mesmo owner.
- Nenhuma implementação de mapa começa antes de aprovação explícita de um dos WPs de endereço já consolidados.

## 4. Ownership exclusivo

O executor detém:

- `surfaces/storefront-nuxt/app/assets/css/tailwind.css`;
- `surfaces/storefront-nuxt/app/components/LegalDocument.vue`;
- `surfaces/storefront-nuxt/app/composables/useNextFocus.ts`;
- `surfaces/storefront-nuxt/app/pages/entrar.vue`;
- `surfaces/storefront-nuxt/app/pages/finalizar.vue`;
- os testes de foco correspondentes;
- os quatro documentos canônicos citados no objetivo.

Outros arquivos do Storefront só podem ser tocados após registrar a necessidade no PR. Nenhum executor de mapa/endereço edita estes arquivos enquanto o lease estiver ativo.

## 5. Escopo

### Código

- Reaplicar semanticamente a régua única de foco do Storefront.
- Preservar a opção `initialReveal: 'always'` para fluxos guiados, especialmente a entrada no checkout.
- Resolver a disputa entre reset global de scroll, ciclo SPA, `nextTick`, `requestAnimationFrame` e `page:finish`.
- Preservar `prefers-reduced-motion`, cancelamento do pedido anterior e cleanup do hook.
- Cobrir navegação Sacola → Checkout, reload direto e mudança de etapa.

### Documentação

- Consolidar a jornada completa observada: login, descoberta, produto, carrinho, checkout, entrega/retirada, troca de endereço, cartões, Pix, pagamento na entrega, dinheiro/troco, CPF/CNPJ, confirmação, tracking e pós-entrega.
- Incorporar a observação posterior ao relatório inicial, removendo a contradição de que nenhum pedido foi submetido.
- Registrar o avanço otimista após copiar o Pix como observação a validar tecnicamente, não como verdade interna do iFood.
- Registrar que a página de tracking ficou atrasada em relação à entrega e só refletiu mudança após refresh manual.
- Registrar URLs e transições relevantes sem incluir tokens, códigos Pix, identificadores de pedido, endereço residencial ou outros dados pessoais.
- Registrar o erro móvel “conexão não é privada” no handoff de pagamento como risco de confiança e continuidade.
- Separar a hipótese de chamada antecipada de entregador do que foi diretamente observado.
- Integrar e deduplicar as decisões de mapa de confirmação e divergência endereço × localização.
- Atualizar SHAs e baseline técnico dos documentos.

## 6. Não escopo

- Implementar mapa, geocodificação, cálculo de distância ou feature flag de localização.
- Alterar checkout, pagamento, tracking ou login além do comportamento de foco dos commits resgatados.
- Pesquisa adicional autenticada no iFood ou novo pedido.
- Replicar copy, layout, marca ou assets do iFood.
- Declarar cobertura completa do app nativo.

## 7. Etapas de execução

### Fase 0 — preservar as fontes

1. Congelar a worktree de Foco Inteligente e as duas worktrees documentais.
2. Registrar seus SHAs, diffs e estado.
3. Criar branch limpa do `origin/main` atual.
4. Não rebasear destrutivamente nem arquivar as fontes antes do merge.

### Fase 1 — resgate do foco

1. Reaplicar `d055d522d` e `c28c98bd3` em commits separados ou portar os hunks de forma equivalente.
2. Resolver conflitos comparando comportamento atual, não apenas texto.
3. Revisar a régua visual única em relação ao chrome fixo e ao fio Brass.
4. Garantir que `page:finish` seja consumido uma vez e removido no unmount.
5. Garantir que pedidos rápidos de foco usem “o mais novo vence”.
6. Não adicionar listeners, loops de frames ou timers persistentes.

### Fase 2 — consolidação do benchmark

1. Importar o WP e relatório de benchmark para o baseline atual.
2. Atualizar a taxonomia de evidência.
3. Acrescentar a observação real de pedido e pós-pedido.
4. Sanitizar PII e segredos.
5. Criar uma matriz por etapa: padrão iFood observado, estado Shopman, oportunidade, risco e prioridade.
6. Marcar explicitamente lacunas de mobile e itens que continuam hipótese.

### Fase 3 — mapa e divergência

1. Integrar os dois WPs sem repetir princípios, contratos ou eventos.
2. Fazer o WP de confirmação visual ser a base e o WP de divergência uma extensão dependente.
3. Consolidar estados, feature flags, privacidade, acessibilidade, fallback e rollback.
4. Resolver baselines antigos e cross-links.
5. Manter duas decisões separadas:
   - confirmar visualmente um ponto escolhido;
   - alertar, com baixa fricção, quando localização atual e destino divergem.

### Fase 4 — revisão e entrega

1. Fazer revisão de acessibilidade e mobile do código.
2. Fazer revisão de evidência e privacidade dos documentos.
3. Abrir dois PRs independentes, se isso acelerar revisão:
   - PR C1: código do Foco Inteligente;
   - PR C2: documentação consolidada.
4. Nenhum dos PRs depende do outro para merge, mas ambos referenciam este WP.

## 8. Gates e testes

### Foco Inteligente

- testes de `useNextFocus`;
- guardrails da régua de foco;
- testes de foco do checkout;
- suíte completa de `storefront-nuxt`;
- lint, typecheck e build;
- E2E ou prova manual de navegação SPA e reload.

Cenários obrigatórios:

- Sacola → Checkout com usuário identificado posiciona “Como receber” na régua;
- reload direto produz o mesmo destino;
- mudança de etapa cancela reveal antigo;
- `prefers-reduced-motion` evita animação;
- back/forward e scroll manual não entram em disputa infinita;
- teclado móvel aberto não esconde o campo/CTA;
- Tab, leitor de tela e foco nativo continuam coerentes;
- `LegalDocument` e entrada não sofrem regressão de espaçamento.

### Documentação

- nenhum dado pessoal, token, código de pagamento ou identificador de pedido;
- nenhuma hipótese rotulada como observação;
- nenhuma contradição entre “pedido não submetido” e a sessão posterior;
- cross-links válidos;
- uma única recomendação para cada decisão de mapa/divergência;
- baselines e status atualizados.

O CI completo deve estar verde no HEAD dos PRs de código. PR documental deve passar os gates de docs do repositório.

## 9. PR, merge e deploy

- PR C1 contém before/after em viewport móvel e desktop e explica SPA versus reload.
- PR C2 lista fontes, limitações e itens ainda não verificados.
- Ambos devem ser atualizados com o `main` antes da merge queue.
- O código vai primeiro a staging e recebe smoke nos fluxos Entrar e Finalizar.
- Documentação não exige deploy.
- Este WP não ativa mapa nem coleta geolocalização.

## 10. Rollback

- Reverter PR C1 restaura o comportamento anterior sem migration ou perda de dados.
- Se o problema for apenas `initialReveal: 'always'`, desativar o uso no checkout em hotfix pequeno, preservando o composable compatível.
- Documento incorreto é corrigido por follow-up rastreável; não apagar histórico de evidência.
- Worktrees fonte ficam disponíveis até merge e smoke.

## 11. Definition of Done

- Os dois commits de foco foram reconciliados com o `main`, não apenas cherry-picked cegamente.
- Testes, lint, typecheck, build e prova SPA/reload estão verdes.
- O benchmark canônico cobre a jornada observada até o pós-entrega e declara suas limitações mobile.
- Os WPs de mapa e divergência estão deduplicados, ordenados e atualizados.
- Não há PII nem segredo nos documentos.
- Nenhum código de mapa foi implementado sem aprovação.
- PRs, CI e smoke de staging estão registrados.
- Worktrees antigas estão prontas para arquivamento recuperável.
