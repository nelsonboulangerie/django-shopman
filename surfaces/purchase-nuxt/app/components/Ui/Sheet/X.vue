<template>
  <DialogClose data-slot="sheet-close-x" :class="styles({ class: normalizeClass(props.class) || undefined })" v-bind="forwarded">
    <slot>
      <Icon :name="icon" class="size-5" />
      <span class="sr-only">{{ srText }}</span>
    </slot>
  </DialogClose>
</template>

<script lang="ts" setup>
  import { DialogClose } from "reka-ui";
  import type { DialogCloseProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";
  import { reactiveOmit } from "@vueuse/core";
  import { tv } from "tailwind-variants";

  const props = withDefaults(
    defineProps<
      DialogCloseProps & {
        class?: HTMLAttributes["class"];
        icon?: string;
        /** O que o leitor de tela anuncia. */
        srText?: string;
      }
    >(),
    { icon: "lucide:x", srText: "Fechar" },
  );
  const forwarded = reactiveOmit(props, "class", "icon", "srText");
  const styles = tv({
    base: "inline-flex size-11 shrink-0 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-hidden disabled:pointer-events-none",
  });
</script>
