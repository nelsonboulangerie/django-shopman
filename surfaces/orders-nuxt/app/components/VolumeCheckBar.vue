<script setup lang="ts">
// A faixa da conferência das sacolas (P1-13): o que o leitor do posto Saída
// acabou de bipar. Aparece só quando há conferência ou aviso; some ao encerrar.
// A sacola de outro pedido é o aviso forte, com as duas saídas na cor dele.
// Nada aqui segura a saída do pedido: a conferência só avisa.
import { conferenceLine, type ConferenceState } from "~/presentation/volumeCheck";
import { splitRef } from "~/presentation/board";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

const props = defineProps<{
  state: ConferenceState;
  /** Tela de um pedido só (o detalhe): não oferece trocar de pedido. */
  fixed?: boolean;
}>();
const emit = defineEmits<{
  (e: "switch", ref: string): void;
  (e: "dismiss-alarm" | "end"): void;
}>();

const complete = computed(() => {
  const c = props.state.conference;
  return Boolean(c && c.total && c.checked >= c.total);
});

const alarmActions = computed(() => {
  const alarm = props.state.alarm;
  if (!alarm?.otherRef || props.fixed) return [];
  const other = alarm.otherRef;
  const current = props.state.conference?.ref;
  return [
    { label: `Conferir o ${splitRef(other).code}`, onClick: () => emit("switch", other) },
    current ? { label: `Seguir no ${splitRef(current).code}`, onClick: () => emit("dismiss-alarm") } : null,
  ];
});
</script>

<template>
  <div v-if="state.alarm || state.conference" class="grid gap-2" data-volume-check aria-live="assertive">
    <NuxtAlert
      v-if="state.alarm"
      :color="state.alarm.tone"
      variant="subtle"
      :icon="state.alarm.tone === 'error' ? 'i-lucide-octagon-alert' : 'i-lucide-triangle-alert'"
      :title="state.alarm.message"
      :actions="alertActions(state.alarm.tone, alarmActions)"
      orientation="horizontal"
      close
      :data-volume-alarm="state.alarm.tone"
      @update:open="(open: boolean) => { if (!open) emit('dismiss-alarm'); }"
    />
    <NuxtAlert
      v-if="state.conference"
      :color="complete ? 'success' : 'info'"
      variant="subtle"
      :icon="complete ? 'i-lucide-package-check' : 'i-lucide-scan-barcode'"
      :title="conferenceLine(state.conference)"
      close
      data-volume-conference
      @update:open="(open: boolean) => { if (!open) emit('end'); }"
    />
  </div>
</template>
