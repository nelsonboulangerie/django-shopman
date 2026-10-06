# Infraestrutura de UX das superfícies de operador

O catálogo executável e as decisões de convergência ficam em
[`operator-kitchen-sink.md`](operator-kitchen-sink.md). Este documento descreve
os mecanismos; o Kitchen Sink define como compô-los em anatomias e receitas.

Esta é a referência de consumo do `WP-UX-13B`. Ela vale para os oito apps Nuxt de
operador. Storefront e Admin/Unfold ficam fora. A auditoria específica de cada app só
começa depois do merge desta infraestrutura; o PDV continua suspenso até esse ponto.

## Inventário de partida e consolidação

| entrega | estado encontrado | fonte consolidada | decisão |
|---|---|---|---|
| runner da matriz | duplicada e inadequada: Marketing e PDV tinham configs locais diferentes | `surfaces/operator-kit/visual` + `scripts/run_operator_visual.py` | compor configs futuras pelo runner único; harnesses legados continuam fixtures, não fonte |
| scanner geométrico | parcial: checks pontuais de largura e alvo em specs locais | `visual/scanner.ts` | adotar scanner transversal com achados tipados e exceção explícita |
| inventário de rotas/subtelas | parcial: 60 entradas manuais, sem conferir a rota derivada do arquivo | `operator-component-ledger.json` + `check_operator_component_ledger.py` | preservar o ledger e acrescentar inventário Nuxt automático |
| ledger canônico | parcial: rotas, variantes e status, todos `pending` | o mesmo ledger, versão 2 | estender, não criar outro: matriz, estados, responsáveis, evidências e gate de fechamento |
| gate de visita/captura/pending | ausente | `check_operator_component_ledger.py --require-complete` | o CI estrutural aceita dívida nomeada; o fechamento reprova qualquer `pending` |
| mapa de atalhos | duplicado: listeners e helpers por componente/app | `app/types/operatorShortcut.ts`, `app/utils/operatorShortcuts.ts`, `app/shortcuts/suiteShortcuts.ts` | novos comandos só entram pelo mapa tipado; dívida existente fica inventariada e congelada |
| tokens estruturais | parcial: cores e tipografia centrais, geometria espalhada | `operator-theme.css` | rail, cabeçalho, barra de ação, pane, espaçamento, safe area e camadas têm um token único |
| Splitter | ausente no kit; havia resize específico de colunas | `OperatorSplitter.vue` sobre `USplitter` (`NuxtSplitter` com o prefixo da suíte) | adotar o oficial e acrescentar somente validação de persistência, SSR, rótulo e reset |
| catálogo vivo | inadequado: `__visual_board` era fixture privada do Marketing | `operator-kit/catalog/OperatorKitCatalogPage.vue` | catálogo compartilhado, habilitado somente por `OPERATOR_KIT_CATALOG=1` |
| guardrail de duplicação | parcial: teto de `components/Ui` e imports diretos | três scripts `check_operator_*` | bloquear nova árvore, layout, token, listener e anatomia oficial local |
| documentação | parcial e espalhada | este documento, README do kit e README do runner | uma sequência de consumo para as próximas sessões |

## Ordem canônica de estrutura

A decisão parte sempre da anatomia oficial disponível no Nuxt UI 4.11.3:

| estrutura atual/necessidade | equivalente oficial | funções que precisam sobreviver | decisão 13B | teste/gate |
|---|---|---|---|---|
| raiz do app | `UApp` | locale, overlays, tooltip e toaster únicos | `OperatorAppRoot` compõe `NuxtApp` com o prefixo da suíte | catálogo + teste estrutural |
| escritório/gestão | `UDashboardGroup`, `UDashboardSidebar`, `UDashboardPanel`, `UDashboardNavbar`, `UDashboardToolbar` | navegação, mobile, persistência, cabeçalho e toolbar | `OperatorOfficeShell` adota a família Dashboard | catálogo e `UiNuxtStructuralPrimitives` |
| rail operacional existente | Dashboard/Sidebar + `UNavigationMenu` | identidade, alertas, lock, kiosk, atalhos e barra de polegar | manter sem crescer até o WP do app comparar a jornada; não é exceção aprovada | inventário de shells + testes atuais do rail |
| página administrativa | `UPage`, `UPageHeader`, `UPageBody`, `UPageAside` | título, descrição, ações, conteúdo e aside | `OperatorPage` adota a família UPage | catálogo e guardrail de tag direta |
| fluxo operacional | `UMain` e composição por slots | rail/header/conteúdo/barra de ação, sem impor regra de app | `OperatorOperationalShell` compõe a estrutura oficial | catálogo |
| largura e respiro | `UContainer` + tokens | margem fluida, conteúdo extremo e zoom | `OperatorPage` + tokens `--op-page-*` | scanner e teste de tokens |
| navegação | `UNavigationMenu`, `USidebar` | desktop/mobile, nomes, foco e retorno | adotados no shell e no catálogo; cada app migra no próprio WP | guardrail de implementação local |
| pane ajustável | `USplitter` | ponteiro, teclado, limites, persistência e SSR | `OperatorSplitter` estende minimamente | testes de storage, teclado/ponteiro oficiais e catálogo |
| busca da suíte | `UDashboardSearch`/`UCommandPalette` | busca remota, escopos, câmera, filtro local e links cross-app | composição futura; o contrato atual não é refeito no 13B | listener já migrou para o mapa; app prova anatomia no próprio WP |
| formulário, tabela, cards, tabs e overlays | famílias oficiais correspondentes | domínio, copy, estados, foco e camadas | usar oficial ou wrapper fino do kit | catálogo vivo + testes de wrappers |

Identidade Shopman entra por tokens, tipografia Instrument Sans, ícones, densidade,
radius, copy e variantes. Um app não copia markup oficial para “personalizar”. Ele passa
props, slots e tokens. HTML ou Reka direto exige motivo operacional, responsável e teste
no ledger.

## Runner e ledger

O ledger é a fonte única de apps, rotas, cenários (`variants`), matriz, estados,
responsáveis e status. Uma tela `pending` ainda não declara cobertura. Ao virar `audited`,
`migrated` ou `retained-with-reason`, passa a exigir:

- estados e viewports aplicáveis;
- evidência por rota e cenário, com `visited: true`;
- captura organizada pelo reporter;
- exceção com `kind`, `reason`, `owner` e `test`;
- configuração incremental do runner naquele item.

Comandos:

```bash
make test-operator-ux
make operator-visual app=operator-kit scenario=canonical-layouts viewports=desktop-common,mobile-standard
make operator-visual app=marketing route=/campaigns scenario=empty plan=1
make test-operator-audit-close
```

O último comando deve ficar vermelho enquanto os WPs 13C a 13J ainda têm `pending`. Isso
é a prova de que o fechamento não aceita tela não visitada. O CI normal roda o gate
estrutural e impede nova dívida; o 13K liga o fechamento quando as evidências existirem.

## Scanner geométrico

`scanOperatorGeometry` verifica overflow, item fora do viewport, chrome cobrindo ação,
clipping de texto e foco, camada de overlay, envelope de toque, distância entre ações,
safe area, forma de skeleton e limites de pane. Marque o envelope real de checkbox,
switch ou outro composto com `data-touch-envelope`; não aumente o desenho do controle
para satisfazer a métrica. `data-operator-audit-ignore` só vale em fixture deliberada,
nunca numa tela auditada.

## Atalhos

Todo comando novo declara id, combinações por plataforma, escopo, owner, contextos
habilitados e proibidos, alternativa sem teclado e regras de campo/overlay/repeat/IME.
`defineOperatorShortcutMap` recusa colisões. `useOperatorShortcutMap` é o único listener
global autorizado para comandos novos.

Os listeners anteriores estão em `operator-global-shortcut-exceptions.json`. A entrada
do `Alt+S` do PDV está nomeada, mas o 13B não escolhe seu substituto. O WP-UX-13J toma
essa decisão com Chrome/Edge, Windows/macOS, ABNT2 e teclado internacional.

## Splitter

O consumidor fornece limites próprios nas `items`; o wrapper não conhece PDV, KDS ou
mobile. `USplitter` (`NuxtSplitter` na suíte) continua dono de ponteiro, setas, Home/End e ARIA. O kit acrescenta:

- id estável para SSR/hidratação;
- chave de persistência explícita;
- storage que descarta JSON inválido, tamanho não finito e contagem errada de panes;
- passo de teclado configurável, rótulo do separador e alvo de ponteiro;
- `reset()` para restaurar a divisão inicial.

Mobile e touch continuam decisão do consumidor. Não se monta Splitter onde a tarefa pede
sheet, sequência vertical ou troca de tela.

## Catálogo vivo e CI

`npm run catalog:dev` abre o catálogo em `/__operator_kit_catalog`. A rota só é injetada
quando a env do harness vale `1`; builds normais dos oito apps não a conhecem. O catálogo
demonstra shell de escritório, shell operacional, dashboard, sidebar desktop/mobile,
navbar, toolbar, página com aside, splitter, formulário, tabela/lista, overlays e estados.

O job `operator-kit` executa unitários, lint, typecheck, build do catálogo, Chromium fixado,
matriz visual, scanner e upload das evidências/contact sheets. Os gates Python rodam antes
da matriz e emitem arquivo, tela, cenário ou exceção que faltou.

## O que esta frente não declara

- Nenhum dos oito apps foi auditado por aparecer como fixture.
- Marketing e PDV continuam com harnesses locais legados; eles passam a consumir o runner
  quando seu WP declarar cenários e evidências no ledger.
- Nenhuma exceção operacional de dispositivo foi aprovada aqui.
- A retomada do PDV acontece somente depois do merge do 13B.
