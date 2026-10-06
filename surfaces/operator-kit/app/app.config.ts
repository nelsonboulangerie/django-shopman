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
    popover: { slots: { content: "bg-popover" } },
    slideover: { slots: { content: "bg-card" } },
    modal: { slots: { content: "bg-card" } },
    drawer: { slots: { content: "bg-card" } },
    tooltip: { slots: { content: "bg-popover text-default" } },
    dropdownMenu: { slots: { content: "bg-popover" } },
    contextMenu: { slots: { content: "bg-popover" } },
    card: {
      slots: {
        header: "p-4 sm:px-4",
        body: "p-4 sm:p-4",
        footer: "p-4 sm:px-4",
      },
      variants: {
        variant: {
          outline: { root: "bg-card" },
          solid: { description: "text-inverted opacity-100" },
        },
      },
      defaultVariants: { variant: "outline" },
    },
    // Altura de controle: padrão do Nuxt UI no ponteiro fino (compacto) e
    // --spacing-control (44/48) só no @media (pointer: coarse). Não se força
    // altura base em campo nem em botão — era isso que desalinhava select x
    // Number/Date/Time e inflava a paginação.
    select: {
      slots: { content: "bg-popover" },
    },
    selectMenu: {
      slots: { content: "bg-popover" },
    },
    alert: {
      defaultVariants: { variant: "subtle" },
      slots: {
        title: "text-default",
        description: "text-default opacity-100",
      },
      compoundVariants: [
        {
          variant: "solid",
          class: {
            title: "text-inherit",
            description: "text-inherit opacity-100",
          },
        },
      ],
    },
  },
});
