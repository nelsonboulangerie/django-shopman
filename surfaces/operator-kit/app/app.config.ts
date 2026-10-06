export default defineAppConfig({
  ui: {
    card: {
      slots: {
        header: "p-4",
        body: "p-4",
        footer: "p-4",
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
      variants: { size: { md: { base: "h-control px-3 py-2 text-sm" } } },
      defaultVariants: { size: "md" },
    },
    selectMenu: {
      variants: { size: { md: { base: "h-control px-3 py-2 text-sm" } } },
      defaultVariants: { size: "md" },
    },
    textarea: {
      variants: { size: { md: { base: "px-3 py-2 text-sm" } } },
      defaultVariants: { size: "md" },
    },
    alert: {
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
