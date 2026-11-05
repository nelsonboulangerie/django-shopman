<script setup lang="ts">
// O selo da suíte. Mesmo nome, mesmas props e mesmos slots do `NuxtBadge` do Nuxt UI
// (a camada do kit tem prioridade sobre a do módulo): os apps escrevem `<NuxtBadge>`
// como sempre, e o texto sai com iniciais maiúsculas (presentation/badgeCase.ts).
import type { BadgeProps, BadgeSlots } from "@nuxt/ui";
import CanonicalBadge from "@nuxt/ui/components/Badge.vue";
import { computed, type FunctionalComponent } from "vue";

import { badgeCase, badgeCaseNodes } from "../presentation/badgeCase";

const props = defineProps<BadgeProps>();
defineSlots<BadgeSlots>();

const forwarded = computed(() => ({
  ...props,
  label: typeof props.label === "string" ? badgeCase(props.label) : props.label,
}));

const Cased: FunctionalComponent = (_, { slots }) => badgeCaseNodes(slots.default?.() ?? []);
</script>

<template>
  <CanonicalBadge v-bind="forwarded">
    <template v-if="$slots.leading" #leading="scope"><slot name="leading" v-bind="scope" /></template>
    <template v-if="$slots.default" #default="scope"
      ><Cased><slot v-bind="scope" /></Cased
    ></template>
    <template v-if="$slots.trailing" #trailing="scope"><slot name="trailing" v-bind="scope" /></template>
  </CanonicalBadge>
</template>
