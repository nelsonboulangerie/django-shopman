<script setup lang="ts">
// Operator alerts bell — count badge + dropdown panel with per-alert ack. Color is
// functional (severity); the bell itself is neutral chrome. Lives in the board header.
// A ação contextual vem resolvida pelo backend; o sino não inventa rota nem
// decide se reconhecer encerra o perigo.
import type {
  AlertAckActionProjection,
  AlertContextActionProjection,
  AlertProjection,
} from "~/types/production";

const { alerts, activeCount, criticalCount, ack, isPending } = useAlerts();
const open = ref(false);
const router = useRouter();

function sevChip(sev: AlertProjection["severity"]): string {
  if (sev === "critical" || sev === "error")
    return "border-destructive/40 bg-destructive/10 text-destructive";
  return "border-warning/40 bg-warning/10 text-warning";
}

function contextAction(
  alert: AlertProjection,
): AlertContextActionProjection | null {
  return (
    alert.actions.find(
      (action): action is AlertContextActionProjection =>
        action.kind === "open_alert_context" && action.enabled,
    ) ?? null
  );
}

function ackAction(alert: AlertProjection): AlertAckActionProjection | null {
  return (
    alert.actions.find(
      (action): action is AlertAckActionProjection =>
        action.kind === "acknowledge_alert" && action.enabled,
    ) ?? null
  );
}

function follow(alert: AlertProjection) {
  const action = contextAction(alert);
  if (!action) return;
  open.value = false;
  router.push(action.href);
}
</script>

<template>
  <div class="relative">
    <UiButton
      type="button"
      class="relative"
      variant="outline"
      size="icon"
      :aria-label="`Alertas (${activeCount})`"
      title="Alertas"
      @click="open = !open"
    >
      <Icon name="lucide:bell" class="size-4" />
      <span
        v-if="activeCount"
        class="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full px-1 text-xs font-bold tabular-nums"
        :class="
          criticalCount
            ? 'bg-destructive text-destructive-foreground'
            : 'bg-warning text-warning-foreground'
        "
        >{{ activeCount }}</span
      >
    </UiButton>

    <!-- backdrop to close on outside click -->
    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />

    <div
      v-if="open"
      class="absolute right-0 z-50 mt-2 flex max-h-[70vh] w-80 flex-col overflow-hidden rounded-md border bg-card shadow-lg"
    >
      <div class="flex items-center justify-between border-b px-4 py-2.5">
        <h2 class="text-sm font-bold">Alertas</h2>
        <UiButton
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Fechar"
          @click="open = false"
        >
          <Icon name="lucide:x" class="size-4" />
        </UiButton>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto p-2">
        <div
          v-if="!alerts.length"
          class="grid place-items-center gap-1.5 py-8 text-center text-muted-foreground"
        >
          <Icon name="lucide:check-circle-2" class="size-6" />
          <p class="text-sm">Nenhum alerta agora.</p>
        </div>
        <ul v-else class="flex flex-col gap-1.5">
          <li
            v-for="a in alerts"
            :key="a.pk"
            class="flex items-start gap-2 rounded-md border p-2.5"
            :class="sevChip(a.severity)"
          >
            <component
              :is="contextAction(a) ? 'button' : 'div'"
              class="min-w-0 flex-1 text-left"
              v-bind="
                contextAction(a)
                  ? { type: 'button', 'aria-label': contextAction(a)?.label }
                  : {}
              "
              @click="follow(a)"
            >
              <p
                class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide"
              >
                {{ a.severity_label }} · {{ a.type_label }}
                <Icon
                  v-if="contextAction(a)"
                  name="lucide:arrow-up-right"
                  class="size-3"
                />
              </p>
              <p class="mt-0.5 break-words text-sm text-foreground">
                {{ a.message }}
              </p>
              <p class="mt-0.5 text-xs text-muted-foreground">
                {{ a.created_at_display
                }}<template v-if="a.order_ref"> · {{ a.order_ref }}</template>
              </p>
            </component>
            <UiButton
              v-if="ackAction(a)"
              type="button"
              class="shrink-0"
              variant="outline"
              size="icon"
              aria-label="Marcar alerta como visto"
              title="Visto"
              :disabled="isPending(a.pk)"
              @click="ack(a)"
            >
              <Icon name="lucide:check" class="size-3.5" />
            </UiButton>
            <div
              v-else
              class="grid size-11 shrink-0 place-items-center rounded-md border bg-background text-muted-foreground"
              aria-label="Alerta visto; permanece aberto até resolução"
              title="Visto; aguardando resolução"
            >
              <Icon name="lucide:eye" class="size-3.5" />
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
