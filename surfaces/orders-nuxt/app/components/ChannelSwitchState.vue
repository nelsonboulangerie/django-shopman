<script setup lang="ts">
// O estado do toggle "Ativo", no corpo do card: o que fecha o canal AGORA (o
// horário da loja prevalece sobre o toggle) e a trilha do último gesto — quem,
// quando, por quê, até quando —, mais o agendamento que ainda vem. Estado normal
// (ligado, loja aberta, sem gesto) não diz nada.
import type { ChannelSwitchProjection } from "~/types/feeds";

defineProps<{ sw: ChannelSwitchProjection }>();
</script>

<template>
  <div v-if="sw.closed_by_shop || sw.state_line || sw.scheduled_line" class="flex flex-col gap-1" data-switch-state>
    <p v-if="sw.closed_by_shop" class="flex items-center gap-1.5 text-sm font-medium text-amber-700 dark:text-amber-300" data-switch-closed-by-shop>
      <Icon name="lucide:clock" class="size-3.5 shrink-0" />
      {{ sw.closed_by_shop }}
    </p>
    <p v-if="sw.state_line" class="text-xs text-muted-foreground" data-switch-trail>{{ sw.state_line }}</p>
    <p v-if="sw.scheduled_line" class="flex items-center gap-1.5 text-xs text-muted-foreground" data-switch-scheduled>
      <Icon name="lucide:calendar-clock" class="size-3.5 shrink-0" />
      {{ sw.scheduled_line }}
    </p>
  </div>
</template>
