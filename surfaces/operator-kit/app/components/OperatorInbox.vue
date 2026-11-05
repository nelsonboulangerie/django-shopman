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
  canReportNotMe,
  inboxLayout,
  isHighlighted,
  routineSignInsLabel,
  signInSummary,
} from "../presentation/notifications";
import {
  inboxAlertDescription,
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
  settled,
  markRead,
  signIns,
  loadSignIns,
  error,
  signInError,
  refresh,
  markAllRead,
  notMe,
} = useNotifications();
const confirm = useConfirm();
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
// Sem a primeira leitura da caixa pessoal, o número seria só o da operação e pularia
// logo depois (beta 05/11, MKT-22): espera a soma inteira.
const badge = computed(() => (settled.value ? inboxBadge(total.value) : ""));
const label = computed(() => inboxAriaLabel(settled.value ? total.value : 0));
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

// A caixa pessoal na ordem de quem lê: operação primeiro, acessos de rotina numa linha
// só quando são muitos (beta 05/11, CEN-01).
const layout = computed(() => inboxLayout(items.value));
const routineOpen = ref(false);
const visibleItems = computed(() => [
  ...layout.value.operation,
  ...layout.value.signIns,
  ...(routineOpen.value ? layout.value.routine : []),
]);
const { run: readAll, pending: readAllPending } = usePendingAction(() => markAllRead());

// "Não fui eu": o servidor descreve o que vai acontecer, a pessoa confirma, e só então
// as sessões da conta caem (a ação mora no backend desde sempre; faltava o botão).
const { run: reportNotMe, pending: notMePending } = usePendingAction(async (item: UserNotification) => {
  const first = await notMe(item.pk, false);
  if (first === "done" || first === "failed") return;
  const ok = await confirm({
    title: "Encerrar os acessos da sua conta?",
    description: first.needsConfirmation,
    confirmLabel: "Encerrar os acessos",
    cancelLabel: "Manter os acessos",
  });
  if (!ok) return;
  if ((await notMe(item.pk, true)) === "done") {
    useSonner.success("Acessos encerrados. Nos outros dispositivos, entre de novo.");
  }
});

const open = ref(false);
const tab = ref<"operation" | "personal">("operation");
const personalView = ref<"inbox" | "signIns">("inbox");
function onOpen(next: boolean) {
  open.value = next;
  if (!next) return;
  personalView.value = "inbox";
  routineOpen.value = false;
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
            :description="inboxAlertDescription(alert)"
            :ui="{ description: 'whitespace-pre-line' }"
            :data-alert-seen="alert.seen ? '' : undefined"
            data-operator-inbox-alert
          >
            <template #actions>
              <!-- O gesto que resolve ali mesmo (P2-19: "Aceitar" no pedido parado).
                   Com ele à vista, ele é o sólido, numa linha só dele, e embaixo ficam
                   "Abrir" (contorno) e "Visto", com os rótulos inteiros. -->
              <template v-if="alert.actLabel && source?.act">
                <NuxtButton
                  class="min-w-0 basis-full justify-center"
                  :color="alertColor(alert.tone)"
                  variant="solid"
                  :label="alert.actLabel"
                  :disabled="source?.isPending?.(alert.key)"
                  :loading="source?.isPending?.(alert.key)"
                  data-alert-act
                  @click="source?.act?.(alert.key)"
                />
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
              </template>
              <NuxtButton
                v-else-if="alert.href"
                class="min-w-0 basis-0 flex-[2]"
                :to="alert.href"
                :color="alertColor(alert.tone)"
                variant="solid"
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
                :loading="source?.isPending?.(alert.key) && !(alert.actLabel && source?.act)"
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
                variant="solid"
                label="Atualizar avisos"
                @click="refresh"
            /></template>
          </NuxtAlert>
          <NuxtEmpty
            v-if="!items.length && !error"
            icon="i-lucide-bell-off"
            title="Nada por aqui"
          />
          <NuxtButton
            v-if="unread > 0"
            class="justify-self-end"
            color="neutral"
            variant="ghost"
            icon="i-lucide-check-check"
            label="Marcar todas como lidas"
            :loading="readAllPending"
            data-notifications-read-all
            @click="readAll()"
          />
          <NuxtAlert
            v-for="item in visibleItems"
            :key="item.pk"
            :color="isHighlighted(item) ? 'warning' : 'neutral'"
            variant="subtle"
            :icon="
              isHighlighted(item) ? 'i-lucide-alert-triangle' : 'i-lucide-bell'
            "
            :title="item.title"
            :description="`${item.message} · ${item.created_at_display}`"
            :ui="{ description: 'whitespace-pre-line' }"
            data-notification-item
            :data-highlight="isHighlighted(item) ? 'true' : undefined"
          >
            <template #actions>
              <NuxtButton
                v-if="item.action_url && item.action_label"
                :to="item.action_url"
                :color="isHighlighted(item) ? 'warning' : 'neutral'"
                variant="solid"
                trailing-icon="i-lucide-arrow-right"
                :label="item.action_label"
                :target="attrsFor(item.action_url).target"
                :rel="attrsFor(item.action_url).rel"
                data-notification-open
                @click="openNotification(item)"
              />
              <!-- Acesso destacado: "Não fui eu" é a ação principal (cheia); no de rotina,
                   contorno. Dois botões porque a variante de ação de Alert é literal
                   (trava `canonicalPilot.guardrails` do Gestor) e a cor repete a do
                   aviso (trava `guardrails.alertActions` do kit). -->
              <NuxtButton
                v-if="canReportNotMe(item) && isHighlighted(item)"
                :color="isHighlighted(item) ? 'warning' : 'neutral'"
                variant="solid"
                label="Não fui eu"
                :loading="notMePending"
                :disabled="notMePending"
                data-notification-not-me
                @click="reportNotMe(item)"
              />
              <NuxtButton
                v-else-if="canReportNotMe(item)"
                :color="isHighlighted(item) ? 'warning' : 'neutral'"
                variant="outline"
                label="Não fui eu"
                :loading="notMePending"
                :disabled="notMePending"
                data-notification-not-me
                @click="reportNotMe(item)"
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
          <NuxtButton
            v-if="layout.routine.length"
            block
            class="justify-start"
            color="neutral"
            variant="outline"
            :icon="routineOpen ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
            :label="routineSignInsLabel(layout.routine.length)"
            :aria-expanded="routineOpen"
            data-notifications-routine
            @click="routineOpen = !routineOpen"
          />
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
                variant="solid"
                label="Atualizar acessos"
                @click="loadSignIns"
            /></template>
          </NuxtAlert>
          <!-- Lendo, a lista não está vazia: está chegando (beta 05/11, CEN-13). -->
          <NuxtEmpty
            v-if="signInsPending && !signIns.length"
            loading
            title="Carregando seus acessos"
          />
          <NuxtEmpty
            v-else-if="!signIns.length && !signInError"
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
