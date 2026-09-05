<script setup lang="ts">
// FILIPETAS — o pedido remoto virando papel para o painel de parede.
//
// Por que esta tela mora no PDV e não no Gestor: a filipeta é PAPEL, e o papel
// só existe onde estão a bobina e o agente do balcão. O `useCounterAgent` lê a
// sua configuração de `POSProjection.cash_drawer` (`agent_url` + `token`), que
// é identidade de ESTAÇÃO — o Gestor não tem nenhuma, e dar uma a ele é
// trabalho de identidade de estação, não de filipeta. Quem imprime a semana
// está no balcão, em frente à impressora. A permissão, porém, é a do pedido
// (`shop.manage_orders`, que o grupo Caixa já tem), porque o documento é do
// pedido e não do caixa.
import {
  PRESET_LABELS,
  activePreset,
  batchNotice,
  fulfillmentIcon,
  groupByDate,
  printCtaLabel,
  rangeLabel,
  ticketCountLabel,
  type TicketPreset,
} from "~/presentation/orderTickets";

useHead({ title: "Filipetas · PDV" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();
const { operator: activeOperator, lock } = useOperatorLock("cashman.operate_pos");

const tickets = usePosOrderTickets(pos);

const presets = Object.keys(PRESET_LABELS) as TicketPreset[];
const current = computed(() => activePreset(tickets.range.value, tickets.today));
const groups = computed(() => groupByDate(tickets.rows.value, tickets.today));
const notice = computed(() => batchNotice(tickets.count.value, tickets.maxBatch.value));

const NOTICE_CLASS: Record<string, string> = {
  neutral: "border-border bg-muted/40 text-muted-foreground",
  warning: "border-warning/30 bg-warning/10 text-warning",
  danger: "border-destructive/30 bg-destructive/10 text-destructive",
};

async function goToSaleBoard() {
  await navigateTo("/");
}

async function goToCashSession() {
  await navigateTo("/session");
}
</script>

<template>
  <main class="flex flex-wrap content-start min-h-dvh bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-nowrap md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="posPending"
      view="tickets"
      @board="goToSaleBoard"
      @cash="goToCashSession"
      @tickets="tickets.refresh()"
      @lock="lock()"
      @refresh="refreshPos()"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
        <RailToggle />
        <h1 class="min-w-0 truncate text-lg font-semibold leading-tight tracking-tight">Filipetas</h1>
        <span class="ml-auto truncate text-sm text-muted-foreground">
          {{ rangeLabel(tickets.range.value, tickets.today) }}
        </span>
      </header>

      <div class="flex-1 md:min-h-0 md:overflow-y-auto">
        <div class="mx-auto grid w-full max-w-3xl gap-4 p-4 md:py-8">
          <p class="text-sm text-muted-foreground">
            Comprovante do pedido remoto — entrega, retirada ou encomenda — para pendurar no painel.
            Não é nota fiscal e não comprova pagamento; o papel diz isso.
          </p>

          <!-- INTERVALO: os atalhos que a casa pede, e as duas datas para o resto. -->
          <section class="grid gap-3 rounded-md border border-border bg-card p-4">
            <div class="flex flex-wrap gap-2">
              <UiButton
                v-for="preset in presets"
                :key="preset"
                size="sm"
                :variant="current === preset ? 'outline' : 'ghost'"
                :class="current === preset ? 'border-primary bg-primary/5 text-foreground' : ''"
                @click="tickets.setPreset(preset)"
              >
                {{ PRESET_LABELS[preset] }}
              </UiButton>
            </div>

            <div class="flex flex-wrap items-end gap-3">
              <label class="grid gap-1 text-sm">
                <span class="text-muted-foreground">De</span>
                <UiInput
                  type="date"
                  class="h-11"
                  :model-value="tickets.range.value.date_from"
                  @update:model-value="(value: string) => tickets.setRange({ date_from: value })"
                />
              </label>
              <label class="grid gap-1 text-sm">
                <span class="text-muted-foreground">Até</span>
                <UiInput
                  type="date"
                  class="h-11"
                  :model-value="tickets.range.value.date_to"
                  @update:model-value="(value: string) => tickets.setRange({ date_to: value })"
                />
              </label>
              <UiButton
                variant="ghost"
                size="icon"
                aria-label="Atualizar a conferência"
                :disabled="tickets.pending.value"
                @click="tickets.refresh()"
              >
                <Icon name="lucide:refresh-cw" class="size-5" />
              </UiButton>
            </div>
          </section>

          <!-- ⚠️ QUANTAS VÃO SAIR, antes do gesto. Ninguém quer descobrir na bobina. -->
          <section
            v-if="notice"
            class="flex items-start gap-2 rounded-md border p-3 text-sm"
            :class="NOTICE_CLASS[notice.tone]"
          >
            <Icon
              :name="notice.tone === 'neutral' ? 'lucide:info' : 'lucide:triangle-alert'"
              class="mt-0.5 size-4 shrink-0"
            />
            <p>{{ notice.message }}</p>
          </section>

          <!-- Sem impressora a tela não esconde o botão: ela diz por quê. -->
          <section
            v-if="!tickets.hasPrinter.value"
            class="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground"
          >
            <Icon name="lucide:printer-off" class="mt-0.5 size-4 shrink-0" />
            <p>
              {{ tickets.printerUnavailableReason.value }}
              As filipetas saem no balcão que tem impressora.
            </p>
          </section>

          <UiButton
            size="lg"
            class="w-full"
            :disabled="!tickets.canPrint.value || tickets.printing.value"
            :loading="tickets.printing.value"
            @click="tickets.printBatch()"
          >
            <Icon name="lucide:printer" class="size-5" />
            {{ printCtaLabel(tickets.count.value) }}
          </UiButton>

          <!-- A CONFERÊNCIA, agrupada por dia, na ordem em que o papel vai sair. -->
          <section v-if="tickets.pending.value" class="p-4 text-sm text-muted-foreground">
            Carregando os pedidos do intervalo…
          </section>

          <section
            v-else-if="!tickets.count.value"
            class="grid justify-items-center gap-2 rounded-md border border-dashed border-border p-8 text-center"
          >
            <Icon name="lucide:calendar-x" class="size-6 text-muted-foreground" />
            <p class="text-sm text-muted-foreground">
              {{ ticketCountLabel(0) }} para {{ rangeLabel(tickets.range.value, tickets.today) }}.
            </p>
          </section>

          <section v-for="group in groups" v-else :key="group.date" class="grid gap-2">
            <h2 class="text-sm font-semibold text-muted-foreground">
              {{ group.date_label }} · {{ ticketCountLabel(group.rows.length) }}
            </h2>
            <ul class="grid gap-2">
              <li
                v-for="row in group.rows"
                :key="row.ref"
                class="flex items-center gap-3 rounded-md border border-border bg-card p-3"
              >
                <Icon :name="fulfillmentIcon(row.fulfillment_type)" class="size-5 shrink-0 text-muted-foreground" />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-medium">
                    {{ row.customer_name || row.ref }}
                  </p>
                  <p class="truncate text-xs text-muted-foreground">
                    {{ row.ref }} · {{ row.fulfillment_label }}
                    <template v-if="row.window_label"> · {{ row.window_label }}</template>
                  </p>
                </div>
                <span
                  v-if="row.already_printed"
                  class="shrink-0 rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground"
                >
                  2ª via
                </span>
                <UiButton
                  variant="ghost"
                  size="icon-sm"
                  :aria-label="`Imprimir a filipeta de ${row.ref}`"
                  :disabled="tickets.printingRef.value === row.ref"
                  :loading="tickets.printingRef.value === row.ref"
                  @click="tickets.printOne(row.ref)"
                >
                  <Icon name="lucide:printer" class="size-4" />
                </UiButton>
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  </main>
</template>
