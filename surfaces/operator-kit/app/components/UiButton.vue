<script lang="ts">
import type { HTMLAttributes } from "vue";

export type UiButtonVariant =
  | "default"
  | "destructive"
  | "outline"
  | "secondary"
  | "ghost"
  | "link"
  | "gradient";

export type UiButtonSize =
  "xs" | "sm" | "default" | "lg" | "icon-xs" | "icon-sm" | "icon" | "icon-lg";

export type UiButtonEffect =
  | "expandIcon"
  | "ringHover"
  | "shine"
  | "shineHover"
  | "gooeyRight"
  | "gooeyLeft"
  | "underline"
  | "hoverUnderline"
  | "gradientSlideShow";

export type UiButtonProps = {
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
  loading?: boolean;
  as?: string;
  to?: string | Record<string, unknown>;
  href?: string;
  target?: string;
  rel?: string;
  class?: HTMLAttributes["class"];
  variant?: UiButtonVariant;
  size?: UiButtonSize;
  text?: string;
  iconPlacement?: "left" | "right";
  icon?: string;
  loadingIcon?: string;
  block?: boolean;
  effect?: UiButtonEffect;
  skeuomorphic?: boolean;
};
</script>

<script setup lang="ts">
import { computed, normalizeClass } from "vue";

defineOptions({ inheritAttrs: false });

const props = withDefaults(defineProps<UiButtonProps>(), {
  type: "button",
  loadingIcon: "line-md:loading-loop",
  iconPlacement: "left",
  loading: false,
  variant: "default",
  size: "default",
  block: false,
});

const emit = defineEmits<{ click: [event: MouseEvent] }>();

// A aparência pertence ao Nuxt UI. Antes, o wrapper deixava o `NuxtButton`
// gerar um botão `primary/solid` e tentava pintar outra variante por cima com
// classes. O resultado era estruturalmente contraditório: um `outline` mantinha
// `text-inverted` do sólido e virava texto branco sobre papel. Esta tradução é a
// única camada da casa: nomes legados entram, variantes oficiais saem.
const appearance: Record<
  UiButtonVariant,
  {
    color: "primary" | "error" | "neutral";
    variant: "solid" | "outline" | "soft" | "ghost" | "link";
  }
> = {
  default: { color: "primary", variant: "solid" },
  destructive: { color: "error", variant: "solid" },
  outline: { color: "neutral", variant: "outline" },
  secondary: { color: "neutral", variant: "soft" },
  ghost: { color: "neutral", variant: "ghost" },
  link: { color: "primary", variant: "link" },
  gradient: { color: "primary", variant: "solid" },
};

const sizes: Record<UiButtonSize, string> = {
  xs: "h-7 gap-1 px-2.5 text-xs has-[>svg]:px-2",
  sm: "h-9 gap-1.5 px-3 has-[>svg]:px-2.5",
  default: "h-11 px-4 py-2 has-[>svg]:px-3",
  lg: "h-14 px-6 has-[>svg]:px-4",
  "icon-xs": "size-7",
  "icon-sm": "size-9",
  icon: "size-11",
  "icon-lg": "size-14",
};

const nuxtSizes: Record<UiButtonSize, "xs" | "sm" | "md" | "lg" | "xl"> = {
  xs: "xs",
  sm: "sm",
  default: "md",
  lg: "xl",
  "icon-xs": "xs",
  "icon-sm": "sm",
  icon: "md",
  "icon-lg": "xl",
};

const effects: Record<UiButtonEffect, string> = {
  expandIcon: "group relative gap-0",
  ringHover: "hover:ring-ring/50 transition-all duration-300 hover:ring-3",
  shine:
    "before:animate-shine relative overflow-hidden bg-position-[0s_ease] before:absolute before:inset-0 before:rounded-[inherit] before:bg-[linear-gradient(45deg,transparent_25%,rgba(255,255,255,0.5)_50%,transparent_75%,transparent_100%)] before:bg-size-[250%_250%,100%_100%] before:bg-no-repeat",
  shineHover:
    "relative overflow-hidden before:absolute before:inset-0 before:rounded-[inherit] before:bg-[linear-gradient(45deg,transparent_25%,rgba(255,255,255,0.5)_50%,transparent_75%,transparent_100%)] before:bg-size-[250%_250%,100%_100%] before:bg-position-[200%_0,0_0] before:bg-no-repeat before:transition-[background-position_0s_ease] before:duration-1000 hover:before:bg-position-[-100%_0,0_0]",
  gooeyRight:
    "relative z-0 overflow-hidden duration-500 before:absolute before:inset-0 before:-z-10 before:translate-x-[150%] before:translate-y-[150%] before:scale-[2.5] before:rounded-[100%] before:bg-linear-to-r before:from-white/40 before:transition-transform before:duration-1000 hover:before:translate-x-[0%] hover:before:translate-y-[0%]",
  gooeyLeft:
    "relative z-0 overflow-hidden duration-500 after:absolute after:inset-0 after:-z-10 after:translate-x-[-150%] after:translate-y-[150%] after:scale-[2.5] after:rounded-[100%] after:bg-linear-to-l after:from-white/40 after:transition-transform after:duration-1000 hover:after:translate-x-[0%] hover:after:translate-y-[0%]",
  underline:
    "after:bg-primary relative no-underline! after:absolute after:bottom-2 after:h-px after:w-2/3 after:origin-bottom-left after:scale-x-100 after:transition-transform after:duration-300 after:ease-in-out hover:after:origin-bottom-right hover:after:scale-x-0",
  hoverUnderline:
    "after:bg-primary relative no-underline! after:absolute after:bottom-2 after:h-px after:w-2/3 after:origin-bottom-right after:scale-x-0 after:transition-transform after:duration-300 after:ease-in-out hover:after:origin-bottom-left hover:after:scale-x-100",
  gradientSlideShow:
    "animate-gradient-flow bg-[linear-gradient(-45deg,var(--gradient-lime),var(--gradient-ocean),var(--gradient-wine),var(--gradient-rust))] bg-size-[400%] text-white",
};

const rootClass = computed(() => [
  "active:translate-y-px",
  sizes[props.size],
  props.variant === "gradient"
    ? "bg-[linear-gradient(314deg,color-mix(in_oklch,var(--primary),white_33%),var(--primary))] hover:brightness-110"
    : "",
  props.effect ? effects[props.effect] : "",
  props.skeuomorphic
    ? "[box-shadow:0px_0px_0px_1px_rgba(0,0,0,0.18)_inset,0px_-2px_0px_0px_rgba(0,0,0,0.05)_inset,var(--shadow-xs)]"
    : "",
  props.block ? "w-full" : "",
  normalizeClass(props.class),
]);

const iconOnly = computed(() => props.size.startsWith("icon"));
const nuxtAppearance = computed(() => appearance[props.variant]);
</script>

<template>
  <NuxtButton
    v-bind="$attrs"
    :as="as"
    :to="to"
    :href="href"
    :target="target"
    :rel="rel"
    :type="type"
    :disabled="disabled"
    :loading="loading"
    :loading-icon="loadingIcon"
    :color="nuxtAppearance.color"
    :variant="nuxtAppearance.variant"
    :size="nuxtSizes[size]"
    :leading-icon="icon && iconPlacement === 'left' ? icon : undefined"
    :trailing-icon="icon && iconPlacement === 'right' ? icon : undefined"
    :square="iconOnly"
    :block="block"
    :class="rootClass"
    :ui="{
      leadingIcon: 'size-4',
      trailingIcon: 'size-4',
      label: 'min-w-0 truncate',
    }"
    @click="emit('click', $event)"
  >
    <slot>
      <span v-if="text">{{ text }}</span>
    </slot>
  </NuxtButton>
</template>
