<template>
  <TabsTrigger
    data-slot="tabs-trigger"
    v-bind="forwarded"
    :class="twMerge(baseClass, normalizeClass(props.class))"
  >
    <slot />
  </TabsTrigger>
</template>

<script lang="ts" setup>
import { TabsTrigger } from "reka-ui";
import type { TabsTriggerProps } from "reka-ui";
import { reactiveOmit } from "@vueuse/core";
import { normalizeClass } from "vue";
import type { HTMLAttributes } from "vue";
import { twMerge } from "tailwind-merge";

const props = defineProps<TabsTriggerProps & { class?: HTMLAttributes["class"] }>();
const forwarded = reactiveOmit(props, "class");
const baseClass = "inline-flex min-h-control min-w-control items-center justify-center rounded-sm px-3 op-label font-medium text-muted-foreground outline-none transition hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm";
</script>
