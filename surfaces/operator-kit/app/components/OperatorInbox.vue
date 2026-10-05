<script setup lang="ts">
// "Avisos": UMA caixa por app, UM item no rail, UM sino no celular (V6-KIT, K01/T-01).
//
// A prévia v4 (`_rail3bottom.html`, `gestor-fila4.html`, `cozinha-celular4.html`) tem um
// item só, "Avisos", com um selo. O real tinha dois no Gestor (Alertas e Avisos), só
// "Alertas" na Produção e nenhum no Marketing. Ter duas fontes de dado não obriga dois
// ícones: esta peça junta, num painel, o que pede a operação (os alertas que o app
// registra com `provideOperatorInboxAlerts`, e a capacidade do serviço quando passa do
// crítico) e a caixa PESSOAL (avisos de acesso, "Meus acessos"). Duas abas, um selo
// somado. Nenhuma função saiu: "Visto", "abrir o lugar exato", "Marcar como lida" e o
// log de acessos seguem aqui.
//
// ⚠️ **Não interrompe.** Contador discreto e lista consultável: sem modal, sem som, sem
// roubo de foco. ⚠️ **Realce, nunca silo.** O aviso suspeito fica na MESMA lista,
// marcado.
//
// O painel abre num portal (K05): fora do `<aside>` do rail, ele não herda o creme do
// texto do rail (o título sumia) e fica por cima da fila (o cadeado do cartão
// atravessava o painel).
import { computed, onBeforeUnmount, ref } from "vue";
import { PopoverClose, PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

import { useNotifications } from "../composables/useNotifications";
import { useOperatorCapacity } from "../composables/useOperatorCapacity";
import { useOperatorInboxAlerts, useSharedCapacity, type OperatorInboxAlert } from "../composables/useSuiteChrome";
import {
  CAPACITY_LEVEL_META,
  capacityGuidance,
  capacityLevel,
  capacitySummary,
} from "../presentation/capacity";
import { anomalyLabels, isHighlighted, signInSummary } from "../presentation/notifications";
import { inboxAriaLabel, inboxBadge, inboxTotal } from "../presentation/suiteChrome";

const props = withDefaults(defineProps<{
  /**
   * `rail`: o item "Avisos" no pé do rail da suíte, painel à direita.
   * `header`: o sino da barra de 56px (celular e tablet em pé), painel abaixo.
   */
  placement?: "rail" | "header";
}>(), { placement: "header" });

const source = useOperatorInboxAlerts();
const { items, unread, markRead, signIns, loadSignIns, error, signInError, refresh } = useNotifications();
const { reading, authorized, stale } = useOperatorCapacity();
// Publica a leitura para o menu do operador (uma leitura por tela, não duas).
const sharedCapacity = useSharedCapacity();
sharedCapacity.value = { reading, authorized, stale };
onBeforeUnmount(() => {
  if (sharedCapacity.value?.reading === reading) sharedCapacity.value = null;
});

const capacity = computed(() => (authorized.value ? capacityLevel(reading.value) : "unknown"));
// A capacidade só entra na caixa quando passa do limite: abaixo dele, ela mora no menu
// do operador (as iniciais), escrita, sem ponto vermelho permanente no rail.
const capacityAlert = computed(() => capacity.value === "critical" || capacity.value === "attention");
const capacityCritical = computed(() => capacity.value === "critical");

const alertCount = computed(() => source.value?.count ?? 0);
const total = computed(() => inboxTotal({ alerts: alertCount.value, unread: unread.value, capacityCritical: capacityCritical.value }));
const badge = computed(() => inboxBadge(total.value));
const label = computed(() => inboxAriaLabel(total.value));

/** Há aba da operação: o app registrou alertas, ou a capacidade passou do limite. */
const hasOperation = computed(() => Boolean(source.value) || capacityAlert.value);
const operationCount = computed(() => alertCount.value + (capacityCritical.value ? 1 : 0));
const alerts = computed<OperatorInboxAlert[]>(() => source.value?.items ?? []);

const open = ref(false);
const tab = ref<"operation" | "personal">("operation");
// Duas vistas na aba pessoal: a caixa e o log de acessos. O log não tem página
// própria, e mandar a pessoa para o Admin noutro domínio não é "conferir sempre que
// quiser"; então ele mora aqui.
const personalView = ref<"inbox" | "signIns">("inbox");

function onOpen(next: boolean) {
  open.value = next;
  if (!next) return;
  personalView.value = "inbox";
  // Abre na aba que tem o que fazer: a operação primeiro, se ela pede algo.
  tab.value = hasOperation.value && (operationCount.value > 0 || unread.value === 0) ? "operation" : "personal";
}

const { run: showSignIns, pending: signInsPending } = usePendingAction(async () => {
  personalView.value = "signIns";
  await loadSignIns();
});

const TONE_CLASS: Record<OperatorInboxAlert["tone"], string> = {
  critical: "border-destructive/40 bg-destructive/8",
  warning: "border-warning/40 bg-warning/10",
  info: "border-border bg-muted/40",
};
const TONE_TEXT: Record<OperatorInboxAlert["tone"], string> = {
  critical: "text-destructive",
  warning: "text-warning",
  info: "text-muted-foreground",
};
</script>

<template>
  <PopoverRoot :open="open" @update:open="onOpen">
    <PopoverTrigger as-child>
      <RailSection
        v-if="props.placement === 'rail'"
        icon="lucide:bell"
        label="Avisos"
        :badge="badge"
        :aria-label="label"
        data-operator-inbox-trigger
        data-placement="rail"
      />
      <button
        v-else
        type="button"
        class="relative grid size-11 shrink-0 place-items-center rounded-md text-foreground transition hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:size-12"
        :aria-label="label"
        data-operator-inbox-trigger
        data-placement="header"
      >
        <Icon name="lucide:bell" class="size-6" aria-hidden="true" />
        <span
          v-if="badge"
          aria-hidden="true"
          class="absolute top-1 right-0.5 h-[18px] min-w-[18px] rounded-full bg-suite-badge px-[5px] text-[11px] leading-[18px] font-bold tabular-nums text-suite-badge-foreground"
          data-operator-inbox-count
        >{{ badge }}</span>
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        :side="props.placement === 'rail' ? 'right' : 'bottom'"
        align="end"
        :side-offset="8"
        :collision-padding="8"
        class="z-[60] flex max-h-[min(78dvh,40rem)] w-[23rem] max-w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-lg outline-hidden"
        data-operator-inbox-panel
      >
        <div class="flex items-center gap-2 border-b border-border py-2 pr-2 pl-4">
          <h2 class="op-title flex-1">Avisos</h2>
          <PopoverClose
            class="grid size-10 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
            aria-label="Fechar os avisos"
          >
            <Icon name="lucide:x" class="size-5" aria-hidden="true" />
          </PopoverClose>
        </div>

        <!-- Duas abas, um painel: o que a operação pede e o que é seu. -->
        <div
          v-if="hasOperation"
          class="mx-3 mt-3 grid grid-cols-2 gap-1 rounded-lg bg-secondary p-1"
          role="tablist"
          aria-label="Caixas de avisos"
        >
          <button
            type="button"
            role="tab"
            class="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-md px-2 op-label font-semibold transition"
            :class="tab === 'operation' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
            :aria-selected="tab === 'operation'"
            data-operator-inbox-tab="operation"
            @click="tab = 'operation'"
          >
            {{ source?.title || "Da operação" }}
            <span v-if="operationCount" class="tnum">{{ operationCount }}</span>
          </button>
          <button
            type="button"
            role="tab"
            class="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-md px-2 op-label font-semibold transition"
            :class="tab === 'personal' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
            :aria-selected="tab === 'personal'"
            data-operator-inbox-tab="personal"
            @click="tab = 'personal'"
          >
            Para você
            <span v-if="unread" class="tnum">{{ unread }}</span>
          </button>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-3" role="tabpanel">
          <!-- Da operação -->
          <template v-if="hasOperation && tab === 'operation'">
            <ul class="flex flex-col gap-1.5" data-operator-inbox-operation>
              <li
                v-if="capacityAlert"
                class="rounded-lg border p-2.5"
                :class="capacityCritical ? TONE_CLASS.critical : TONE_CLASS.warning"
                data-operator-inbox-capacity
              >
                <p class="op-micro font-semibold" :class="capacityCritical ? TONE_TEXT.critical : TONE_TEXT.warning">
                  Capacidade do serviço · {{ CAPACITY_LEVEL_META[capacity].label }}
                </p>
                <p class="mt-0.5 op-body tnum">{{ capacitySummary(reading) }}</p>
                <p class="mt-0.5 op-micro text-muted-foreground">{{ capacityGuidance(capacity, reading?.thresholds ?? null) }}</p>
              </li>
              <li
                v-for="alert in alerts"
                :key="alert.key"
                class="flex items-start gap-2 rounded-lg border p-2.5"
                :class="[TONE_CLASS[alert.tone], alert.seen ? 'opacity-75' : '']"
                :data-alert-seen="alert.seen ? '' : undefined"
                data-operator-inbox-alert
              >
                <div class="min-w-0 flex-1">
                  <p v-if="alert.eyebrow" class="op-micro font-semibold" :class="TONE_TEXT[alert.tone]">{{ alert.eyebrow }}</p>
                  <p class="mt-0.5 op-body whitespace-pre-line break-words text-foreground">{{ alert.message }}</p>
                  <p v-if="alert.meta || alert.seen" class="mt-0.5 op-micro text-muted-foreground">
                    {{ alert.meta }}<template v-if="alert.seen"><template v-if="alert.meta"> · </template>visto</template>
                  </p>
                  <NuxtLink
                    v-if="alert.href"
                    :to="alert.href"
                    class="mt-2 inline-flex min-h-10 items-center gap-1.5 rounded-md border border-border bg-card px-3 op-label font-semibold text-foreground transition hover:bg-accent"
                    @click="open = false"
                  >
                    {{ alert.hrefLabel || "Abrir" }}
                    <Icon name="lucide:arrow-right" class="size-4" aria-hidden="true" />
                  </NuxtLink>
                </div>
                <button
                  v-if="alert.canAck && source?.ack"
                  type="button"
                  class="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-md border border-border bg-card px-2.5 op-label font-medium text-muted-foreground transition hover:text-foreground disabled:opacity-60"
                  :disabled="source?.isPending?.(alert.key)"
                  :aria-busy="source?.isPending?.(alert.key) || undefined"
                  aria-label="Marcar como visto"
                  title="Marca que você leu. O alerta sai quando o problema for resolvido."
                  data-alert-ack
                  @click="source?.ack?.(alert.key)"
                >
                  <Icon name="lucide:check" class="size-4" aria-hidden="true" /> Visto
                </button>
              </li>
            </ul>
            <div
              v-if="!alerts.length && !capacityAlert"
              class="grid place-items-center gap-1.5 py-8 text-center text-muted-foreground"
            >
              <Icon name="lucide:check-circle-2" class="size-6" aria-hidden="true" />
              <p class="op-body">{{ source?.emptyText || "Nenhum alerta agora." }}</p>
            </div>
          </template>

          <!-- Para você: a caixa pessoal -->
          <template v-else-if="personalView === 'inbox'">
            <div v-if="error" role="status" class="px-1 py-2 op-body text-muted-foreground">
              <p>{{ error }}</p>
              <button type="button" class="underline" @click="refresh">Atualizar avisos</button>
            </div>
            <p v-if="!items.length && !error" class="px-1 py-6 text-center op-body text-muted-foreground">
              Nada por aqui.
            </p>
            <ul v-else class="flex flex-col gap-1.5">
              <li
                v-for="item in items"
                :key="item.pk"
                data-notification-item
                :data-highlight="isHighlighted(item) ? 'true' : undefined"
                class="rounded-lg border p-2.5"
                :class="isHighlighted(item) ? 'border-warning/40 bg-warning/10' : 'border-border'"
              >
                <div class="flex items-start gap-2">
                  <Icon
                    v-if="isHighlighted(item)"
                    name="lucide:alert-triangle"
                    class="mt-0.5 size-4 shrink-0 text-warning"
                  />
                  <div class="min-w-0 flex-1">
                    <p class="op-body font-medium text-foreground" :class="{ 'text-muted-foreground': item.is_read }">
                      {{ item.title }}
                    </p>
                    <p class="whitespace-pre-line op-micro text-muted-foreground">{{ item.message }}</p>
                    <p v-if="anomalyLabels(item).length" class="sr-only">Acesso destacado.</p>
                    <div class="mt-1 flex items-center gap-2">
                      <span class="op-micro text-muted-foreground">{{ item.created_at_display }}</span>
                      <button
                        v-if="!item.is_read"
                        type="button"
                        class="op-micro text-muted-foreground underline-offset-2 hover:underline"
                        @click="markRead(item.pk)"
                      >
                        Marcar como lida
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            </ul>
            <button
              type="button"
              data-see-sign-ins
              class="mt-2 inline-flex min-h-10 w-full items-center justify-center gap-1.5 rounded-lg op-body text-muted-foreground hover:bg-accent hover:text-foreground"
              :disabled="signInsPending"
              @click="showSignIns"
            >
              <Icon name="lucide:history" class="size-4" aria-hidden="true" /> Meus acessos
            </button>
          </template>

          <template v-else>
            <button
              type="button"
              class="mb-1 inline-flex min-h-10 items-center gap-1.5 rounded-lg px-1 op-body text-muted-foreground hover:text-foreground"
              @click="personalView = 'inbox'"
            >
              <Icon name="lucide:arrow-left" class="size-4" aria-hidden="true" /> Avisos
            </button>
            <div v-if="signInError" role="status" class="px-1 py-2 op-body text-muted-foreground">
              <p>{{ signInError }}</p>
              <button type="button" class="underline" @click="loadSignIns">Atualizar acessos</button>
            </div>
            <p v-if="!signIns.length && !signInError" class="px-1 py-6 text-center op-body text-muted-foreground">
              Nenhum acesso registrado.
            </p>
            <ul v-else class="flex flex-col gap-1.5">
              <li
                v-for="entry in signIns"
                :key="entry.pk"
                data-sign-in-item
                :data-highlight="entry.highlight ? 'true' : undefined"
                class="rounded-lg border p-2.5"
                :class="entry.highlight ? 'border-warning/40 bg-warning/10' : 'border-border'"
              >
                <p class="op-body font-medium text-foreground">{{ signInSummary(entry) }}</p>
                <p class="op-micro text-muted-foreground">{{ entry.created_at_display }}</p>
                <p v-if="entry.anomaly_labels.length" class="op-micro text-warning">
                  {{ entry.anomaly_labels.join("; ") }}
                </p>
              </li>
            </ul>
          </template>
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
