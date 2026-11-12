<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { useSupport } from "../composables/useSupport";
import OperatorButton from "./OperatorButton.vue";
import OperatorScreenState from "./OperatorScreenState.vue";

import {
  SUPPORT_FILTERS,
  SUPPORT_PRIORITY_LABELS,
  SUPPORT_TYPE_LABELS,
  canDecide,
  canLinkDev,
  canReply,
  canTriage,
  contextRows,
  filterTickets,
  formatAge,
  priorityLabel,
  statusColor,
  statusLabel,
  ticketTitle,
  typeLabel,
  type SupportFilter,
} from "../presentation/support";
import type { SupportDecisionKind, SupportPriority, SupportType } from "../types/support";

const props = withDefaults(
  defineProps<{
    open: boolean;
    context?: Record<string, unknown>;
  }>(),
  { context: () => ({}) },
);

const emit = defineEmits<{ "update:open": [value: boolean] }>();

const isOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit("update:open", value),
});

const {
  tickets,
  ticket,
  capabilities,
  pending,
  error,
  load,
  select,
  create,
  reply,
  triage,
  decide,
  linkDev,
  clear,
} = useSupport();

const now = ref(Date.now());
let clock: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  clock = setInterval(() => (now.value = Date.now()), 60_000);
});
onBeforeUnmount(() => {
  if (clock) clearInterval(clock);
});

const filter = ref<SupportFilter>("all");
const visibleTickets = computed(() => filterTickets(tickets.value, filter.value));

const newOpen = ref(false);
const newDescription = ref("");
const newType = ref<SupportType>("question");

const replyBody = ref("");
const internalNote = ref(false);

const decisionMode = ref<"" | "reject" | "defer">("");
const decisionReason = ref("");
const decisionDate = ref("");

const devRef = ref("");
const triageType = ref<SupportType>("question");
const triagePriority = ref<SupportPriority>("normal");

const typeItems = Object.entries(SUPPORT_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const priorityItems = Object.entries(SUPPORT_PRIORITY_LABELS).map(([value, label]) => ({ value, label }));

watch(
  () => props.open,
  (open) => {
    if (open) {
      void load();
    } else {
      clear();
      newOpen.value = false;
    }
  },
);

watch(ticket, (value) => {
  if (value) {
    triageType.value = value.type;
    triagePriority.value = value.priority;
    decisionMode.value = "";
    decisionReason.value = "";
  }
});

function openTicket(ref: string): void {
  void select(ref);
}

async function submitNew(): Promise<void> {
  const description = newDescription.value.trim();
  if (!description) return;
  const created = await create({ description, type: newType.value, context: props.context });
  if (created) {
    newDescription.value = "";
    newOpen.value = false;
  }
}

async function send(): Promise<void> {
  if (!ticket.value) return;
  const body = replyBody.value.trim();
  if (!body) return;
  if (await reply(ticket.value.ref, body, internalNote.value)) {
    replyBody.value = "";
    internalNote.value = false;
  }
}

async function runTriage(): Promise<void> {
  if (!ticket.value) return;
  await triage(ticket.value.ref, { type: triageType.value, priority: triagePriority.value });
}

async function approve(): Promise<void> {
  if (!ticket.value) return;
  await decide(ticket.value.ref, "approve", "aprovado pelo dono");
}

async function submitDecision(): Promise<void> {
  if (!ticket.value || !decisionMode.value) return;
  const kind = decisionMode.value as SupportDecisionKind;
  const ok = await decide(
    ticket.value.ref,
    kind,
    decisionReason.value.trim(),
    kind === "defer" ? decisionDate.value : undefined,
  );
  if (ok) {
    decisionMode.value = "";
    decisionReason.value = "";
    decisionDate.value = "";
  }
}

async function submitDev(): Promise<void> {
  if (!ticket.value) return;
  const ref = devRef.value.trim();
  if (!ref) return;
  if (await linkDev(ticket.value.ref, ref)) devRef.value = "";
}
</script>

<template>
  <NuxtModal v-model:open="isOpen" title="Suporte">
    <template #body>
      <div class="flex max-h-[75vh] flex-col gap-4 overflow-y-auto" data-support-panel>
        <p v-if="error" class="rounded bg-error/10 px-3 py-2 text-sm text-error" role="alert" data-support-error>
          {{ error }}
        </p>

        <div v-if="ticket" class="flex flex-col gap-4" data-support-ticket>
          <div class="flex items-center gap-2">
            <OperatorButton
              label="Voltar"
              icon="i-lucide-arrow-left"
              variant="ghost"
              size="sm"
              @click="clear()"
            />
            <NuxtBadge :color="statusColor(ticket.status)" :label="statusLabel(ticket.status)" size="sm" />
            <span class="text-xs text-muted">{{ ticket.ref }}</span>
            <span class="ml-auto text-xs text-muted">{{ formatAge(ticket.created_at, now) }}</span>
          </div>

          <div>
            <h3 class="text-lg font-semibold">{{ ticketTitle(ticket) }}</h3>
            <p class="text-xs text-muted">
              {{ typeLabel(ticket.type) }} · {{ priorityLabel(ticket.priority) }} ·
              {{ ticket.requester }} ({{ ticket.requester_role }})
            </p>
            <p v-if="ticket.ledger_ref" class="mt-1 text-xs text-muted">
              Compromisso: {{ ticket.ledger_ref }}
            </p>
          </div>

          <details v-if="contextRows(ticket.context).length" class="rounded border border-default p-3">
            <summary class="cursor-pointer text-sm font-medium">Contexto do chamado</summary>
            <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <template v-for="row in contextRows(ticket.context)" :key="row.label">
                <dt class="text-muted">{{ row.label }}</dt>
                <dd class="break-words">{{ row.value }}</dd>
              </template>
            </dl>
          </details>

          <div class="flex flex-col gap-3" data-support-thread>
            <article
              v-for="message in ticket.messages"
              :key="message.id"
              class="rounded-lg border border-default p-3"
              :class="message.internal_note ? 'bg-warning/10' : 'bg-elevated/40'"
            >
              <div class="flex items-center gap-2 text-xs text-muted">
                <span>{{ message.author || "Sistema" }}</span>
                <span v-if="message.internal_note" class="font-medium text-warning">Nota interna</span>
                <span class="ml-auto">{{ formatAge(message.created_at, now) }}</span>
              </div>
              <p class="mt-1 whitespace-pre-line text-sm">{{ message.body }}</p>
            </article>
            <p v-if="!ticket.messages.length" class="text-sm text-muted">Sem mensagens ainda.</p>
          </div>

          <div v-if="ticket.decisions.length" class="rounded border border-default p-3">
            <h4 class="text-sm font-medium">Decisões</h4>
            <ul class="mt-2 flex flex-col gap-1 text-xs">
              <li v-for="decision in ticket.decisions" :key="decision.id">
                <span class="font-medium">{{ decision.decided_by }}</span>
                {{ decision.decision === "approve" ? "aprovou" : decision.decision === "reject" ? "recusou" : "adiou" }}
                <span v-if="decision.reason">: {{ decision.reason }}</span>
              </li>
            </ul>
          </div>

          <section v-if="canTriage(ticket, capabilities)" class="flex flex-col gap-2 rounded border border-default p-3">
            <h4 class="text-sm font-medium">Triagem</h4>
            <div class="flex flex-wrap items-center gap-2">
              <NuxtSelect v-model="triageType" :items="typeItems" value-key="value" label-key="label" size="sm" class="min-w-40" />
              <NuxtSelect v-model="triagePriority" :items="priorityItems" value-key="value" label-key="label" size="sm" class="min-w-32" />
              <OperatorButton label="Triar" size="sm" :loading="pending" @click="runTriage" />
            </div>
          </section>

          <section v-if="canDecide(ticket, capabilities)" class="flex flex-col gap-2 rounded border border-default p-3">
            <h4 class="text-sm font-medium">Decisão do dono</h4>
            <div class="flex flex-wrap gap-2">
              <OperatorButton label="Aprovar" size="sm" color="success" :loading="pending" @click="approve" />
              <OperatorButton label="Recusar" size="sm" variant="outline" @click="decisionMode = 'reject'" />
              <OperatorButton label="Adiar" size="sm" variant="outline" @click="decisionMode = 'defer'" />
            </div>
            <div v-if="decisionMode" class="flex flex-col gap-2">
              <NuxtTextarea
                v-model="decisionReason"
                :rows="2"
                :placeholder="decisionMode === 'reject' ? 'Motivo da recusa' : 'Motivo do adiamento'"
              />
              <NuxtInput v-if="decisionMode === 'defer'" v-model="decisionDate" type="date" size="sm" />
              <OperatorButton label="Confirmar" size="sm" :loading="pending" @click="submitDecision" />
            </div>
          </section>

          <section v-if="canLinkDev(ticket, capabilities)" class="flex flex-col gap-2 rounded border border-default p-3">
            <h4 class="text-sm font-medium">Compromisso de dev</h4>
            <div class="flex flex-wrap items-center gap-2">
              <NuxtInput v-model="devRef" placeholder="DEV-2026-010" size="sm" class="min-w-40" />
              <OperatorButton label="Ligar" size="sm" :loading="pending" @click="submitDev" />
            </div>
            <p class="text-xs text-muted">O PR cita o compromisso no corpo.</p>
          </section>

          <form v-if="canReply(ticket)" class="flex flex-col gap-2" @submit.prevent="send">
            <NuxtTextarea v-model="replyBody" :rows="3" placeholder="Escreva uma mensagem" />
            <div class="flex items-center justify-between gap-2">
              <NuxtCheckbox v-if="capabilities.triage" v-model="internalNote" label="Nota interna" />
              <OperatorButton
                type="submit"
                label="Enviar"
                icon="i-lucide-send"
                size="sm"
                :loading="pending"
                :disabled="!replyBody.trim()"
              />
            </div>
          </form>
        </div>

        <div v-else class="flex flex-col gap-4" data-support-list>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap gap-1">
              <NuxtButton
                v-for="item in SUPPORT_FILTERS"
                :key="item.id"
                size="xs"
                :variant="filter === item.id ? 'solid' : 'soft'"
                :color="filter === item.id ? 'primary' : 'neutral'"
                @click="filter = item.id"
              >
                {{ item.label }}
              </NuxtButton>
            </div>
            <OperatorButton label="Novo chamado" icon="i-lucide-plus" size="sm" @click="newOpen = !newOpen" />
          </div>

          <form v-if="newOpen" class="flex flex-col gap-2 rounded border border-default p-3" @submit.prevent="submitNew">
            <NuxtSelect v-model="newType" :items="typeItems" value-key="value" label-key="label" size="sm" />
            <NuxtTextarea
              v-model="newDescription"
              :rows="4"
              placeholder="O que aconteceu? O contexto da tela já vai junto."
            />
            <OperatorButton
              type="submit"
              label="Abrir chamado"
              size="sm"
              :loading="pending"
              :disabled="!newDescription.trim()"
            />
          </form>

          <OperatorScreenState
            v-if="!pending && !visibleTickets.length"
            state="empty"
            icon="i-lucide-life-buoy"
            title="Nenhum chamado."
            description="Abra um chamado quando precisar de ajuda."
          />

          <ul v-else class="flex flex-col divide-y divide-default">
            <li v-for="item in visibleTickets" :key="item.ref">
              <NuxtButton
                variant="ghost"
                block
                class="w-full justify-start px-0 py-2 text-left"
                @click="openTicket(item.ref)"
              >
                <span class="flex w-full flex-col gap-1">
                  <span class="flex w-full items-center gap-2">
                    <NuxtBadge :color="statusColor(item.status)" :label="statusLabel(item.status)" size="sm" />
                    <span class="text-xs text-muted">{{ typeLabel(item.type) }} · {{ item.ref }}</span>
                    <span class="ml-auto text-xs text-muted">{{ formatAge(item.created_at, now) }}</span>
                  </span>
                  <span class="text-sm font-medium">{{ ticketTitle(item) }}</span>
                  <span class="text-xs text-muted">{{ item.requester }} · {{ priorityLabel(item.priority) }}</span>
                </span>
              </NuxtButton>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </NuxtModal>
</template>
