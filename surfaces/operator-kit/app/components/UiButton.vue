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
  "group inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap outline-none transition active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-invalid:border-destructive disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4";

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

const rootClass = computed(() => [
  base,
  variants[props.variant],
  sizes[props.size],
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
