<template>
  <DialogTitle data-slot="sheet-title" :class="styles({ class: normalizeClass(props.class) || undefined })" v-bind="forwarded">
    <slot>{{ title }}</slot>
  </DialogTitle>
</template>

<script lang="ts" setup>
  import { DialogTitle } from "reka-ui";
  import type { DialogTitleProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";
  import { reactiveOmit } from "@vueuse/core";
  import { tv } from "tailwind-variants";

  const props = defineProps<
    DialogTitleProps & {
      class?: HTMLAttributes["class"];
      /** O texto do título. */
      title?: string;
    }
  >();
  const forwarded = reactiveOmit(props, "class", "title");
  const styles = tv({ base: "text-foreground font-semibold" });
</script>
