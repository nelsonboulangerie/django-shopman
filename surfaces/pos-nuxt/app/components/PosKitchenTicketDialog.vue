<script setup lang="ts">
// O card do ticket da cozinha, no PDV: o balcão vê o que a estação tem da
// linha — estação, itens, hora do disparo, estado — no mesmo desenho do card do
// KDS. Quando a estação NÃO tem tela (recebe a Via Cozinha impressa), o balcão
// é uma das três portas da baixa (decisão do dono, 26/09/2026): o card traz
// "Pronto", a mesma ação e a mesma régua de servidor da Saída.
//
// A atualização depois do pronto vem sozinha: o ticket salvo avisa o balcão
// pelo canal `tabs` (ADR-016), e o selo da linha vira "Pronto".
import type { POSKitchenTicket, POSKitchenTicketReceipt } from "~/types/pos";

const props = defineProps<{
  open: boolean;
  /** O nome da linha tocada, para o título dizer de onde o card veio. */
  lineName: string;
  tickets: POSKitchenTicket[];
}>();
const emit = defineEmits<{ "update:open": [boolean] }>();

const { call } = usePosAction();
const busy = ref<Set<number>>(new Set());
/** Concluídos por este diálogo, até o push trazer o estado novo. */
const doneHere = ref<Set<number>>(new Set());

function statusOf(ticket: POSKitchenTicket): string {
  return doneHere.value.has(ticket.pk) ? "Pronto" : ticket.status_label;
}
function canReady(ticket: POSKitchenTicket): boolean {
  return ticket.can_mark_ready && !doneHere.value.has(ticket.pk);
}

async function markReady(ticket: POSKitchenTicket) {
  if (busy.value.has(ticket.pk)) return;
  busy.value = new Set(busy.value).add(ticket.pk);
  try {
    const response = await call<{ ticket: POSKitchenTicketReceipt }>(
      `/api/v1/backstage/kds/printed-tickets/${ticket.pk}/done/`,
      { method: "POST" },
    );
    doneHere.value = new Set(doneHere.value).add(ticket.pk);
    if (response.ticket.completed_now) useSonner.success(response.ticket.message);
    else useSonner.info(response.ticket.message);
  } catch (error) {
    useSonner.error(httpErrorMessage(error, "Não deu para marcar como pronto. Tente de novo."));
  } finally {
    const next = new Set(busy.value);
    next.delete(ticket.pk);
    busy.value = next;
  }
}

watch(
  () => props.open,
  (open) => { if (!open) doneHere.value = new Set(); },
);
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle class="text-lg">Na cozinha</UiDialogTitle>
        <UiDialogDescription>{{ lineName }}</UiDialogDescription>
      </UiDialogHeader>
      <ul class="flex flex-col gap-3">
        <li
          v-for="ticket in tickets"
          :key="ticket.pk"
          class="flex flex-col gap-2.5 rounded-md border bg-card p-4"
          data-testid="pos-kitchen-ticket"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate text-lg font-bold leading-tight">{{ ticket.station_name }}</p>
              <p class="text-sm text-muted-foreground">
                enviado às {{ ticket.fired_at_display }}<template v-if="ticket.prints && ticket.paper_label">
                  · {{ ticket.paper_label }}</template
                >
              </p>
            </div>
            <span
              class="shrink-0 rounded-md border px-2.5 py-1 text-sm font-semibold"
              :class="statusOf(ticket) === 'Pronto' ? 'border-success/40 bg-success/10 text-success' : ''"
            >
              {{ statusOf(ticket) }}
            </span>
          </div>
          <p
            v-if="ticket.prints && ticket.paper_failed"
            class="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
          >
            O papel não saiu na impressora desta estação. Avise a estação.
          </p>
          <ul class="space-y-1 border-t pt-2.5">
            <li v-for="(item, idx) in ticket.items" :key="idx" class="text-sm">
              <span class="font-bold tabular-nums">{{ item.qty }}×</span>{{ " " }}<span class="font-medium">{{ item.name }}</span>
              <span v-if="item.notes" class="block pl-6 text-xs font-semibold">{{ item.notes }}</span>
            </li>
          </ul>
          <UiButton
            v-if="canReady(ticket)"
            class="h-11 w-full text-base"
            :disabled="busy.has(ticket.pk)"
            @click="markReady(ticket)"
          >
            <Icon name="lucide:check" class="size-5" />
            Pronto
          </UiButton>
          <p v-else-if="!ticket.prints && statusOf(ticket) !== 'Pronto'" class="text-xs text-muted-foreground">
            {{ ticket.station_name }} tem tela: o pronto é dado lá.
          </p>
        </li>
      </ul>
    </UiDialogContent>
  </UiDialog>
</template>
