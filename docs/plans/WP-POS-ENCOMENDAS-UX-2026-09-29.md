# WP — Encomendas do PDV: clareza operacional e omotenashi

**Data:** 2026-09-29  
**Owner:** frente isolada `codex/pos-orders-ux-20260929`  
**Prioridade:** P1, usabilidade operacional antes do Go-live  
**Estado:** em execução, sem mudança de dados operacionais

## Por que este WP existe

A integração funcional de Encomendas chegou ao `main` no PR #1231, compondo as doadoras #1221 e #1222. O contrato e as capacidades estão cobertos, mas a tela resultante trata busca, período, resumo, filtros, impressão e sete dias como blocos de peso visual semelhante. Isso aumenta varredura, quebra o ritmo do balcão e faz a seção parecer uma ferramenta separada do restante do PDV.

O objetivo é tornar a tela legível em poucos segundos, com a próxima tarefa operacional evidente, sem reabrir decisões funcionais já integradas.

## Fonte de verdade e código superseded

- **Fonte funcional única:** merge `a05f82af9bb577d0b331aa224018d87b8ed70312` do PR #1231.
- **Somente contexto histórico:** PRs #1221 e #1222. Ambos são snapshots WIP declarados como “não mergear”; nenhuma linha será recuperada diretamente deles.
- **Preservar:** tela única, detalhe compartilhado, estado na URL, busca global, Dia/Semana, filtros combináveis, impressão do lote visível, redirects legados, ações server-driven e retorno ao mesmo recorte.
- **Não reabrir:** contrato Django, projeções, pagamentos, impressão física, fiscal, KDS, edição/cancelamento/reagendamento e semântica de status.

## Diagnóstico comprovado

1. O cabeçalho do conteúdo exibe busca, switch, navegador de período, seletor de data, resumo financeiro, nota de escopo, três grupos de filtros e impressão antes da primeira encomenda.
2. O modo Semana mantém duas árvores completas de conteúdo, grade e lista, alternadas por container query. Isso duplica a hierarquia visual e os pontos de manutenção.
3. A grade larga força sete colunas iguais. Cards compactos perdem canal, resumo de itens e situação, justamente os sinais usados pelo balcão para decidir o próximo gesto.
4. Busca e navegação do período têm peso visual semelhante, embora “cliente veio buscar” seja a tarefa urgente e orientada a pessoa.
5. Estados de carregamento e erro são texto solto ou avisos, sem reservar a geometria do conteúdo. A mudança de altura torna a leitura menos estável.
6. A UI já possui bons fundamentos: foco inicial, leitura de código, URL como estado, mensagens por extenso, alvos de toque, foco visível, chips com contagem e ações server-driven. O redesign deve preservá-los.

## Hipóteses a validar visualmente

- Um painel de busca com título curto, ícone e ajuda progressiva reduz a carga sem esconder a busca.
- Um único quadro semanal responsivo, com largura mínima útil por dia, é mais compreensível que sete colunas comprimidas mais uma lista duplicada.
- Resumo e ação de impressão no mesmo bloco do período tornam o resultado dos filtros previsível.
- Dar destaque apenas a saldo a receber, pagamentos a conferir, falta de impressão e hoje melhora a tomada de decisão sem transformar todo card em alerta.

## Princípios de design

- **Pessoa primeiro:** “Cliente veio buscar?” permanece o primeiro foco e a primeira região do conteúdo.
- **Uma região, uma pergunta:** localizar cliente; escolher recorte; refinar; agir; abrir pedido.
- **Exceção chama atenção:** perigo, dúvida de pagamento e saldo recebem cor; o restante permanece neutro.
- **Sem beco sem saída:** empty/error/offline sempre dizem o que ocorreu e oferecem a próxima ação segura.
- **Toque e teclado equivalentes:** 44 px mínimos, foco visível, Enter no resultado único, atalhos documentados e nenhuma ação apenas em hover.
- **Continuidade:** o card mostra os sinais que ligam balcão, retirada/entrega, impressão e produção; o detalhe segue compartilhado com o Gestor.

## Escopo

### Onda 1 — hierarquia e densidade

- organizar busca, período/resumo, filtros/impressão e lista em regiões semânticas;
- consolidar o quadro semanal em uma única árvore responsiva;
- melhorar card de dia e de encomenda sem alterar o contrato;
- adicionar skeletons estáveis e retry local nos estados sem leitura;
- manter navegação e query string idênticas;
- validar 320×568, 390×844, 768×1024, 1024×768 e 1440×900.

### Onda 2 — continuidade operacional, somente se a Onda 1 provar lacuna

- sinalizar prioridade temporal com dados já existentes;
- expor ligação com KDS/produção/retirada/entrega apenas quando o contrato já fornecer a capacidade;
- documentar atalhos de teclado existentes no próprio contexto.

## Fora de escopo

- qualquer migration ou alteração de dados;
- novas regras de negócio ou inferência client-side de status;
- mudanças em pagamentos, fiscal, estoque, catálogo ou integrações externas;
- reativar páginas `panel.vue`, `today.vue`, `week.vue` ou `PosPreorderPaymentFilter.vue` removidas no #1231;
- alterar `orders-nuxt` ou o detalhe compartilhado na Onda 1;
- ativar flags, credenciais, 2FA ou fazer ação operacional em Live.

## Ownership exclusivo de arquivos

Na Onda 1, esta frente é a única escritora de:

- `surfaces/pos-nuxt/app/pages/preorders/index.vue`;
- `surfaces/pos-nuxt/app/components/PosPreorderFilters.vue`;
- `surfaces/pos-nuxt/app/components/PosPreorderRow.vue`;
- componentes novos `PosPreorders*` estritamente apresentacionais;
- testes de Encomendas em `surfaces/pos-nuxt/tests/`;
- harness/baselines visuais novos do PDV;
- este WP.

Não haverá escrita em projeções Django, contrato gerado, catálogo, dados de produção ou arquivos do detalhe compartilhado sem um WP/PR separado.

## Etapas de execução

1. Capturar o baseline do `origin/main` em desktop, tablet e mobile com fixture hermética.
2. Registrar medidas: quantidade de regiões antes da primeira encomenda, largura mínima de card, overflow, foco e número de árvores responsivas.
3. Refatorar somente apresentação, reutilizando `Ui*`, `OperatorAppBar`, tokens e `PosPreorderRow`.
4. Ajustar testes funcionais sem reduzir as asserções herdadas do #1231.
5. Criar matriz visual determinística para normal, empty, loading, error e busca.
6. Rodar lint, typecheck, testes focados, suíte completa do POS e build.
7. Abrir PR pequeno da Onda 1, anexar, entrar na fila e acompanhar deploy.
8. Após deploy, executar smoke Live somente leitura e registrar no ledger canônico.

## Gates

- **G0 — não regressão:** nenhuma capacidade ou teste do #1231 removido.
- **G1 — visual:** sem overflow/corte nos cinco viewports; contraste e foco perceptíveis; zoom 200% utilizável.
- **G2 — operacional:** busca continua focada, Enter abre resultado único, filtros e volta do detalhe preservam URL, impressão corresponde apenas ao visível.
- **G3 — acessibilidade:** regiões nomeadas, ordem de tab coerente, controles com nome acessível, avisos anunciáveis e touch targets de 44 px.
- **G4 — desempenho:** uma árvore semanal; nenhuma nova leitura de API; sem dependência ou bundle pesado.
- **G5 — Live:** deploy verde, PDV alcançável e fronteira de autenticação fechada; fluxo autenticado requer operador humano e fica como gate explícito se credencial não for autorizada.

## Testes obrigatórios

- Vitest: `pages/preorders.test.ts`, `preordersPresentation.test.ts`, componentes alterados e guardrails do app bar/rail.
- Playwright visual: normal, dia, semana, busca, empty, erro e loading em mobile/tablet/desktop.
- `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` em `surfaces/pos-nuxt`.
- Testes de teclado: foco inicial, digitação com foco fora, Enter em resultado único, ordem de tab e retorno do detalhe.
- Testes de contrato visual: uma única árvore semanal no DOM e ausência dos caminhos superseded.

## Deploy, ativação e rollback

- Entrega por PR da Onda 1, sem migration/env/config/flag.
- O deploy padrão publica a imagem do PDV após merge no `main`; o smoke automatizado deve concluir verde.
- Smoke Live seguro: host do PDV 200, assets carregam, rota sem autenticação falha fechada e não dispara escrita.
- Smoke funcional autenticado exige operador autorizado e não será improvisado com credenciais.
- Rollback: reverter o merge da Onda 1 e republicar a imagem anterior do PDV. Como contrato e backend não mudam, o rollback é somente de apresentação.

## Definition of Done

- baseline antes/depois versionado e revisável;
- nenhuma linha recuperada diretamente dos snapshots #1221/#1222;
- uma única árvore semanal responsiva;
- funcionalidades e URLs do #1231 preservadas;
- matriz de estados e viewports verde;
- PR mergeado, deploy concluído, smoke Live registrado e rollback explícito no ledger;
- eventuais lacunas de continuidade com KDS/produção viram WP separado, não código especulativo.
