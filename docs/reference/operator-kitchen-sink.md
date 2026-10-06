# Operator Kitchen Sink canônico

O Operator Kitchen Sink é a superfície executável do design system das apps de
operador. Ele não é uma galeria paralela: a página real
`surfaces/kitchensink-nuxt` compõe `OperatorKitchenSink`, cujas fixtures,
componentes, tokens e receitas continuam em `surfaces/operator-kit`.

## Contrato

- Nuxt UI fornece anatomia, estados ARIA, foco e comportamento base.
- O `operator-kit` traduz tokens e acrescenta apenas contratos estruturais ou comportamento operacional compartilhado.
- A app Kitchen Sink não declara primitiva, token ou layout próprio.
- Diferença apenas estética não cria variante.
- Componente local de domínio pode existir; shell, navegação, page header, toolbar, splitter, overlay ou token visual novo precisa entrar no cânone ou no registro forte de exceções.
- Fixtures são estáticas e determinísticas. Nenhum cenário depende do Django ou de dados vivos.

## Léxico mínimo

| Nome | Responsabilidade | Composição permitida | Não usar para |
|---|---|---|---|
| `OperatorAppRoot` | raiz Nuxt UI, toaster e contexto comum | uma vez na casca do app | shell ou navegação |
| `OperatorOfficeShell` | sidebar, navbar, toolbar e painel Nuxt UI | gestão, análise, cadastros | fluxo contínuo de chão |
| `OperatorOperationalShell` | chrome estável e barra de ação | PDV, Cozinha, Produção | dashboard administrativo |
| `OperatorPage` | container, header, body, links e aside | página com fluxo de leitura | substituir pane de operação |
| `OperatorPageHeader` | título, posto, busca, status, filtros e ações | dentro de shell operacional | inventar cabeçalho local |
| `OperatorSuiteRail` | navegação da suíte por seções | um modelo de seção por app | navegação de página |
| `OperatorSectionBar` | alternativa responsiva ao rail | celular e tablet em pé | segunda fonte de navegação |
| `UiToolbar` | ações e filtros do mesmo contexto | controles irmãos | layout geral da página |
| `OperatorSplitter` | panes redimensionáveis, teclado e persistência | lista/detalhe e editor/prévia no desktop | duas colunas comprimidas no celular |
| `UiModal` | decisão bloqueante com foco contido | confirmação ou formulário curto | workspace longo ou navegação |
| Nuxt UI puro | card, alert, empty, skeleton, table, form, badge, tabs, popover | composição direta com tokens do kit | wrapper que apenas renomeia |

`UiButton` conserva somente a tradução legada de hierarquia e as alturas
operacionais já usadas. Efeitos, gradientes e sombra skeuomórfica sem consumidor
foram removidos. Eles não são variantes semânticas.

## Anatomias

### Escritório

`OperatorAppRoot > OperatorOfficeShell > OperatorPage`. A sidebar contém a
navegação do domínio; navbar contém identidade e ação principal; toolbar contém
filtros ou tabs. O corpo usa seções com títulos explícitos. `aside` explica a
decisão sem competir com a ação.

### Operação

`OperatorAppRoot > OperatorOperationalShell`. Navegação, `OperatorPageHeader`,
conteúdo e barra de ação são regiões distintas. A ação atual permanece estável;
o conteúdo usa `min-width: 0`, rolagem própria e safe area.

### Split view

`OperatorSplitter` é a única anatomia de panes simultâneas. Desktop preserva
limites, teclado e tamanho salvo. Em celular, a mesma necessidade vira sequência
ou sheet. Não se reduz tipografia para manter duas panes.

### Formulários e fluxos

`NuxtForm` + `NuxtFormField` organizam campos. Ajuda esclarece formato ou
consequência. Ações ficam no final e seguem a hierarquia primária, secundária,
destrutiva. Fluxos com etapas usam `UiStepper` e `useNextFocus`; a etapa atual
declara `data-focus-target`.

### Listas, tabelas, detalhes e filas

- lista: identidade, estado, dado para decidir e próximo ato;
- tabela: comparação entre colunas; abaixo do limite útil, vira cartões;
- detalhe: título, estado, fatos, histórico e ações, nesta ordem;
- fila: exceções humanas primeiro, depois ordenação, restante e vazio;
- dashboard: resposta e consequência antes do gráfico; métrica sem contexto não é dashboard.

### Overlays

Há cinco receitas, não uma largura por tela: confirmação, formulário curto,
workspace, detalhe lateral e captura em tela cheia. Popover é informação breve.
Sheet é detalhe ou ação responsiva. Modal não substitui página.

## Laboratório visual e contratos oficiais

O início do catálogo mostra exercícios comparáveis, ainda sujeitos à decisão do
dono: card pai suave com unidade branca, card branco com unidade suave, elevação
discreta, ação principal em largura total, divisão 1:2 e largura pelo conteúdo.
Não são novas variantes autorizadas para todas as apps.

Badges demonstram `solid`, `outline`, `soft` e `subtle` com cores semânticas,
primária e neutra. Grupos de checkbox e radio demonstram `list`, `card` e `table`.
Select e SelectMenu usam popovers oficiais, incluindo busca e item indisponível.
Calendários usam data fixa e intervalo fixo, sem depender do relógio ou do backend.

A tabela compõe seleção, expansão, badges, sorting, filtro, total de coluna,
paginação e rolagem externa. Reordenação manual tem exercício próprio com drag
and drop e alternativa equivalente por teclado/toque. Fetch e infinite scroll
devem consumir os contratos de dados e reconciliação do kit; não exigem nova
estética nem um mock de rede vivo no catálogo.

`useNextFocus` acompanha mudança de etapa. `usePendingAction` demonstra uma
resposta simulada concluída explicitamente, com bloqueio de repetição.
`useConnectivity` mostra a rede real do dispositivo separada dos estados de
fixture. O shell usa DashboardGroup/Sidebar/Panel/Navbar/Toolbar e a página usa
Container/Page/Header/Body/Aside oficiais.

O tema é definido em `operator-theme.css` e `app/app.config.ts` na layer:
`@theme` fornece tipografia e geometria, `--ui-*` traduz cores e superfícies para
o contrato oficial, e slots globais mantêm legibilidade dos alertas. O painel
não soma padding ao container da página. Ícones usam `@nuxt/icon`, SVG e coleções
locais; o scan inclui fixtures TypeScript. Fontes usam `@nuxt/fonts` com
Instrument Sans. Não se introduz CDN manual, fonte por componente ou paleta local.

Referências: [índice para agentes](https://ui.nuxt.com/llms.txt),
[design system](https://ui.nuxt.com/docs/getting-started/theme/design-system),
[variáveis CSS](https://ui.nuxt.com/docs/getting-started/theme/css-variables) e
[customização por slots](https://ui.nuxt.com/docs/getting-started/theme/components).

## Cenários determinísticos

O seletor do Kitchen Sink grava o cenário na URL. Os cenários cobrem `loading`,
`empty`, `error`, `offline`, `reconnecting`, `slow-network`, `readonly`,
`forbidden`, `success` e `extreme-content`, além do normal. A matriz do ledger
mantém também seleção, overlays, teclado, toque, conteúdo longo e estados salvos.

- loading inicial usa skeleton da anatomia final;
- atualização parcial preserva o dado anterior;
- offline diz o que ainda funciona;
- reconexão mantém o último dado confirmado;
- rede lenta bloqueia repetição ambígua do gesto;
- readonly mostra dados e explica por que a ação não está disponível;
- forbidden não vaza dado protegido;
- erro recuperável oferece próximo passo; erro terminal nomeia a saída;
- sucesso confirma a nova fonte da verdade;
- conteúdo extremo quebra linha, nunca reduz tipografia para caber.

## Matriz das necessidades reais

O inventário em `operator-component-ledger.json` contém 60 telas e 241 variantes
dos oito apps operacionais. O Kitchen Sink não promove cada diferença histórica;
condensa as necessidades abaixo.

| Apps | Necessidade comprovada | Solução canônica |
|---|---|---|
| Central | launcher, atenção cross-app, avisos | office dashboard, attention list, metric tile |
| PDV | venda densa, carrinho, pagamento, caixa | operational split workspace, pane/sheet responsivo, step flow |
| Cozinha | tickets, urgência, fila por telefone | operational queue, live/stale status, action sheet |
| Gestor | fila, board, bulk, detalhe, catálogo | queue recipe, table/cards, splitter, side detail |
| Produção | estágios, planejamento, QC, receitas | operational grid, progress header, step flow, editor split |
| Marketing | decisão, composição, revisão, agenda | office list, workspace, form/stepper, preview split |
| Compras | compra, recebimento, contagem, cadastro | dashboard, master/detail, exception flow, scanner overlay |
| B.I. | KPIs, explicação, gráfico, comparação | analytical dashboard, semantic palette, table fallback |

Redundâncias que devem convergir: sete adapters locais de rail/barra, headers
manuais, shells de settings/list-detail, larguras próprias de modal, cards feitos
por classes, tabelas sem fallback e page states locais. Visualização de domínio
continua local quando carrega semântica, mas consome paleta e tipografia do kit.

## Exceções inevitáveis

Exceção exige `app`, `surface`, caso de uso, limitação concreta do cânone,
alternativas rejeitadas, justificativa, responsável e teste. Os registros
executáveis ficam em `operator-layout-exceptions.json`,
`operator-token-exceptions.json` e `operator-global-shortcut-exceptions.json`.

As exceções funcionais aceitas são: segundo monitor público do PDV, painel
público de retirada, quadro distante de Produção, mídia física de
impressão/etiqueta e captura por câmera, scanner, áudio ou periférico. Elas
mudam audiência, meio ou API do dispositivo. Não autorizam nova estética.

Marketing preview, colunas do Gestor, editor acoplado de Compras, gráficos do
B.I., page headers, menus e rails não justificam anatomia paralela.

## Como consumir

1. Estenda `../operator-kit` e mantenha SSR. Use `OperatorAppRoot` na casca.
2. Escolha `OperatorOfficeShell` ou `OperatorOperationalShell` pela tarefa, não pelo app.
3. Componha Nuxt UI diretamente quando ele já resolve o contrato.
4. Use as receitas do Kitchen Sink para página, estado e responsividade.
5. Se faltar capacidade recorrente em pelo menos dois casos reais, evolua o kit, acrescente cenário determinístico, documentação e teste.
6. Se a necessidade for realmente específica, registre a exceção forte antes do componente ou token.

## Desenvolvimento, preview e dispositivos reais

```bash
cd surfaces/operator-kit && npm ci
cd ../kitchensink-nuxt && npm ci && npm run dev
# http://127.0.0.1:3009
```

A surface é `deployment: preview`: participa de CI, Dependabot, PWA e imagem
standalone, mas não entra em `operator-office`, no ingress ou na Central. Isso
impede que o catálogo afete a saúde das apps operacionais. O preview usa a
permissão exclusiva `backstage.view_operator_kitchen_sink`, sem concessão a
grupos; apenas superusuário entra até uma concessão explícita.

```bash
docker build -f surfaces/Dockerfile.surface \
  --build-arg SURFACE=kitchensink-nuxt -t shopman-kitchensink .
cloudflared tunnel --url http://127.0.0.1:3009
```

Para testar num dispositivo real, abra a URL temporária no telefone/tablet,
autentique uma conta autorizada e percorra teclado externo, toque, rotação, safe
areas, zoom do sistema, overlays, perda/retorno da rede e textos longos. O túnel
deve apontar para o ambiente local; não reutilize cookies do domínio vivo em
`trycloudflare.com`.

## Gates

```bash
make test-surface-registry test-surface-versions test-operator-ux
python scripts/check_operator_component_ledger.py --app kitchensink --require-complete
cd surfaces/operator-kit && npm run lint && npm test && npm run typecheck && npm run catalog:build && npm run test:visual
cd ../kitchensink-nuxt && npm run lint && npm test && npm run typecheck && npm run build
```

Os gates derivam as apps do registry, bloqueiam layout estrutural novo, listener
global, import direto de Reka/Nuxt UI fora do kit, crescimento das dívidas de
controle, e qualquer custom property fora da lista exata de exceções. A matriz
visual oficial cobre 1920×1080, 1440×900, 1366×768, 1280×800, 1180×820 touch,
820×1180 touch, 390×844, 320×568 e 1280×800 a 200%.
