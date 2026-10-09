<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";

import { useNotifications } from "../composables/useNotifications";
import { useOperatorAppLink } from "../composables/useOperatorAppLink";
import { useOperatorCapacity } from "../composables/useOperatorCapacity";
import {
  useOperatorInboxAlerts,
  useSharedCapacity,
  type OperatorInboxAlert,
} from "../composables/useSuiteChrome";
import {
  CAPACITY_LEVEL_META,
  capacityGuidance,
  capacityLevel,
  capacitySummary,
} from "../presentation/capacity";
import {
  anomalyLabels,
  isHighlighted,
  signInSummary,
} from "../presentation/notifications";
import {
  inboxAriaLabel,
  inboxBadge,
  inboxTotal,
} from "../presentation/suiteChrome";
import type { UserNotification } from "../types/notification";

const props = withDefaults(
  defineProps<{
    placement?: "rail" | "header";
    /**
     * O item com nome ("Avisos" sob o sino), como as seções do rail de 76 px do
     * `OperatorSuiteRail` (os apps ainda fora do shell). No shell, o sino fica ao lado
     * do menu do operador e o nome mora no `aria-label`.
     */
    labeled?: boolean;
  }>(),
  { placement: "header", labeled: false },
);
const source = useOperatorInboxAlerts();
const {
  items,
  unread,
  markRead,
  signIns,
  loadSignIns,
  error,
  signInError,
  refresh,
} = useNotifications();
const { reading, authorized, stale } = useOperatorCapacity();
const sharedCapacity = useSharedCapacity();
sharedCapacity.value = { reading, authorized, stale };
onBeforeUnmount(() => {
  if (sharedCapacity.value?.reading === reading) sharedCapacity.value = null;
});

const capacity = computed(() =>
  authorized.value ? capacityLevel(reading.value) : "unknown",
);
const capacityAlert = computed(
  () => capacity.value === "critical" || capacity.value === "attention",
);
const capacityCritical = computed(() => capacity.value === "critical");
const alertCount = computed(() => source.value?.count ?? 0);
const total = computed(() =>
  inboxTotal({
    alerts: alertCount.value,
    unread: unread.value,
    capacityCritical: capacityCritical.value,
  }),
);
const badge = computed(() => inboxBadge(total.value));
const label = computed(() => inboxAriaLabel(total.value));
const hasOperation = computed(
  () => Boolean(source.value) || capacityAlert.value,
);
const operationCount = computed(
  () => alertCount.value + (capacityCritical.value ? 1 : 0),
);
const alerts = computed<OperatorInboxAlert[]>(() => source.value?.items ?? []);
// O aviso leva aonde se resolve, às vezes noutro app (o lote na Produção, o pedido no
// Gestor): instalado, o outro app abre na janela dele.
const { attrsFor } = useOperatorAppLink();
function openNotification(item: UserNotification) {
  open.value = false;
  if (!item.is_read) void markRead(item.pk);
}

const open = ref(false);
const tab = ref<"operation" | "personal">("operation");
const personalView = ref<"inbox" | "signIns">("inbox");
function onOpen(next: boolean) {
  open.value = next;
  if (!next) return;
  personalView.value = "inbox";
  tab.value =
    hasOperation.value && (operationCount.value > 0 || unread.value === 0)
      ? "operation"
      : "personal";
}
const tabs = computed(() => [
  {
    value: "operation",
    label: operationCount.value
      ? `${source.value?.title || "Gerais"} · ${operationCount.value}`
      : source.value?.title || "Gerais",
    "data-operator-inbox-tab": "operation",
  },
  {
    value: "personal",
    label: unread.value ? `Para você · ${unread.value}` : "Para você",
    "data-operator-inbox-tab": "personal",
  },
]);
const { run: showSignIns, pending: signInsPending } = usePendingAction(
  async () => {
    personalView.value = "signIns";
    await loadSignIns();
  },
);
const alertColor = (tone: OperatorInboxAlert["tone"]) =>
  tone === "critical"
    ? ("error" as const)
    : tone === "warning"
      ? ("warning" as const)
      : ("info" as const);
</script>

<template>
  <NuxtPopover
    :open="open"
    :content="{
      side: props.placement === 'rail' ? 'right' : 'bottom',
      align: 'end',
    }"
    @update:open="onOpen"
  >
    <RailSection
      v-if="labeled"
      icon="lucide:bell"
      label="Avisos"
      :badge="badge"
      :aria-label="label"
      data-operator-inbox-trigger
      :data-placement="props.placement"
    />
    <NuxtChip
      v-else
      :show="Boolean(badge)"
      color="warning"
      :text="badge"
      size="4xl"
      inset
    >
      <NuxtButton
        color="neutral"
        variant="ghost"
        icon="i-lucide-bell"
        square
        class="suite-page:size-control suite-page:justify-center"
        :aria-label="label"
        data-operator-inbox-trigger
        :data-placement="props.placement"
      />
    </NuxtChip>

    <template #content>
      <div
        class="grid max-h-[min(78dvh,40rem)] w-[23rem] max-w-[calc(100vw-1rem)] gap-3 overflow-y-auto p-3"
        data-operator-inbox-panel
      >
        <div class="flex items-center justify-between gap-2">
          <h2 class="font-semibold">Avisos</h2>
          <NuxtButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-x"
            square
            aria-label="Fechar os avisos"
            @click="open = false"
          />
        </div>

        <NuxtTabs
          v-if="hasOperation"
          v-model="tab"
          :items="tabs"
          :content="false"
          variant="pill"
          aria-label="Caixas de avisos"
        />

        <div
          v-if="hasOperation && tab === 'operation'"
          class="grid gap-2"
          data-operator-inbox-operation
        >
          <NuxtAlert
            v-if="capacityAlert"
            :color="capacityCritical ? 'error' : 'warning'"
            variant="subtle"
            icon="i-lucide-gauge"
            :title="`Capacidade do serviço · ${CAPACITY_LEVEL_META[capacity].label}`"
            :description="`${capacitySummary(reading)} · ${capacityGuidance(capacity, reading?.thresholds ?? null)}`"
            data-operator-inbox-capacity
          />
          <NuxtAlert
            v-for="alert in alerts"
            :key="alert.key"
            :color="alertColor(alert.tone)"
            :variant="alert.seen ? 'subtle' : 'soft'"
            :title="alert.eyebrow || undefined"
            :description="`${alert.message}${alert.meta ? ` · ${alert.meta}` : ''}${alert.seen ? ' · visto' : ''}`"
            :data-alert-seen="alert.seen ? '' : undefined"
            data-operator-inbox-alert
          >
            <template #actions>
              <NuxtButton
                v-if="alert.href"
                class="min-w-0 basis-0 flex-[2]"
                :to="alert.href"
                :color="alertColor(alert.tone)"
                variant="outline"
                trailing-icon="i-lucide-arrow-right"
                :label="alert.hrefLabel || 'Abrir'"
                :target="attrsFor(alert.href).target"
                :rel="attrsFor(alert.href).rel"
                data-alert-open
                @click="open = false"
              />
              <NuxtButton
                v-if="alert.canAck && source?.ack"
                class="min-w-0 basis-0 flex-1"
                :color="alertColor(alert.tone)"
                variant="outline"
                icon="i-lucide-check"
                label="Visto"
                :disabled="source?.isPending?.(alert.key)"
                :loading="source?.isPending?.(alert.key)"
                aria-label="Marcar como visto"
                title="Marca que você leu. O alerta sai quando o problema for resolvido."
                data-alert-ack
                @click="source?.ack?.(alert.key)"
              />
            </template>
          </NuxtAlert>
          <NuxtEmpty
            v-if="!alerts.length && !capacityAlert"
            icon="i-lucide-check-circle-2"
            :title="source?.emptyText || 'Nenhum alerta agora'"
          />
        </div>

        <div v-else-if="personalView === 'inbox'" class="grid gap-2">
          <NuxtAlert v-if="error" color="error" variant="subtle" :title="error">
            <template #actions
              ><NuxtButton
                color="error"
                variant="outline"
                label="Atualizar avisos"
                @click="refresh"
            /></template>
          </NuxtAlert>
          <NuxtEmpty
            v-if="!items.length && !error"
            icon="i-lucide-bell-off"
            title="Nada por aqui"
          />
          <NuxtAlert
            v-for="item in items"
            :key="item.pk"
            :color="isHighlighted(item) ? 'warning' : 'neutral'"
            variant="subtle"
            :icon="
              isHighlighted(item) ? 'i-lucide-alert-triangle' : 'i-lucide-bell'
            "
            :title="item.title"
            :description="`${item.message} · ${item.created_at_display}`"
            data-notification-item
            :data-highlight="isHighlighted(item) ? 'true' : undefined"
          >
            <template #actions>
              <NuxtButton
                v-if="item.action_url && item.action_label"
                :to="item.action_url"
                :color="isHighlighted(item) ? 'warning' : 'neutral'"
                variant="outline"
                trailing-icon="i-lucide-arrow-right"
                :label="item.action_label"
                :target="attrsFor(item.action_url).target"
                :rel="attrsFor(item.action_url).rel"
                data-notification-open
                @click="openNotification(item)"
              />
              <NuxtButton
                v-if="!item.is_read"
                :color="isHighlighted(item) ? 'warning' : 'neutral'"
                variant="outline"
                label="Marcar como lida"
                @click="markRead(item.pk)"
              />
            </template>
          </NuxtAlert>
          <span
            v-for="item in items"
            :key="`a11y-${item.pk}`"
            class="sr-only"
            >{{ anomalyLabels(item).join("; ") }}</span
          >
          <NuxtButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-history"
            label="Meus acessos"
            :loading="signInsPending"
            data-see-sign-ins
            @click="showSignIns"
          />
        </div>

        <div v-else class="grid gap-2">
          <NuxtButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-arrow-left"
            label="Avisos"
            @click="personalView = 'inbox'"
          />
          <NuxtAlert
            v-if="signInError"
            color="error"
            variant="subtle"
            :title="signInError"
          >
            <template #actions
              ><NuxtButton
                color="error"
                variant="outline"
                label="Atualizar acessos"
                @click="loadSignIns"
            /></template>
          </NuxtAlert>
          <NuxtEmpty
            v-if="!signIns.length && !signInError"
            icon="i-lucide-history"
            title="Nenhum acesso registrado"
          />
          <NuxtAlert
            v-for="entry in signIns"
            :key="entry.pk"
            :color="entry.highlight ? 'warning' : 'neutral'"
            variant="subtle"
            :title="signInSummary(entry)"
            :description="
              [entry.created_at_display, ...entry.anomaly_labels].join(' · ')
            "
            data-sign-in-item
            :data-highlight="entry.highlight ? 'true' : undefined"
          />
        </div>
      </div>
    </template>
  </NuxtPopover>
</template>
