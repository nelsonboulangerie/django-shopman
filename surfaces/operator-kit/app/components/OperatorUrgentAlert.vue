<script setup lang="ts">
// O aviso que não espera (decisão do dono, 07/10/2026): quando a causa tem prazo, a tela
// para até alguém ver. "Resolver" leva ao lugar exato; "Visto" registra a ciência e
// libera a tela, e o aviso volta num ritmo proporcional ao que falta
// (`reminderIntervalMs`, dono, 08/10/2026) até a causa acabar.
//
// Lê num relance, sempre na mesma ordem (dono, 08/10/2026): de onde vem, o assunto,
// quanto falta, o detalhe e o que fazer. Origem e assunto vêm do servidor por tipo
// (`alert_specs`); o detalhe é a mensagem de cada aviso.
//
// Lê a mesma fonte da caixa de Avisos (`provideOperatorInboxAlerts`): o app só precisa
// mandar `respondByIso` no item. Sem prazo, nada aqui acontece.
import { useNow } from "@vueuse/core";
import { computed, onBeforeUnmount, onMounted } from "vue";

import { useOperatorInboxAlerts } from "../composables/useSuiteChrome";
import {
  reminderIntervalMs,
  respondInLabel,
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
const overdue = computed(() =>
  blocking.value
    ? Date.parse(blocking.value.respondByIso!) <= now.value.getTime()
    : false,
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
  await source.value?.ack?.(alert.key);
  if (alert.href) await navigateTo(alert.href);
}

const nextReminder = new Map<string | number, number>();
let timer: ReturnType<typeof setInterval> | null = null;
function remind() {
  const nowMs = Date.now();
  const reminders = view.value.reminders;
  const live = new Set(reminders.map((alert) => alert.key));
  for (const key of [...nextReminder.keys()])
    if (!live.has(key)) nextReminder.delete(key);
  for (const alert of reminders) {
    const left = Date.parse(alert.respondByIso!) - nowMs;
    const due = nextReminder.get(alert.key);
    if (due === undefined) {
      nextReminder.set(alert.key, nowMs + reminderIntervalMs(left));
      continue;
    }
    if (nowMs < due) continue;
    nextReminder.set(alert.key, nowMs + reminderIntervalMs(left));
    toast.add({
      title: [alert.origin, alert.subject].filter(Boolean).join(" · ") || "Aviso com prazo",
      description: `${respondInLabel(alert.respondByIso!, nowMs)} · até ${clock(alert.respondByIso!)}`,
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
    :title="blocking?.subject || blocking?.eyebrow || 'Aviso com prazo'"
    data-operator-urgent-alert
  >
    <!-- 1 origem · 2 assunto: o que é, antes de quanto falta. -->
    <template #header>
      <div v-if="blocking" class="flex min-w-0 flex-col gap-1">
        <p
          v-if="blocking.origin"
          class="flex items-center gap-1.5 op-label text-muted-foreground"
          data-operator-urgent-origin
        >
          <Icon
            v-if="blocking.originIcon"
            :name="blocking.originIcon"
            class="size-4 shrink-0"
          />
          {{ blocking.origin }}
        </p>
        <h2 class="text-lg font-semibold text-highlighted" data-operator-urgent-subject>
          {{ blocking.subject || blocking.eyebrow }}
        </h2>
      </div>
    </template>
    <!-- 3 prazo, contado ao vivo · 4 o detalhe. -->
    <template #body>
      <div v-if="blocking" class="flex flex-col gap-2">
        <p
          class="flex items-center gap-2 font-semibold text-error"
          role="timer"
          aria-live="off"
          data-operator-urgent-left
          :data-overdue="overdue || undefined"
        >
          <Icon name="i-lucide-alarm-clock" class="size-5 shrink-0" />
          {{ respondInLabel(blocking.respondByIso!, now.getTime()) }}
          <span class="font-normal text-muted-foreground"
            >· até {{ clock(blocking.respondByIso!) }}</span
          >
        </p>
        <p class="op-body whitespace-pre-line" data-operator-urgent-message>
          {{ blocking.message }}
        </p>
      </div>
    </template>
    <!-- 5 o que fazer. -->
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
