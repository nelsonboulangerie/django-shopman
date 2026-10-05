<template>
  <TabsContent
    data-slot="tabs-content"
    v-bind="forwarded"
    :class="twMerge('outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring', normalizeClass(props.class))"
  >
    <slot />
  </TabsContent>
</template>

<script lang="ts" setup>
import { TabsContent } from "reka-ui";
import type { TabsContentProps } from "reka-ui";
import { reactiveOmit } from "@vueuse/core";
import { normalizeClass } from "vue";
import type { HTMLAttributes } from "vue";
import { twMerge } from "tailwind-merge";

const props = defineProps<TabsContentProps & { class?: HTMLAttributes["class"] }>();
const forwarded = reactiveOmit(props, "class");
</script>
