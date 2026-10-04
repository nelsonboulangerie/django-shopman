<script setup lang="ts">
// Operator alerts bell — count badge + dropdown panel with per-alert ack. Color is
// functional (severity); the bell itself is neutral chrome. Lives in the board header.
import type { AlertProjection } from "~/types/orders";

// `placement="rail"` (UX-KIT-V1): item "Alertas" no pé do rail da suíte, com o painel à
// direita do rail; o padrão segue sendo o botão do cabeçalho.
const props = withDefaults(defineProps<{ placement?: "header" | "rail" }>(), { placement: "header" });

const { alerts, activeCount, criticalCount, ack, ackAction } = useAlerts();
const open = ref(false);

function contextAction(alert: AlertProjection) {
  return alert.actions?.find((action) => action.kind === "open_alert_context" && action.enabled);
}

function sevChip(sev: AlertProjection["severity"]): string {
  if (sev === "critical" || sev === "error")
    return "border-destructive/40 bg-destructive/10 text-destructive dark:text-orange-300";
  return "border-warning/40 bg-warning/10 text-amber-700 dark:text-amber-300";
}
</script>

<template>
  <div class="relative">
    <RailSection
      v-if="props.placement === 'rail'"
      icon="lucide:triangle-alert"
      label="Alertas"
      :badge="activeCount ? String(activeCount) : ''"
      :aria-label="`Alertas (${activeCount})`"
      :aria-expanded="open"
      title="Alertas"
      data-alerts-trigger
      @activate="open = !open"
    />
    <button
      v-else
      type="button"
      class="relative grid size-control place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground max-md:border-transparent max-md:text-foreground"
      :aria-label="`Alertas (${activeCount})`"
      title="Alertas"
      @click="open = !open"
    >
      <Icon name="lucide:bell" class="size-4" />
      <span
        v-if="activeCount"
        class="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full px-1 text-xs font-bold tabular-nums text-white"
        :class="criticalCount ? 'bg-destructive' : 'bg-warning'"
      >{{ activeCount }}</span>
    </button>

    <!-- backdrop to close on outside click -->
    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />

    <div
      v-if="open"
      class="z-50 flex max-h-[70vh] w-80 flex-col overflow-hidden rounded-lg border bg-card shadow-lg"
      :class="props.placement === 'rail' ? 'fixed bottom-3 left-[84px]' : 'absolute right-0 mt-2'"
    >
      <div class="flex items-center justify-between border-b px-4 py-2.5">
        <h2 class="text-sm font-bold">Alertas</h2>
        <button type="button" class="grid size-7 place-items-center rounded text-muted-foreground transition hover:text-foreground" aria-label="Fechar" @click="open = false">
          <Icon name="lucide:x" class="size-4" />
        </button>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto p-2">
        <div v-if="!alerts.length" class="grid place-items-center gap-1.5 py-8 text-center text-muted-foreground">
          <Icon name="lucide:check-circle-2" class="size-6" />
          <p class="text-sm">Nenhum alerta agora.</p>
        </div>
        <ul v-else class="flex flex-col gap-1.5">
          <li
            v-for="a in alerts"
            :key="a.pk"
            class="flex items-start gap-2 rounded-md border p-2.5"
            :class="[sevChip(a.severity), ackAction(a) ? '' : 'opacity-70']"
            :data-alert-seen="ackAction(a) ? undefined : ''"
          >
            <div class="min-w-0 flex-1">
              <p class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide">
                {{ a.severity_label }} · {{ a.type_label }}
              </p>
              <p class="mt-0.5 whitespace-pre-line break-words text-sm text-foreground">{{ a.message }}</p>
              <p class="mt-0.5 text-xs text-muted-foreground">
                {{ a.created_at_display }}<template v-if="a.order_ref"> · pedido {{ a.order_ref }}</template><template v-if="!ackAction(a)"> · visto</template>
              </p>
              <NuxtLink
                v-if="contextAction(a)"
                :to="contextAction(a)!.href"
                class="mt-2 inline-flex min-h-9 items-center rounded-md border bg-background px-3 text-xs font-semibold text-foreground transition hover:bg-accent"
                @click="open = false"
              >
                {{ contextAction(a)!.label }}
              </NuxtLink>
            </div>
            <button
              v-if="ackAction(a)"
              type="button"
              class="inline-flex min-h-9 shrink-0 items-center gap-1 rounded-md border bg-background px-2 text-xs font-medium text-muted-foreground transition hover:text-foreground"
              aria-label="Marcar como visto"
              title="Marca que você leu. O alerta sai quando o problema for resolvido."
              data-alert-ack
              @click="ack(a)"
            >
              <Icon name="lucide:check" class="size-3.5" /> Visto
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
