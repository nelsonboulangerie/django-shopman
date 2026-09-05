<template>
  <UiSheetPortal :to="to">
    <slot name="overlay">
      <UiSheetOverlay :is-blurred />
    </slot>
    <DialogContent
      data-slot="sheet-content"
      :class="styles({ side, class: normalizeClass(props.class) || undefined })"
      v-bind="{ ...forwarded, ...$attrs }"
    >
      <slot />
    </DialogContent>
  </UiSheetPortal>
</template>

<script lang="ts" setup>
  import { DialogContent, useForwardPropsEmits } from "reka-ui";
  import type { DialogContentEmits, DialogContentProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";
  import { reactiveOmit } from "@vueuse/core";
  import { tv } from "tailwind-variants";
  import type { VariantProps } from "tailwind-variants";

  defineOptions({ inheritAttrs: false });

  const styles = tv({
    base: "bg-card text-card-foreground data-[state=closed]:animate-out data-[state=open]:animate-in fixed z-50 flex flex-col shadow-lg transition ease-in-out data-[state=closed]:duration-200 data-[state=open]:duration-300",
    variants: {
      side: {
        top: "data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top inset-x-0 top-0 h-auto border-b",
        bottom:
          "data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom inset-x-0 bottom-0 h-auto border-t",
        left: "data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left inset-y-0 left-0 h-full w-3/4 border-r sm:max-w-sm",
        right:
          "data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right inset-y-0 right-0 h-full w-3/4 border-l sm:max-w-sm",
      },
    },
    defaultVariants: { side: "right" },
  });

  const props = withDefaults(
    defineProps<
      DialogContentProps & {
        /** Classe(s) para o painel. */
        class?: HTMLAttributes["class"];
        /** De que lado a gaveta entra. */
        side?: VariantProps<typeof styles>["side"];
        /** Alvo do portal. */
        to?: string | HTMLElement;
        /** Desfoca o que ficou atrás. */
        isBlurred?: boolean;
      }
    >(),
    { isBlurred: true, side: "right" },
  );
  const emits = defineEmits<DialogContentEmits>();
  const forwarded = useForwardPropsEmits(reactiveOmit(props, ["class", "to", "side", "isBlurred"]), emits);
</script>
