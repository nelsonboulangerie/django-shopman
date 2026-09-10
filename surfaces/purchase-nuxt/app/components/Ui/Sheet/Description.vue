<template>
  <DialogDescription
    data-slot="sheet-description"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
    v-bind="forwarded"
  >
    <slot>{{ description }}</slot>
  </DialogDescription>
</template>

<script lang="ts" setup>
  import { DialogDescription } from "reka-ui";
  import type { DialogDescriptionProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";
  import { reactiveOmit } from "@vueuse/core";
  import { tv } from "tailwind-variants";

  const props = defineProps<
    DialogDescriptionProps & {
      class?: HTMLAttributes["class"];
      /** O texto da descrição. */
      description?: string;
    }
  >();
  const forwarded = reactiveOmit(props, "class", "description");
  const styles = tv({ base: "text-muted-foreground text-sm" });
</script>
