<script setup lang="ts">
import type { ChannelSwitchDraft } from "~/presentation/channelSwitch";
import { rangeLine } from "~/presentation/channelSwitch";

const draft = defineModel<ChannelSwitchDraft>({ required: true });
const line = computed(() => rangeLine(draft.value));
</script>

<template>
  <div class="grid gap-4" data-period-calendar>
    <!-- Período em dois campos, não quatro: as datas num intervalo só e o horário
         noutro, com os componentes de data e hora da suíte (brief #1529). O seletor
         nativo do sistema (`type="date|time"`) não é canônico. Um por linha: lado a
         lado, o intervalo de datas cortava. Sem ponta aberta: "Sem prazo" já é opção. -->
    <div class="grid gap-4">
      <NuxtFormField label="Datas">
        <UiDateRangeField
          :model-value="{ start: draft.startDate, end: draft.endDate }"
          label="Datas do período"
          :allow-open-ended="false"
          @update:model-value="
            (range) => {
              draft.startDate = range.start;
              draft.endDate = range.end;
            }
          "
        />
      </NuxtFormField>
      <NuxtFormField label="Horário">
        <UiTimeRangeField
          :model-value="{ start: draft.startTime, end: draft.endTime }"
          label="Horário de início e de término"
          :minute-step="15"
          @update:model-value="
            (range) => {
              draft.startTime = range.start;
              draft.endTime = range.end;
            }
          "
        />
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
