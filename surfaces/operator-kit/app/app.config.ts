export default defineAppConfig({
  ui: {
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
    input: {
      variants: { size: { md: { base: "h-control px-3 py-2 text-sm" } } },
      defaultVariants: { size: "md" },
    },
    select: {
      slots: { content: "bg-popover" },
      variants: {
        size: {
          md: {
            base: "h-control px-3 py-2 text-sm",
            leading: "ps-3",
            trailing: "pe-3",
            item: "min-h-control items-center px-3 py-2 text-sm gap-2",
          },
        },
      },
      compoundVariants: [
        { size: "md", leading: true, class: "ps-10" },
        { size: "md", trailing: true, class: "pe-10" },
      ],
      defaultVariants: { size: "md" },
    },
    selectMenu: {
      slots: { content: "bg-popover" },
      variants: {
        size: {
          md: {
            base: "h-control px-3 py-2 text-sm",
            leading: "ps-3",
            trailing: "pe-3",
            item: "min-h-control items-center px-3 py-2 text-sm gap-2",
          },
        },
      },
      compoundVariants: [
        { size: "md", leading: true, class: "ps-10" },
        { size: "md", trailing: true, class: "pe-10" },
      ],
      defaultVariants: { size: "md" },
    },
    textarea: {
      variants: { size: { md: { base: "px-3 py-2 text-sm" } } },
      defaultVariants: { size: "md" },
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
