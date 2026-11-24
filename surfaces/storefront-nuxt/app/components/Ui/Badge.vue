<template>
  <component
    :is="elementType"
    :class="
      badgeVariants({ disabled, size, variant, class: normalizeClass(props.class) || undefined })
    "
    v-bind="forwarded"
    @click="onClick"
  >
    <slot />
  </component>
</template>

<script lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { useForwardProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  import type { NuxtLinkProps } from "#app/components";
</script>

<script lang="ts" setup>
  const badgeVariants = tv({
    base: "focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 inline-flex w-fit max-w-full shrink-0 items-center justify-center gap-1 overflow-hidden rounded-md border text-center transition-[color,box-shadow] focus-visible:ring-[3px] [&>svg]:pointer-events-none [&>svg]:size-3",
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a&]:hover:bg-primary/90 border-transparent",
        secondary:
          "bg-secondary text-secondary-foreground [a&]:hover:bg-secondary/90 border-transparent",
        destructive:
          "bg-destructive focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40 [a&]:hover:bg-destructive/90 border-transparent text-white",
        outline: "text-foreground [a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        success:
          "bg-success text-success-foreground focus-visible:ring-success/30 [a&]:hover:bg-success/90 border-transparent",
        // Âmbar CLARO com texto do corpo, como o aviso (UiAlert warning) já faz: o âmbar
        // cheio da marca com letra branca dá 3,7:1 e reprova o AA a 14 px; nenhuma cor de
        // letra passa sobre aquele tom médio (X9, OC-30). O fundo é opaco porque o selo
        // senta sobre a foto do produto.
        warning:
          "bg-[color-mix(in_srgb,var(--warning)_22%,var(--background))] text-foreground border-warning/60 focus-visible:ring-warning/30",
        info: "bg-info text-info-foreground focus-visible:ring-info/30 [a&]:hover:bg-info/90 border-transparent",
        ghost: "text-foreground [a&]:hover:bg-accent/50 border-transparent bg-transparent",
        error:
          "bg-destructive focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40 [a&]:hover:bg-destructive/90 border-transparent text-white",
      },
      disabled: {
        true: "cursor-not-allowed opacity-50",
      },
      size: {
        sm: "px-2 py-0.5 text-xs font-medium",
        md: "px-2.5 py-[3px] text-sm font-medium",
        lg: "px-2.5 py-1 text-sm font-semibold",
      },
    },
    // O rótulo quebra linha em vez de vazar (`max-w-full`, sem `whitespace-nowrap`): com a
    // fonte do sistema a 200 %, "Fica pronto amanhã" saía do cartão do produto (X11).
    // `md` (14 px) por padrão: na loja o selo carrega estado e disponibilidade
    // ("Indisponível", "Fica pronto amanhã", "Últimas unidades"), que não descem de
    // 14 px (X9, OC-30). O `sm` (12) fica para o contador em pílula, pedido pelo nome.
    defaultVariants: {
      variant: "default",
      disabled: false,
      size: "md",
    },
  });

  type BadgeProps = VariantProps<typeof badgeVariants>;

  const props = defineProps<
    NuxtLinkProps & {
      /** Any additional class that should be added to the badge. */
      class?: HTMLAttributes["class"];
      /** The variant of the badge. */
      variant?: BadgeProps["variant"];
      /** The size of the badge. */
      size?: BadgeProps["size"];
      /** The action to perform when the badge is clicked. */
      onClick?: () => void;
      /** Should the badge be disabled or not. */
      disabled?: boolean;
      /** The element to render the badge as. */
      tag?: string;
    }
  >();

  const forwarded = useForwardProps(reactiveOmit(props, "class", "variant", "onClick", "disabled"));

  const elementType = computed(() => {
    if (props.tag) return props.tag;
    if (props.href || props.to) return resolveComponent("NuxtLink");
    if (props.onClick) return "button";
    return props.tag || "div";
  });
</script>
