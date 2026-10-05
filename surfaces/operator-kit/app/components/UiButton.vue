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
  | "xs"
  | "sm"
  | "default"
  | "lg"
  | "icon-xs"
  | "icon-sm"
  | "icon"
  | "icon-lg";

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

const base =
  "group focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:ring-[3px] active:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4";

const variants: Record<UiButtonVariant, string> = {
  default: "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90",
  destructive:
    "bg-destructive text-destructive-foreground shadow-xs hover:bg-destructive/90",
  outline:
    "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
  secondary:
    "bg-secondary text-secondary-foreground shadow-xs hover:bg-secondary/80",
  ghost: "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
  link: "text-primary underline-offset-4 hover:underline",
  gradient:
    "bg-[linear-gradient(314deg,color-mix(in_oklch,var(--primary),white_33%),var(--primary))] text-primary-foreground shadow-xs hover:brightness-110",
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
  base,
  variants[props.variant],
  sizes[props.size],
  props.effect ? effects[props.effect] : "",
  props.skeuomorphic
    ? "[box-shadow:0px_0px_0px_1px_rgba(0,0,0,0.18)_inset,0px_-2px_0px_0px_rgba(0,0,0,0.05)_inset,var(--shadow-xs)]"
    : "",
  props.block ? "w-full" : "",
  normalizeClass(props.class),
]);

const iconOnly = computed(() => props.size.startsWith("icon"));
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
