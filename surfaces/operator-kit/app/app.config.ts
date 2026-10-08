// Tokens do Nuxt UI redefinidos dentro do rail (ver `ui.dashboardSidebar`).
const RAIL_SCOPE = [
  "bg-rail text-rail-foreground",
  "[--ui-text:var(--rail-foreground)]",
  "[--ui-text-muted:var(--rail-foreground)]",
  "[--ui-text-dimmed:var(--rail-foreground)]",
  "[--ui-text-toned:var(--rail-foreground)]",
  "[--ui-text-highlighted:var(--rail-foreground)]",
  "[--primary:var(--rail-foreground)]",
  "[--ui-primary:var(--rail-foreground)]",
  "[--primary-ink:var(--rail-foreground)]",
  "[--ui-bg-elevated:rgb(0_0_0/0.4)]",
  "[--ui-bg:var(--rail)]",
  "[--ui-border:color-mix(in_srgb,var(--rail-foreground)_25%,transparent)]",
].join(" ");

export default defineAppConfig({
  ui: {
    // O título da barra do topo não se corta ("cópia não se corta"; achado do B.I.,
    // PR-K5): o oficial leva `truncate`, e a 390 px saía "Quem compra no balc…". Aqui
    // ele quebra em linhas (`text-clip` tira o `truncate` no merge, `whitespace-normal`
    // deixa quebrar) e a barra cresce além dos 56 px só quando precisa (`min-h`). A
    // coluna da direita é `shrink-0` no oficial: o título nunca empurra os botões.
    dashboardNavbar: {
      slots: {
        root: "bg-card h-auto min-h-(--ui-header-height) py-1",
        title: "text-clip whitespace-normal text-pretty min-w-0",
      },
    },
    dashboardToolbar: { slots: { root: "bg-card" } },
    checkbox: {
      slots: {
        base: "relative overflow-visible after:absolute after:content-[''] after:start-1/2 after:top-1/2 after:-translate-x-1/2 after:-translate-y-1/2 after:size-control",
        indicator: "rounded-[inherit]",
      },
    },
    switch: {
      slots: {
        base: "relative after:absolute after:content-[''] after:start-1/2 after:top-1/2 after:-translate-x-1/2 after:-translate-y-1/2 after:size-control",
      },
    },
    radioGroup: {
      slots: {
        base: "relative overflow-visible after:absolute after:content-[''] after:start-1/2 after:top-1/2 after:-translate-x-1/2 after:-translate-y-1/2 after:size-control",
        indicator: "rounded-full",
      },
    },
    // O maior tamanho oficial (3xl) basta para presença, mas não para contagens
    // como “6” e “9+”. Só o Chip numérico recebe um degrau extra. Mantemos o
    // círculo de 16 px aprovado, com texto de 12 px para manter a leitura compacta.
    // Anel de 2 px, a espessura do traço dos ícones Lucide (dono, 08/10/2026,
    // PR #1539). O anel é `ring-bg` do Nuxt UI: tem a cor do fundo onde o chip
    // está e o descola do ícone (no rail dourado, o `--ui-bg` do escopo do rail).
    // O `4xl` numerado é exceção declarada: o `3xl` oficial não lê dois dígitos.
    chip: {
      slots: { base: "ring-2" },
      variants: {
        size: {
          "4xl": "h-4 min-w-4 px-1 text-[12px]/none",
        },
      },
    },
    // `soft` é uma variante oficial do Kbd. Defini-la aqui evita que atalhos
    // idênticos mudem de aparência conforme a tela ou o componente consumidor.
    kbd: {
      defaultVariants: { variant: "soft" },
    },
    // Botão: o conjunto mínimo (dono, 08/10/2026, PR #1539) é tamanho `md` ou
    // `xl`, variante `solid`/`outline`/`ghost` e cor `primary`/`neutral`/`error`;
    // estado ativo por `active` + `active-variant`/`active-color`, nunca por ternário
    // no `variant`. A trava é `tests/guardrails.minimalSet.test.ts`. O default do
    // tema continua o oficial (`primary` `solid` `md`): trocá-lo repintaria em
    // silêncio cada `<NuxtButton>` sem cor escrita, que hoje é o gesto principal.
    //
    // Texto latão sobre latão a 10% (`soft`) precisa do tom de tinta do tema para
    // passar o AA (4,5:1); ver `--primary-ink` em operator-theme.css. Só a cor do
    // texto muda; anatomia e variantes continuam as do Nuxt UI. Fica para o estado
    // ativo do rail (`active-variant="soft"`).
    button: {
      compoundVariants: [
        { color: "primary", variant: "soft", class: "text-(--primary-ink)" },
      ],
    },
    // Selo: uma variante só, `soft` (sem borda), nas 6 cores neutral, primary,
    // info, success, warning e error (dono, 08/10/2026, PR #1539). Ninguém escreve
    // `variant` num selo; a trava é `tests/guardrails.minimalSet.test.ts`. AA medido
    // na proposta: mínimo 4,59:1; o primary usa a tinta `--primary-ink`.
    badge: {
      defaultVariants: { variant: "soft" },
      compoundVariants: [
        { color: "primary", variant: "soft", class: "text-(--primary-ink)" },
      ],
    },
    // Rail dourado (dono, 08/10/2026, PR #1539): todo DashboardSidebar da suíte
    // redefine os tokens do Nuxt UI SÓ dentro dele, e as peças canônicas que moram
    // ali (Button, NavigationMenu, Chip, Tooltip de gatilho) leem o dourado sem
    // classe nova nem `:ui` por instância. `--ui-bg` = o rail, para o anel do Chip
    // (`ring-bg`) ter a cor do fundo; `--primary-ink` também, porque o estado ativo
    // (`primary` `soft`) usa essa tinta e ela é resolvida no `:root` (latão sobre
    // latão). `content` é o mesmo rail aberto como slideover abaixo de `lg`.
    dashboardSidebar: {
      slots: {
        root: RAIL_SCOPE,
        content: RAIL_SCOPE,
      },
      variants: {
        side: { left: { root: "border-e-0" } },
      },
    },
    popover: { slots: { content: "bg-popover" } },
    slideover: { slots: { content: "bg-card" } },
    modal: { slots: { content: "bg-card" } },
    drawer: { slots: { content: "bg-card" } },
    tooltip: { slots: { content: "bg-popover text-default" } },
    dropdownMenu: { slots: { content: "bg-popover" } },
    contextMenu: { slots: { content: "bg-popover" } },
    // O `subtle` oficial usa cor/10, portanto é translúcido. Nas superfícies de
    // operador os Alerts também aparecem sobre conteúdo rolável; a tinta precisa
    // ser pré-composta com a superfície do tema para continuar sutil, mas opaca.
    // A anatomia, o padding, a borda e as variantes continuam sendo do Nuxt UI.
    // Conjunto mínimo (dono, 08/10/2026): `subtle` × info/success/warning/error.
    // `primary` e `neutral` estão fora do conjunto, mas ainda têm uso no próprio kit
    // (1 e 6 escritos, mais os ligados do OperatorInbox, contados em 08/10 depois de o
    // Gestor zerar os seus); ficam até a migração desses avisos e morrem com ela.
    alert: {
      compoundVariants: [
        {
          color: "primary",
          variant: "subtle",
          class: {
            root: "bg-[color-mix(in_srgb,var(--primary)_10%,var(--card))]",
          },
        },
        {
          color: "success",
          variant: "subtle",
          class: {
            root: "bg-[color-mix(in_srgb,var(--success)_10%,var(--card))]",
          },
        },
        {
          color: "info",
          variant: "subtle",
          class: {
            root: "bg-[color-mix(in_srgb,var(--info)_10%,var(--card))]",
          },
        },
        {
          color: "warning",
          variant: "subtle",
          class: {
            root: "bg-[color-mix(in_srgb,var(--warning)_10%,var(--card))]",
          },
        },
        {
          color: "error",
          variant: "subtle",
          class: {
            root: "bg-[color-mix(in_srgb,var(--destructive)_10%,var(--card))]",
          },
        },
        {
          color: "neutral",
          variant: "subtle",
          class: {
            root: "bg-[color-mix(in_srgb,var(--muted)_50%,var(--card))]",
          },
        },
      ],
    },
    accordion: {
      // O rótulo do item é item flex sem `min-w-0` no Nuxt UI: um texto longo no
      // slot default empurra a seta para fora e `truncate` nunca corta. Com
      // `min-w-0 flex-1` o rótulo cede espaço e a seta fica na borda (Em andamento
      // do Gestor, dono, 08/10/2026: a linha da situação trunca).
      slots: { label: "min-w-0 flex-1" },
    },
    // Cartão: o de topo é `outline` (default); cartão dentro de outro cartão é
    // `soft` (só fundo, sem borda dupla), escrito na chamada (dono, 08/10/2026).
    // `subtle` não entra. Não há regra de CSS que force o aninhado: é a chamada que
    // diz, e a trava proíbe `subtle`/`solid` novos.
    card: {
      // Densidade operacional única. O UCard oficial sobe para 24 px no body em
      // `sm`; no Gestor isso desperdiça uma linha útil em cada unidade da fila.
      // Conservamos anatomia, variantes e divisores do Nuxt UI, mas fixamos os
      // três slots em 16 px — exatamente o contrato documentado no Kitchen Sink.
      // Tabela que é o conteúdo inteiro do card fica integrada a ele, sem padding
      // (dono, 07/10/2026): a borda e o fundo branco são do card, as linhas vão de
      // ponta a ponta. Com mais coisas no corpo (o resumo do pedido), o padding fica.
      // Accordion como conteúdo inteiro é uma lista emoldurada: sem padding vertical,
      // o gatilho de cada item já dá o respiro (Em andamento, dono, 07/10/2026).
      // O `[data-state]` separa o item do Accordion do item do Timeline, que tem a
      // mesma anatomia (root > item) e precisa do padding: sem ele a Linha do tempo
      // do detalhe encostava no cabeçalho e na base do card (dono, 08/10/2026).
      slots: {
        header: "p-4 sm:p-4",
        body: "p-4 sm:p-4 has-[>[data-slot=root]:only-child>table]:p-0 has-[>[data-slot=root]:only-child>[data-slot=item][data-state]]:py-0",
        footer: "p-4 sm:p-4",
      },
      variants: {
        variant: {
          outline: { root: "bg-card" },
          solid: { description: "text-inverted opacity-100" },
        },
      },
      defaultVariants: { variant: "outline" },
    },
    // PageCard fica reservado a cartões navegáveis ou destaques semânticos. Sua
    // densidade acompanha UCard para não criar uma segunda escala de padding.
    pageCard: {
      slots: {
        container: "p-4 sm:p-4",
      },
      // Mesmo fundo do UCard outline: cartão é branco, também o horizontal da Grade
      // (dono, 07/10/2026). O bege fica só para a página.
      variants: {
        variant: {
          outline: { root: "bg-card" },
        },
      },
    },
    // Altura de controle: padrões compactos oficiais do Nuxt UI. Fluxos que
    // realmente precisam de alvo maior fazem opt-in no próprio componente; uma
    // regra global desalinharia tabs, toolbars, menus, paginação e rail.
    // Exceção opt-in (WP-OPERADOR-NUXTUI-ONDAS, onda 0): nas páginas que vestem a
    // suíte (os sete apps não migrados) e no catálogo, campo, select e item de lista
    // voltam aos 44 px do `main` (`suite-page:`, que alcança o portal da lista). O
    // Gestor não veste o marcador e fica no compacto.
    // `lg`/`xl` são os campos do login (o `largeFields` do PDV é o `xl`, o degrau de ação).
    input: {
      variants: {
        size: {
          md: { base: "suite-page:h-control" },
          lg: { base: "suite-page:h-control" },
          xl: { base: "suite-page:h-action" },
        },
      },
    },
    select: {
      slots: { content: "bg-popover" },
      variants: {
        size: {
          md: { base: "suite-page:h-control", item: "suite-page:min-h-control suite-page:items-center" },
        },
      },
    },
    selectMenu: {
      slots: { content: "bg-popover" },
      variants: {
        size: {
          md: { base: "suite-page:h-control", item: "suite-page:min-h-control suite-page:items-center" },
        },
      },
    },
    // Tabela mora dentro do card branco (dono, 07/10/2026). O cabeçalho fixo e a
    // coluna fixada do Nuxt UI pintam `bg-default/75`, que aqui é o bege da página
    // a 75%: a tabela ficava creme por cima do card, e o que rola por baixo da coluna
    // fixada vazava por ela. Mesmo fundo do card, opaco; o resto é o oficial.
    table: {
      // Tabela integrada ao card (sem padding): o contêiner rolável, quando focável
      // pelo teclado, desenha o anel PARA DENTRO. Para fora, o recorte do card o
      // cortava (a varredura de geometria do Kitchen Sink reprovava o foco).
      slots: {
        root: "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary",
      },
      variants: {
        pinned: {
          true: { th: "sticky bg-card z-1", td: "sticky bg-card z-1" },
        },
        sticky: {
          true: {
            thead: "sticky top-0 inset-x-0 bg-card z-1",
            tfoot: "sticky bottom-0 inset-x-0 bg-card z-1",
          },
          header: { thead: "sticky top-0 inset-x-0 bg-card z-1" },
          footer: { tfoot: "sticky bottom-0 inset-x-0 bg-card z-1" },
        },
      },
    },
  },
});
