<template>
  <DialogOverlay
    data-slot="sheet-overlay"
    :class="styles({ isBlurred, class: normalizeClass(props.class) || undefined })"
    v-bind="forwarded"
  />
</template>

<script lang="ts" setup>
  import { DialogOverlay } from "reka-ui";
  import type { DialogOverlayProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";
  import { reactiveOmit } from "@vueuse/core";
  import { tv } from "tailwind-variants";

  const props = withDefaults(
    defineProps<
      DialogOverlayProps & {
        /** Classe(s) para o elemento raiz. */
        class?: HTMLAttributes["class"];
        /** Desfoca o que ficou atrás. */
        isBlurred?: boolean;
      }
    >(),
    { isBlurred: true },
  );

  const forwarded = reactiveOmit(props, "class");
  const styles = tv({
    base: "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 fixed inset-0 z-50",
    variants: {
      isBlurred: {
        true: "bg-background/60 backdrop-blur-sm",
        false: "backdrop-blur-none",
      },
    },
  });
</script>
