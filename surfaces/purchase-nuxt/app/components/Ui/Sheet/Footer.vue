<template>
  <Primitive data-slot="sheet-footer" :class="styles({ class: normalizeClass(props.class) || undefined })" v-bind="forwarded">
    <slot />
  </Primitive>
</template>

<script lang="ts" setup>
  import { Primitive } from "reka-ui";
  import type { PrimitiveProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";
  import { reactiveOmit } from "@vueuse/core";
  import { tv } from "tailwind-variants";

  const props = withDefaults(
    defineProps<PrimitiveProps & { class?: HTMLAttributes["class"] }>(),
    { as: "div" },
  );
  const forwarded = reactiveOmit(props, "class");
  const styles = tv({ base: "mt-auto flex flex-col gap-2 p-4" });
</script>
