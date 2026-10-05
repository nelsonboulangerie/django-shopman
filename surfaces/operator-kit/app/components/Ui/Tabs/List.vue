<template>
  <TabsList
    data-slot="tabs-list"
    v-bind="forwarded"
    :class="twMerge(baseClass, normalizeClass(props.class))"
  >
    <slot />
  </TabsList>
</template>

<script lang="ts" setup>
import { TabsList } from "reka-ui";
import type { TabsListProps } from "reka-ui";
import { reactiveOmit } from "@vueuse/core";
import { normalizeClass } from "vue";
import type { HTMLAttributes } from "vue";
import { twMerge } from "tailwind-merge";

const props = defineProps<TabsListProps & { class?: HTMLAttributes["class"] }>();
const forwarded = reactiveOmit(props, "class");
const baseClass = "inline-flex min-h-control items-center gap-1 rounded-md border border-border bg-muted/40 p-1";
</script>
