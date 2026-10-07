export default defineAppConfig({
  ui: {
    dashboardNavbar: { slots: { root: "bg-card" } },
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
    chip: {
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
          color: "secondary",
          variant: "subtle",
          class: {
            root: "bg-[color-mix(in_srgb,var(--secondary-foreground)_10%,var(--card))]",
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
    card: {
      // Densidade operacional única. O UCard oficial sobe para 24 px no body em
      // `sm`; no Gestor isso desperdiça uma linha útil em cada unidade da fila.
      // Conservamos anatomia, variantes e divisores do Nuxt UI, mas fixamos os
      // três slots em 16 px — exatamente o contrato documentado no Kitchen Sink.
      // Tabela que é o conteúdo inteiro do card fica integrada a ele, sem padding
      // (dono, 07/10/2026): a borda e o fundo branco são do card, as linhas vão de
      // ponta a ponta. Com mais coisas no corpo (o resumo do pedido), o padding fica.
      slots: {
        header: "p-4 sm:p-4",
        body: "p-4 sm:p-4 has-[>[data-slot=root]:only-child>table]:p-0",
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
    // Tabela mora dentro do card branco (dono, 07/10/2026). O cabeçalho fixo e a
    // coluna fixada do Nuxt UI pintam `bg-default/75`, que aqui é o bege da página
    // a 75%: a tabela ficava creme por cima do card, e o que rola por baixo da coluna
    // fixada vazava por ela. Mesmo fundo do card, opaco; o resto é o oficial.
    table: {
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
    select: {
      slots: { content: "bg-popover" },
    },
    selectMenu: {
      slots: { content: "bg-popover" },
    },
  },
});
