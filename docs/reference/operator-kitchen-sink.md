# Operator Kitchen Sink canônico

## Revisão adversarial contra Nuxt UI 4.11.3 (06/10/2026)

A continuação cobre também o shell operacional do catálogo, navegação funcional,
ação persistente no footer oficial de DashboardPanel, modal, popover e Slideover,
readonly real, seleção parcial da tabela, reordenação e estados endereçáveis.
O catálogo inteiro recebe auditoria de contraste e geometria nos temas claro e
escuro nos nove viewports oficiais; estados adicionais e overlays interativos
rodam em desktop e 320px. A medição não é um certificado de cada pixel: limites
de cobertura e exceções são declarados abaixo, não escondidos por testes verdes.

Uma inspeção visual de toque encontrou o checkbox inflado e o switch circular.
A regra de tamanho mínimo agora exclui os desenhos desses controles. O tema
amplia somente o alvo por pseudo-elemento, preservando trilho, thumb e indicador
oficiais; a auditoria mede esse alvo e um teste clica fora do desenho do switch.
Seleção parcial usa o estado indeterminate oficial, não somente boolean.

Referência: documentação oficial corrente e implementação instalada. A versão
estável foi conferida também no registry npm. Esta revisão não certifica a
migração das telas existentes nem transforma o laboratório em catálogo completo.

| Achado | Correção ou limite explícito |
| --- | --- |
| Sidebar independente aninhada em DashboardSidebar | Removida. Apenas DashboardGroup, DashboardSidebar e DashboardPanel gerenciam layout e estado. |
| Conteúdo da navbar no slot central, oculto no mobile | Título pela prop oficial; ações no slot right; seletor contextual na DashboardToolbar. |
| Navegação repetida na toolbar e botão sem comportamento | Toolbar agora representa contexto, não repete o menu global; botão sem ação removido. |
| Sidebar sem collapse e IDs implícitos | Collapse oficial, NavigationMenu recebe collapsed e painéis têm IDs determinísticos. |
| Resize handle com role presentation | Removida alteração de semântica; eventos encaminhados ao handle oficial. |
| Form state vazio e controles desconectados | Estado reativo, names, v-model, validate e submit reais, herméticos. |
| Switch sem descrição e checkbox com API legada | NuxtSwitch e NuxtCheckbox diretos, com label e description oficiais. |
| Descrição do Switch 4.11.3 não associada por ARIA no componente puro | Slot description e aria-describedby explícitos, sem substituir o controle. Regressão testada no consumidor. |
| Título da navbar truncado em 320px | Quebra de linha no slot de título e toolbar contextual, sem reduzir a fonte. |
| Modal montado separado do acionador | NuxtModal direto com acionador no slot default e ações nos slots oficiais. |
| Tabela dentro de card com padding e duas rolagens | Body sem padding; uma área de scroll; apenas header sticky; footer participa do fluxo. |
| Seleção da tabela indexada pela posição | getRowId usa a ref estável, preservando identidade ao filtrar ou ordenar. |
| Segunda tabela prometia transformação em cards sem implementá-la | Copy corrigida para rolagem explícita; removido padding ao redor da tabela. |
| Stepper com adaptação local de anatomia | Exemplo usa NuxtStepper direto, com navegação não linear explicitamente demonstrada. |
| Off-line, rede lenta e reconexão simulados por copy | São cenários visuais, não teste de rede. O laboratório demonstra useConnectivity real separadamente. |

As escolhas aprovadas de superfície branca, outline, padding, tipografia e alvos
operacionais são tema, configurado na layer. Não autorizam implementações locais
de foco, portal, resize, navegação, validação ou seleção. `OperatorSplitter`
continua acrescentando persistência e atributos ARIA ao Splitter oficial; não é
uma substituição visual. O shell operacional do catálogo foi refeito com
DashboardGroup, DashboardSidebar, DashboardPanel, DashboardNavbar e
DashboardToolbar; isso não certifica os shells históricos das apps existentes.
Os exercícios de fetched/infinite data, rede simulada e periféricos ainda
não estão completos. A página única também não substitui receitas de telas
dedicadas e testadas: esses limites permanecem trabalho em aberto.

Fontes: [DashboardGroup](https://ui.nuxt.com/docs/components/dashboard-group),
[DashboardSidebar](https://ui.nuxt.com/docs/components/dashboard-sidebar),
[DashboardNavbar](https://ui.nuxt.com/docs/components/dashboard-navbar),
[DashboardPanel](https://ui.nuxt.com/docs/components/dashboard-panel),
[Form](https://ui.nuxt.com/docs/components/form),
[Switch](https://ui.nuxt.com/docs/components/switch),
[Table](https://ui.nuxt.com/docs/components/table),
[Modal](https://ui.nuxt.com/docs/components/modal).

O card padrão é `NuxtCard` outline: branco no tema claro (`bg-card`), borda,
sem sombra. Formulários e exemplos de controles usam esse padrão. No tema escuro,
a superfície acompanha `--card`, sem impor branco. Header, body e footer usam
padding de 1rem, inclusive no desktop. Cards solid mantêm texto invertido também
na descrição. Input, Select e SelectMenu padrão usam `size="md"`, 44px (48px em
tablet touch) e texto de 14px. Textarea mantém a tipografia, mas altura multilinha.
Outros tamanhos exigem necessidade demonstrada, não escolha estética arbitrária.

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

Modal, detalhe lateral e drawer usam `bg-card`; popover, menus e tooltip usam
`bg-popover` no tema da layer: branco no tema claro, superfície correspondente no
escuro. O backdrop continua translúcido, sem cobrir o contexto com branco opaco.
Alerts usam `subtle` por padrão. Exemplos têm ícone e
dismiss funcional; trocar o cenário reabre o aviso. Dismiss de um aviso não cancela
a operação nem altera o estado. Toast usa `useToast` e o toaster do `OperatorAppRoot`.

A busca usa `DashboardSearch` e `DashboardSearchButton`, com `Meta+K` oficial e
`Kbd`. O menu demonstra filhos e rodapé; o rodapé da página oferece referências.
A navegação interna rola apenas o corpo do `DashboardPanel`, não o chrome fixo.
`useScrollspy` acompanha as seções visíveis. O header recebe `collapsed` do
`DashboardSidebar` e conserva apenas o ícone quando recolhido.

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
