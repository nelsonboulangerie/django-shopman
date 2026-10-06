<script lang="ts">
import type { HTMLAttributes } from "vue";

export type UiButtonVariant =
  | "default"
  | "destructive"
  | "outline"
  | "secondary"
  | "ghost"
  | "link";

export type UiButtonSize =
  "xs" | "sm" | "default" | "lg" | "icon-xs" | "icon-sm" | "icon" | "icon-lg";

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

const rootClass = computed(() => [
  "active:translate-y-px",
  sizes[props.size],
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
