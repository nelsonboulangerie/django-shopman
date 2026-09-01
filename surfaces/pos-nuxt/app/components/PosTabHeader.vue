<script setup lang="ts">
// Tab header (Arc 5 · context bar) — the open tab's header, lifted out of the
// ticket panel into the top context bar so the cart keeps its vertical room for
// line items + numpad. Owns the renameable tab number, the customer chip +
// sheet, and "liberar comanda" (with confirmation). It renders
// what the read-side hands it and emits intent; the shell resolves the commands.
import type { POSCustomerLookupProjection, POSCustomerSearchResult } from "~/types/pos";

const props = defineProps<{
  tabDisplay: string;
  hasOpenTab: boolean;
  canRename: boolean;
  customerName: string;
  customerPhone: string;
  customerTaxId: string;
  customerEmail: string;
  customerLookup: POSCustomerLookupProjection | null;
  lookupBusy: boolean;
  searchResults: POSCustomerSearchResult[];
  searchBusy: boolean;
  /** O cliente associado foi criado agora (resolve just-in-time). */
  customerResolvedNew?: boolean;
  /** No checkout a barra vira só LEITURA dos fatos do pedido: liberar a comanda
   *  e renomeá-la no meio de um pagamento é ação que não pertence ali. */
  readOnly?: boolean;
  /** Como o cliente recebe: decidido na abertura, revisto de relance aqui. */
  fulfillmentType: "pickup" | "delivery";
  /** O rótulo já resolvido ("Entrega · Centro"), que a página monta. */
  fulfillmentLabel: string;
  /** Quando o cliente quer o pedido: "Para hoje", "qui, 10/09, 10:00 às 10:30". */
  scheduleLabel: string;
  /** O pedido é para outro dia — muda o ícone e o realce do botão. */
  scheduled: boolean;
  loading: boolean;
}>();

const emit = defineEmits<{
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  rename: [string];
  clear: [];
  clearCustomer: [];
  lookupCustomer: [];
  resolveCustomer: [];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
  openFulfillment: [];
  openSchedule: [];
  /** Só em `readOnly` (checkout): quem tem o modal do cliente ali é a tela de
   *  pagamento — a dela carrega a parte fiscal. Dois modais de Cliente na mesma
   *  tela seria a duplicação que esta barra veio justamente desfazer. */
  openCustomer: [];
}>();

const renaming = ref(false);
const renameValue = ref("");
function startRename() {
  renameValue.value = props.tabDisplay || "";
  renaming.value = true;
}
function confirmRename() {
  const next = renameValue.value.trim();
  renaming.value = false;
  if (next && next !== (props.tabDisplay || "")) emit("rename", next);
}
function cancelRename() {
  renaming.value = false;
}
function onRenameKeydown(event: KeyboardEvent) {
  if (event.key === "Enter") {
    event.preventDefault();
    confirmRename();
  } else if (event.key === "Escape") {
    event.preventDefault();
    cancelRename();
  }
}

// The customer picker is the shared PosCustomerModal (full-screen, picker-first).
const customerSheetOpen = ref(false);
// F6 no shell abre o mesmo modal que o chip de cliente abre.
defineExpose({ openCustomer: () => { customerSheetOpen.value = true; } });
// Foco devolvido ao CONTEXTO quando o modal fecha: o diálogo é controlado (sem
// trigger do reka), então sem isto o foco morria no body.
const customerChipRef = ref<HTMLButtonElement | null>(null);
watch(customerSheetOpen, async (open) => {
  if (open || !import.meta.client) return;
  await nextTick();
  customerChipRef.value?.focus();
});

const confirmClear = ref(false);
function runClear() {
  confirmClear.value = false;
  emit("clear");
}
</script>

<template>
  <div class="flex min-w-0 items-center gap-2">
    <!-- tab number (renameable) -->
    <div v-if="renaming" class="flex items-center gap-1">
      <UiInput
        v-model="renameValue"
        class="h-9 w-40 text-lg font-semibold"
        placeholder="Mesa, nome…"
        autofocus
        @keydown="onRenameKeydown"
      />
      <UiButton variant="ghost" size="icon-sm" aria-label="Confirmar nome" @click="confirmRename">
        <Icon name="lucide:check" class="size-4" />
      </UiButton>
      <UiButton variant="ghost" size="icon-sm" aria-label="Cancelar" @click="cancelRename">
        <Icon name="lucide:x" class="size-4" />
      </UiButton>
    </div>
    <button
      v-else-if="hasOpenTab && canRename && !readOnly"
      type="button"
      class="group flex min-w-0 items-center gap-1.5"
      aria-label="Renomear comanda"
      @click="startRename"
    >
      <h1 class="truncate text-lg font-semibold leading-tight tabular-nums tracking-tight">#{{ tabDisplay || "..." }}</h1>
      <Icon name="lucide:pencil" class="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
    <h1 v-else-if="hasOpenTab" class="truncate text-lg font-semibold leading-tight tabular-nums tracking-tight">#{{ tabDisplay || "..." }}</h1>
    <h1 v-else class="truncate text-lg font-semibold leading-tight tracking-tight">Venda rápida</h1>

    <!-- customer chip -->
    <button
      ref="customerChipRef"
      type="button"
      class="flex h-9 min-w-0 shrink items-center gap-1.5 rounded-full border border-border px-3 text-sm transition hover:bg-accent"
      aria-haspopup="dialog"
      @click="readOnly ? $emit('openCustomer') : (customerSheetOpen = true)"
    >
      <Icon name="lucide:user-round" class="size-4 shrink-0 text-muted-foreground" />
      <span v-if="customerName" class="min-w-0 max-w-40 truncate font-medium">{{ customerName }}</span>
      <span v-else class="shrink-0 text-muted-foreground">Adicionar cliente</span>
    </button>

    <!-- RECEBIMENTO — irmão do chip de cliente. Os dois são fatos do PEDIDO,
         decididos na abertura do atendimento e revistos de relance daqui em
         diante. Na barra eles são LEITURA com porta de saída; o lugar onde se
         decide é o começo do fluxo, não esta barra. -->
    <button
      v-if="hasOpenTab"
      type="button"
      class="flex h-9 min-w-0 shrink items-center gap-1.5 rounded-full border px-3 text-sm transition hover:bg-accent"
      :class="fulfillmentType === 'delivery' ? 'border-primary bg-primary/5' : 'border-border'"
      aria-haspopup="dialog"
      @click="$emit('openFulfillment')"
    >
      <Icon :name="fulfillmentType === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4 shrink-0 text-muted-foreground" />
      <span class="min-w-0 max-w-48 truncate font-medium">{{ fulfillmentLabel }}</span>
    </button>

    <!-- QUANDO — o terceiro irmão. A data morava dentro do formulário de
         ENTREGA, e por isso a retirada agendada não existia: a casa recebe
         encomenda por telefone e o balcão não tinha onde escrever isso.
         "Para hoje" é o padrão e é uma AFIRMAÇÃO, não um campo vazio. -->
    <button
      v-if="hasOpenTab"
      type="button"
      class="flex h-9 min-w-0 shrink items-center gap-1.5 rounded-full border px-3 text-sm transition hover:bg-accent"
      :class="scheduled ? 'border-primary bg-primary/5' : 'border-border'"
      aria-haspopup="dialog"
      @click="$emit('openSchedule')"
    >
      <Icon :name="scheduled ? 'lucide:calendar-clock' : 'lucide:clock'" class="size-4 shrink-0 text-muted-foreground" />
      <span class="min-w-0 max-w-56 truncate font-medium">{{ scheduleLabel }}</span>
    </button>

    <!-- release tab (pushed to the right of the context bar) -->
    <UiButton
      v-if="hasOpenTab && !readOnly"
      variant="ghost"
      size="icon-sm"
      class="ml-auto shrink-0 text-muted-foreground"
      aria-label="Liberar comanda"
      title="Liberar comanda"
      @click="confirmClear = true"
    >
      <Icon name="lucide:x" class="size-4" />
    </UiButton>

    <PosCustomerModal
      v-model:open="customerSheetOpen"
      :customer-name="customerName"
      :customer-phone="customerPhone"
      :customer-tax-id="customerTaxId"
      :customer-email="customerEmail"
      :customer-lookup="customerLookup"
      :search-results="searchResults"
      :search-busy="searchBusy"
      :lookup-busy="lookupBusy"
      :resolved-new="customerResolvedNew"
      @update:customer-name="$emit('update:customerName', $event)"
      @update:customer-phone="$emit('update:customerPhone', $event)"
      @update:customer-tax-id="$emit('update:customerTaxId', $event)"
      @update:customer-email="$emit('update:customerEmail', $event)"
      @search="$emit('search', $event)"
      @select-result="$emit('selectResult', $event)"
      @clear="$emit('clearCustomer')"
      @resolve-customer="$emit('resolveCustomer')"
      @apply-customer-favorite="$emit('applyCustomerFavorite')"
      @repeat-customer-last-order="$emit('repeatCustomerLastOrder')"
    />

    <UiDialog :open="confirmClear" @update:open="(value) => { if (!value) confirmClear = false; }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Liberar comanda?</UiDialogTitle>
          <UiDialogDescription>
            Isso descarta este atendimento e libera a comanda. A ação não pode ser desfeita.
          </UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter class="gap-2">
          <UiButton variant="outline" @click="confirmClear = false">Cancelar</UiButton>
          <UiButton variant="destructive" :disabled="loading" @click="runClear">Liberar comanda</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </div>
</template>
