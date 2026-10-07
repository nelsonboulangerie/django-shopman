<script setup lang="ts">
// O aviso que não espera (decisão do dono, 07/10/2026): quando a causa decide sozinha
// num prazo (a negociação do iFood, por exemplo), a tela para até alguém ver. "Resolver
// agora" leva ao lugar exato; "Visto" registra a ciência e libera a tela, mas o aviso
// volta a lembrar a cada URGENT_REMINDER_MINUTES até a causa acabar ou o prazo vencer.
//
// Lê a mesma fonte da caixa de Avisos (`provideOperatorInboxAlerts`): o app só precisa
// mandar `respondByIso` no item. Sem prazo, nada aqui acontece.
import { useNow } from "@vueuse/core";
import { computed, onBeforeUnmount, onMounted } from "vue";

import { useOperatorInboxAlerts } from "../composables/useSuiteChrome";
import {
  URGENT_REMINDER_MINUTES,
  deadlineLeftLabel,
  urgentAlerts,
} from "../presentation/suiteChrome";

const source = useOperatorInboxAlerts();
const toast = useToast();
const now = useNow({ interval: 1000 });

const view = computed(() =>
  urgentAlerts(source.value?.items ?? [], now.value.getTime()),
);
const blocking = computed(() => view.value.blocking);
const pending = computed(() =>
  blocking.value ? Boolean(source.value?.isPending?.(blocking.value.key)) : false,
);

function clock(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime())
    ? ""
    : at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

async function seen() {
  if (!blocking.value) return;
  await source.value?.ack?.(blocking.value.key);
}
async function resolveNow() {
  const alert = blocking.value;
  if (!alert) return;
  // Ir resolver também é ter visto: sem o Visto, o modal voltaria por cima do
  // lugar onde a pessoa foi resolver.
  await source.value?.ack?.(alert.key);
  if (alert.href) await navigateTo(alert.href);
}

// Lembrete dos já vistos: o primeiro sai um intervalo depois do Visto, e assim por diante.
const nextReminder = new Map<string | number, number>();
let timer: ReturnType<typeof setInterval> | null = null;
function remind() {
  const nowMs = Date.now();
  const reminders = view.value.reminders;
  const live = new Set(reminders.map((alert) => alert.key));
  for (const key of [...nextReminder.keys()])
    if (!live.has(key)) nextReminder.delete(key);
  for (const alert of reminders) {
    const due = nextReminder.get(alert.key);
    if (due === undefined) {
      nextReminder.set(alert.key, nowMs + URGENT_REMINDER_MINUTES * 60_000);
      continue;
    }
    if (nowMs < due) continue;
    nextReminder.set(alert.key, nowMs + URGENT_REMINDER_MINUTES * 60_000);
    toast.add({
      title: `Ainda sem resposta: responder até ${clock(alert.respondByIso!)}`,
      description: alert.message,
      color: "error",
      icon: "i-lucide-alarm-clock",
      duration: 15_000,
      actions: alert.href
        ? [
            {
              label: alert.hrefLabel || "Abrir",
              to: alert.href,
              color: "error",
              variant: "outline",
            },
          ]
        : undefined,
    });
  }
}
onMounted(() => {
  timer = setInterval(remind, 15_000);
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
</script>

<template>
  <NuxtModal
    :open="Boolean(blocking)"
    :dismissible="false"
    :close="false"
    title="Precisa de resposta"
    :description="blocking?.meta"
    data-operator-urgent-alert
  >
    <template #body>
      <div v-if="blocking" class="flex flex-col gap-3">
        <p class="op-body">{{ blocking.message }}</p>
        <NuxtAlert
          color="error"
          variant="subtle"
          icon="i-lucide-alarm-clock"
          :title="deadlineLeftLabel(blocking.respondByIso!, now.getTime())"
          role="timer"
          aria-live="off"
          data-operator-urgent-left
        />
      </div>
    </template>
    <template #footer>
      <div class="grid w-full grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2">
        <NuxtButton
          block
          color="neutral"
          variant="outline"
          label="Visto"
          :disabled="pending || !blocking?.canAck"
          data-operator-urgent-seen
          @click="seen"
        />
        <NuxtButton
          block
          color="primary"
          icon="i-lucide-arrow-right"
          :label="blocking?.hrefLabel || 'Resolver agora'"
          :disabled="pending"
          :loading="pending"
          data-operator-urgent-resolve
          @click="resolveNow"
        />
      </div>
    </template>
  </NuxtModal>
</template>
