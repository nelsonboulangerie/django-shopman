<script setup lang="ts">
import type { ChannelSwitchDraft } from "~/presentation/channelSwitch";
import { rangeLine } from "~/presentation/channelSwitch";

const draft = defineModel<ChannelSwitchDraft>({ required: true });
const line = computed(() => rangeLine(draft.value));
</script>

<template>
  <div class="grid gap-4" data-period-calendar>
    <div class="grid gap-4 sm:grid-cols-2">
      <NuxtFormField label="Data de início">
        <NuxtInput v-model="draft.startDate" class="w-full" type="date" />
      </NuxtFormField>
      <NuxtFormField label="Hora de início">
        <NuxtInput v-model="draft.startTime" class="w-full" type="time" :step="900" />
      </NuxtFormField>
      <NuxtFormField label="Data de término">
        <NuxtInput v-model="draft.endDate" class="w-full" type="date" />
      </NuxtFormField>
      <NuxtFormField label="Hora de término">
        <NuxtInput v-model="draft.endTime" class="w-full" type="time" :step="900" />
      </NuxtFormField>
    </div>
    <NuxtAlert
      v-if="line"
      color="neutral"
      variant="subtle"
      icon="i-lucide-calendar-range"
      :title="line"
      data-period-range
    />
  </div>
</template>
