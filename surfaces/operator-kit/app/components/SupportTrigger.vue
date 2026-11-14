<script setup lang="ts">
import { ref } from "vue";

import type { OperatorFitSize } from "../presentation/actionLabel";
import OperatorButton from "./OperatorButton.vue";
import SupportPanel from "./SupportPanel.vue";

withDefaults(
  defineProps<{
    context?: Record<string, unknown>;
    label?: string;
    shortLabel?: string;
    size?: OperatorFitSize;
    variant?: "solid" | "outline" | "soft" | "subtle" | "ghost" | "link";
    color?: "primary" | "success" | "info" | "warning" | "error" | "neutral";
    block?: boolean;
  }>(),
  {
    context: () => ({}),
    label: "Preciso de ajuda",
    shortLabel: "Ajuda",
    size: "md",
    variant: "soft",
    color: "neutral",
    block: false,
  },
);

const open = ref(false);
</script>

<template>
  <span class="inline-flex">
    <OperatorButton
      :label="label"
      :short-label="shortLabel"
      icon="i-lucide-life-buoy"
      :size="size"
      :variant="variant"
      :color="color"
      :block="block"
      @click="open = true"
    />
    <SupportPanel v-model:open="open" :context="context" />
  </span>
</template>
