<template>
  <TabsRoot data-slot="tabs" v-bind="forwarded" :class="normalizeClass(props.class)">
    <slot />
  </TabsRoot>
</template>

<script lang="ts" setup>
import { TabsRoot, useForwardPropsEmits } from "reka-ui";
import type { TabsRootEmits, TabsRootProps } from "reka-ui";
import { reactiveOmit } from "@vueuse/core";
import { normalizeClass } from "vue";
import type { HTMLAttributes } from "vue";

const props = withDefaults(
  defineProps<TabsRootProps & { class?: HTMLAttributes["class"] }>(),
  { orientation: "horizontal", activationMode: "automatic" },
);
const emits = defineEmits<TabsRootEmits>();
const forwarded = useForwardPropsEmits(reactiveOmit(props, "class"), emits);
</script>
