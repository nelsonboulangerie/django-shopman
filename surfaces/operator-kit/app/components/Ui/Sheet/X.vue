<template>
  <DialogClose
    data-slot="sheet-close-x"
    :class="styles({ placement, class: normalizeClass(props.class) || undefined })"
    v-bind="forwarded"
  >
    <slot>
      <Icon :name="icon" :class="placement === 'inline' ? 'size-5' : 'size-4'" />
      <span class="sr-only">{{ srText }}</span>
    </slot>
  </DialogClose>
</template>

<script lang="ts" setup>
  import { DialogClose } from "reka-ui";
  import type { DialogCloseProps } from "reka-ui";
  import { tv } from "tailwind-variants";
  import type { VariantProps } from "tailwind-variants";
  import { reactiveOmit } from "@vueuse/core";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const props = withDefaults(
    defineProps<
      DialogCloseProps & {
        /** Custom class(es) to add to parent element. */
        class?: HTMLAttributes["class"];
        /** Icon to display. */
        icon?: string;
        /** Screen reader text. */
        srText?: string;
        /** Corner controls float over the sheet; inline controls participate in a custom header. */
        placement?: "corner" | "inline";
      }
    >(),
    {
      icon: "lucide:x",
      srText: "Fechar",
      placement: "corner",
    }
  );
  const forwarded = reactiveOmit(props, "class", "icon", "srText", "placement");
  const styles = tv({
    base: "ring-offset-background focus:ring-ring grid size-11 shrink-0 place-items-center rounded-md transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none",
    variants: {
      placement: {
        corner: "data-[state=open]:bg-secondary absolute top-2 right-2 opacity-70 transition-opacity hover:opacity-100",
        inline: "border border-border bg-card text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-ring",
      },
    },
  });
</script>
