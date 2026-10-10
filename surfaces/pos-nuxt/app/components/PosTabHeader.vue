<script setup lang="ts">
// Tab header (Arc 5 · context bar) — the open tab's header, lifted out of the
// ticket panel into the top context bar so the cart keeps its vertical room for
// line items + numpad. Owns the renameable tab number, the customer chip +
// sheet, and "liberar comanda" (with confirmation). It renders
// what the read-side hands it and emits intent; the shell resolves the commands.
import type { POSCustomerLookupProjection, POSCustomerSearchResult, POSSeatingSpotOption } from "~/types/pos";
import type { CustomerDecision, ServerConflictCandidate } from "~/presentation/customerDecision";
import { tabTitleView } from "~/presentation/tabTitle";

const props = defineProps<{
  salesMode?: "counter" | "order";
  tabDisplay: string;
  /** O número da comanda ("1007"); vira o "#1007" pequeno quando ela tem nome. */
  tabNumber?: string;
  /** Hora em que a comanda abriu ("21:48"), lida no tablet ("aberta 21:48"). */
  openedAt?: string;
  /** As mesas do Salão de hoje: ao renomear, escolher uma com um toque (vínculo
   *  OPCIONAL comanda × mesa, dono 04/10/2026). */
  seatingSpots?: POSSeatingSpotOption[];
  /** A mesa vinculada a esta comanda ("" = sem mesa). */
  seatingSpotRef?: string;
  /** Mesas já com outra comanda aberta (não se escolhe a mesma duas vezes). */
  occupiedSpotRefs?: string[];
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
  /** Rascunho dos padrões do cliente NOVO — mora no shell, o modal só lê. */
  newCustomerPrefs?: { cpf_na_nota?: boolean; email_receipt?: boolean };
  /** A escolha pendente do operador (conflito/correção de contato). */
  customerDecision?: CustomerDecision | null;
  customerMergeBusy?: boolean;
  customerReleaseBusy?: boolean;
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
  /** Há linha JÁ DISPARADA para a cozinha nesta comanda. Liberar a comanda
   *  cancela os tickets no KDS (`clear_pos_tab` → `cancel_tickets_for_session`),
   *  e o aviso precisa dizer isso: quem lê "descarta este atendimento" pensa em
   *  apagar itens de uma tela, e o que acontece é um ticket sumindo do fogão
   *  com alguém de mão na massa. */
  hasFiredItems?: boolean;
  /** O horário escolhido virou impossível (item lançado depois da escolha). */
  scheduleConflict?: boolean;
  scheduleConflictReason?: string;
  /** A encomenda exige um cliente e ainda não há nenhum. O chip PULSA em vez de
   *  a tela abrir mais um aviso: o lugar de identificar o cliente já está na
   *  barra, visível o tempo todo — o que faltava era ele CHAMAR. */
  customerRequired?: boolean;
  /** O cliente não troca aqui (edição de encomenda): o chip só LÊ, e esta é a
   *  frase do porquê, que sobe no toque em vez de abrir o modal. */
  customerLockedReason?: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  salesModeChange: ["counter" | "order"];
  /** Novo nome; e, quando veio de uma mesa tocada, o ref dela ("" = sem mesa). */
  rename: [name: string, seatingSpotRef?: string];
  clear: [];
  clearCustomer: [];
  lookupCustomer: [];
  resolveCustomer: [done: (saved: boolean) => void];
  decisionConfirm: [ownerRef?: string];
  decisionCancel: [];
  decisionMerge: [candidate?: ServerConflictCandidate];
  /** LIBERAR o contato preso num cadastro desativado. */
  decisionRelease: [value: string];
  decisionPick: [ServerConflictCandidate];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
  /** Um padrão do cliente virado no modal: vale nesta venda, na hora. */
  applyPreference: [key: "cpf_na_nota" | "email_receipt", value: boolean];
  openFulfillment: [];
  openSchedule: [];
  /** Só em `readOnly` (checkout): quem tem o modal do cliente ali é a tela de
   *  pagamento — a dela carrega a parte fiscal. Dois modais de Cliente na mesma
   *  tela seria a duplicação que esta barra veio justamente desfazer. */
  openCustomer: [];
  customerClosed: [];
  /** Toque no chip com o cliente travado (`customerLockedReason`). */
  customerLocked: [reason: string];
}>();

const SALES_MODES = [
  { ref: "counter", label: "Balcão", icon: "lucide:store" },
  { ref: "order", label: "Encomendas", icon: "lucide:calendar-clock" },
] as const;

// "Mesa 6" grande e "#1007" pequeno (v4): o nome é como a mesa chama, o número é
// a referência do balcão e do cupom. Sem nome próprio, o número é o título.
const title = computed(() => tabTitleView(props.tabDisplay, props.tabNumber || ""));
// Toque não tem teclado: nenhuma tecla impressa (SPEC4 §7).
const coarsePointer = useMediaQuery("(pointer: coarse)");
// O tamanho dos controles da barra no conjunto mínimo: `md` no mouse, `xl` no toque.
const controlSize = computed(() => (coarsePointer.value ? "xl" : "md"));
const isCounter = computed(() => (props.salesMode || "counter") === "counter");
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
/** Tocar a mesa dá à comanda o nome dela e o vínculo, num gesto só. */
function pickSpot(spot: POSSeatingSpotOption) {
  renaming.value = false;
  emit("rename", spot.label, spot.ref);
}
function clearSpot() {
  renaming.value = false;
  emit("rename", props.tabDisplay || props.tabNumber || "", "");
}
const occupied = computed(() => new Set(props.occupiedSpotRefs || []));
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
const customerSeed = ref("");
// F6 no shell abre o mesmo modal que o chip de cliente abre. `seed`: a busca da
// venda passou o que o operador digitou ("Buscar cliente “Maria”").
function openCustomerSheet(seed = "") {
  if (props.customerLockedReason) {
    emit("customerLocked", props.customerLockedReason);
    return;
  }
  customerSeed.value = typeof seed === "string" ? seed : "";
  customerSheetOpen.value = true;
}
// Foco devolvido ao CONTEXTO quando o modal fecha: o diálogo é controlado (sem
// trigger do reka), então sem isto o foco morria no body.
const customerChipRef = ref<{ $el?: HTMLElement } | null>(null);
watch(customerSheetOpen, async (open) => {
  if (open || !import.meta.client) return;
  await nextTick();
  customerChipRef.value?.$el?.focus();
  emit("customerClosed");
});

const confirmClear = ref(false);
function runClear() {
  confirmClear.value = false;
  emit("clear");
}
/** A porta "Liberar comanda" da barra de contexto pede a MESMA confirmação de sempre. */
function askRelease() {
  if (!props.hasOpenTab || props.readOnly) return;
  confirmClear.value = true;
}
defineExpose({ openCustomer: openCustomerSheet, askRelease });
</script>

<template>
  <div class="flex min-w-0 flex-nowrap items-center gap-2">
    <!-- MODO DE ATENDIMENTO (v4): o seletor da suíte, o ligado `solid` (o ativo único
         da suíte), com ícone que dobra a leitura e `aria-pressed` para o leitor de tela. -->
    <div v-if="!readOnly" class="inline-flex shrink-0 items-center gap-1 max-lg:hidden" role="group" aria-label="Modo de atendimento" data-pos-sales-modes>
      <NuxtButton
        v-for="mode in SALES_MODES"
        :key="mode.ref"
        :size="controlSize"
        color="neutral"
        variant="outline"
        active-color="primary"
        active-variant="solid"
        :active="(salesMode || 'counter') === mode.ref"
        :icon="mode.icon"
        :aria-pressed="(salesMode || 'counter') === mode.ref"
        :data-pos-sales-mode-active="(salesMode || 'counter') === mode.ref ? '' : undefined"
        :disabled="loading"
        @click="$emit('salesModeChange', mode.ref)"
      >
        <span class="sr-only">{{ mode.label }}</span>
        <span class="hidden @min-[60rem]:inline" aria-hidden="true">{{ mode.label }}</span>
      </NuxtButton>
    </div>
    <!-- tab number (renameable) -->
    <div v-if="renaming" class="relative flex items-center gap-1" data-pos-tab-rename>
      <!-- As mesas do Salão (vínculo OPCIONAL): um toque dá o nome e liga a mesa.
           Quem prefere escrever escreve; balcão segue sem mesa. -->
      <div
        v-if="seatingSpots?.length"
        class="absolute top-full left-0 z-40 mt-1 grid w-[min(22rem,80vw)] gap-2 rounded-lg border border-border bg-popover p-2.5 text-popover-foreground shadow-lg"
        data-pos-tab-rename-spots
      >
        <p class="op-micro text-muted-foreground">Ou escolha a mesa do salão</p>
        <div class="flex max-h-48 flex-wrap gap-1.5 overflow-y-auto">
          <NuxtButton
            v-for="spot in seatingSpots"
            :key="spot.ref"
            :size="controlSize"
            color="neutral"
            variant="outline"
            active-color="primary"
            active-variant="solid"
            :active="spot.ref === seatingSpotRef"
            :disabled="occupied.has(spot.ref) && spot.ref !== seatingSpotRef"
            :title="occupied.has(spot.ref) && spot.ref !== seatingSpotRef ? `${spot.label} já tem comanda aberta` : spot.area"
            :data-pos-spot-option="spot.ref"
            :label="spot.label"
            @mousedown.prevent
            @click="pickSpot(spot)"
          />
        </div>
        <NuxtButton
          v-if="seatingSpotRef"
          color="primary"
          variant="ghost"
          class="justify-self-start"
          label="Tirar a mesa desta comanda"
          @mousedown.prevent
          @click="clearSpot"
        />
      </div>
      <UiInput
        v-model="renameValue"
        class="h-10 w-40 text-lg font-semibold"
        placeholder="Mesa, nome…"
        autofocus
        @keydown="onRenameKeydown"
      />
      <NuxtButton color="neutral" variant="ghost" icon="i-lucide-check" square aria-label="Confirmar nome" @click="confirmRename" />
      <NuxtButton color="neutral" variant="ghost" icon="i-lucide-x" square aria-label="Cancelar" @click="cancelRename" />
    </div>
    <NuxtButton
      v-else-if="hasOpenTab && canRename && !readOnly"
      color="neutral"
      variant="ghost"
      class="max-w-56 shrink-0 font-normal"
      aria-label="Renomear comanda"
      title="Renomear comanda"
      data-pos-tab-title
      @click="startRename"
    >
      <span class="flex min-w-0 flex-col text-left leading-none">
        <h1 class="op-heading tabular-nums [overflow-wrap:anywhere]">{{ title.title }}</h1>
        <span v-if="title.ref || openedAt" class="mt-0.5 op-micro text-muted-foreground tnum lg:hidden" data-pos-tab-subtitle>{{ [title.ref, openedAt ? `aberta ${openedAt}` : ""].filter(Boolean).join(" · ") }}</span>
      </span>
      <span v-if="title.ref" class="shrink-0 self-end pb-1 op-micro text-muted-foreground tnum max-lg:hidden" data-pos-tab-number>{{ title.ref }}</span>
      <Icon name="lucide:pencil" class="size-3.5 shrink-0 text-muted-foreground max-lg:hidden" />
    </NuxtButton>
    <span v-else-if="hasOpenTab" class="inline-flex max-w-56 shrink-0 items-center gap-1.5 px-2" data-pos-tab-title>
      <span class="flex min-w-0 flex-col leading-none">
        <h1 class="op-heading tabular-nums [overflow-wrap:anywhere]">{{ title.title }}</h1>
        <span v-if="title.ref || openedAt" class="mt-0.5 op-micro text-muted-foreground tnum lg:hidden" data-pos-tab-subtitle>{{ [title.ref, openedAt ? `aberta ${openedAt}` : ""].filter(Boolean).join(" · ") }}</span>
      </span>
      <span v-if="title.ref" class="shrink-0 self-end pb-1 op-micro text-muted-foreground tnum max-lg:hidden" data-pos-tab-number>{{ title.ref }}</span>
    </span>
    <h1 v-else class="whitespace-nowrap px-2 op-heading">Venda rápida</h1>
    <div class="hidden h-6 w-px shrink-0 bg-border lg:block" aria-hidden="true" />

    <!-- OS TRÊS CHIPS CARREGAM A PRÓPRIA TECLA: F6 · F7 · F8, na ordem em que
         aparecem. O atalho existia e só vivia no dicionário (tecla `?`), que é
         onde se aprende, não onde se lembra. No balcão quem ensina é a tela: a
         tecla ao lado do botão é o que faz a mão largar o mouse.

         `aria-hidden` nos três: quem usa leitor de tela navega por foco, e o
         nome acessível do botão não deve virar "Identificar cliente F6". -->

    <!-- customer chip, e, na encomenda anônima, o CHAMADO.
         O checkout tinha um cartaz dizendo "identifique o cliente" a 400px de
         distância do único botão que faz isso. Dois lugares para uma pendência:
         um que fala e outro que resolve. Agora quem fala é o próprio botão:
         ele pulsa, ganha a cor do alerta e diz o porquê no `title`.
         `motion-safe:` porque pulso é enfeite para quem pediu para a tela parar
         de se mexer; a cor e a borda seguram o recado sozinhas. -->
    <NuxtButton
      ref="customerChipRef"
      data-context-entry="customer"
      :size="controlSize"
      :color="customerRequired ? 'primary' : 'neutral'"
      variant="outline"
      class="h-auto min-h-8 min-w-0 shrink gap-2 py-1"
      :class="customerRequired ? 'motion-safe:animate-pulse' : ''"
      aria-haspopup="dialog"
      :title="customerLockedReason || (customerRequired ? 'A encomenda precisa de cliente: é quem a casa avisa se algo mudar até a data' : 'Cliente (F6)')"
      @click="readOnly ? $emit('openCustomer') : openCustomerSheet()"
    >
      <Icon
        :name="customerRequired ? 'lucide:user-round-plus' : 'lucide:user-round'"
        class="size-4 shrink-0"
        :class="customerRequired ? '' : 'text-muted-foreground'"
      />
      <span v-if="customerName || customerLookup?.ref" class="min-w-0 max-w-44 text-left leading-tight font-semibold [overflow-wrap:anywhere] max-sm:sr-only" :title="customerName || customerLookup?.email || customerLookup?.tax_id || customerLookup?.ref">{{ customerName || customerLookup?.email || customerLookup?.tax_id || customerLookup?.ref }}</span>
      <span v-else class="whitespace-nowrap max-sm:sr-only" :class="customerRequired ? '' : 'text-muted-foreground'"><span class="hidden @min-[50rem]:inline">Identificar cliente</span><span class="@min-[50rem]:hidden">Cliente</span></span>
      <OperatorKbd
        v-if="!coarsePointer"
        class="hidden @min-[50rem]:inline-flex"
        aria-hidden="true"
      >F6</OperatorKbd>
    </NuxtButton>

    <!-- RECEBIMENTO: irmão do chip de cliente. Os dois são fatos do PEDIDO,
         decididos na abertura do atendimento e revistos de relance daqui em
         diante. Na barra eles são LEITURA com porta de saída; o lugar onde se
         decide é o começo do fluxo, não esta barra. -->
    <!-- NO BALCÃO os dois chips continuam (v4, `pos-sale4.html`): "Consumir aqui F7"
         e "Agora F8" tracejado. São a porta da encomenda: entregar ou agendar troca
         o modo e abre a mesma pergunta (`pages/index.vue`, `leaveCounterThen`). -->
    <NuxtButton
      v-if="hasOpenTab"
      :size="controlSize"
      :color="!isCounter && fulfillmentType === 'delivery' ? 'primary' : 'neutral'"
      variant="outline"
      class="min-w-0 shrink-0 gap-2 max-sm:hidden"
      aria-haspopup="dialog"
      :aria-label="`Recebimento: ${isCounter ? 'Consumir aqui' : fulfillmentLabel}`"
      :title="isCounter ? 'Consumir aqui. Recebimento (F7): entregar vira encomenda' : `${fulfillmentLabel}. Recebimento (F7)`"
      data-context-entry="fulfillment"
      @click="$emit('openFulfillment')"
    >
      <Icon :name="isCounter ? 'lucide:utensils' : (fulfillmentType === 'delivery' ? 'lucide:bike' : 'lucide:store')" class="size-4 shrink-0 text-muted-foreground" />
      <span class="hidden whitespace-nowrap font-semibold @min-[36rem]:inline" aria-hidden="true">{{ isCounter ? 'Consumir aqui' : fulfillmentLabel }}</span>
      <OperatorKbd
        v-if="!coarsePointer"
        class="hidden @min-[50rem]:inline-flex"
        aria-hidden="true"
      >F7</OperatorKbd>
    </NuxtButton>

    <!-- QUANDO: o terceiro irmão. A data morava dentro do formulário de
         ENTREGA, e por isso a retirada agendada não existia: a casa recebe
         encomenda por telefone e o balcão não tinha onde escrever isso.
         "Para hoje" é o padrão e é uma AFIRMAÇÃO, não um campo vazio; por isso
         a borda tracejada (v4) enquanto nada foi agendado. -->
    <NuxtButton
      v-if="hasOpenTab"
      :size="controlSize"
      :color="scheduleConflict ? 'error' : (scheduled ? 'primary' : 'neutral')"
      variant="outline"
      class="min-w-0 shrink-0 gap-2 max-sm:hidden"
      :class="scheduleConflict || scheduled ? '' : 'text-muted-foreground'"
      data-context-entry="schedule"
      aria-haspopup="dialog"
      :aria-label="`Quando: ${isCounter ? 'Agora' : scheduleLabel}`"
      :title="scheduleConflictReason || (isCounter ? 'Agora. Quando (F8): agendar vira encomenda' : `${scheduleLabel}. Quando (F8)`)"
      @click="$emit('openSchedule')"
    >
      <Icon
        :name="scheduleConflict ? 'lucide:triangle-alert' : (scheduled ? 'lucide:calendar-clock' : 'lucide:clock')"
        class="size-4 shrink-0"
        :class="scheduleConflict ? '' : 'text-muted-foreground'"
      />
      <span class="hidden whitespace-nowrap @min-[26rem]:inline" :class="scheduled || scheduleConflict ? 'font-semibold' : ''" aria-hidden="true">{{ isCounter ? 'Agora' : scheduleLabel }}</span>
      <OperatorKbd
        v-if="!coarsePointer"
        class="hidden @min-[50rem]:inline-flex"
        aria-hidden="true"
      >F8</OperatorKbd>
    </NuxtButton>

    <!-- Liberar comanda: a porta mora no fim da barra de contexto (`pages/index.vue`,
         v4); o gesto e a confirmação continuam aqui (`askRelease`). -->
    <PosCustomerModal
      v-model:open="customerSheetOpen"
      :seed-query="customerSeed"
      :customer-name="customerName"
      :customer-phone="customerPhone"
      :customer-tax-id="customerTaxId"
      :customer-email="customerEmail"
      :customer-lookup="customerLookup"
      :search-results="searchResults"
      :search-busy="searchBusy"
      :lookup-busy="lookupBusy"
      :resolved-new="customerResolvedNew"
      :new-customer-prefs="newCustomerPrefs"
      :customer-decision="readOnly ? null : customerDecision"
      :customer-merge-busy="customerMergeBusy"
      :customer-release-busy="customerReleaseBusy"
      @update:customer-name="$emit('update:customerName', $event)"
      @update:customer-phone="$emit('update:customerPhone', $event)"
      @update:customer-tax-id="$emit('update:customerTaxId', $event)"
      @update:customer-email="$emit('update:customerEmail', $event)"
      @search="$emit('search', $event)"
      @select-result="$emit('selectResult', $event)"
      @clear="$emit('clearCustomer')"
      @resolve-customer="$emit('resolveCustomer', $event)"
      @decision-confirm="$emit('decisionConfirm', $event)"
      @decision-cancel="$emit('decisionCancel')"
      @decision-merge="$emit('decisionMerge', $event)"
      @decision-release="$emit('decisionRelease', $event)"
      @decision-pick="$emit('decisionPick', $event)"
      @apply-customer-favorite="$emit('applyCustomerFavorite')"
      @repeat-customer-last-order="$emit('repeatCustomerLastOrder')"
      @apply-preference="(key, value) => $emit('applyPreference', key, value)"
    />

    <NuxtModal
      :open="confirmClear"
      title="Liberar comanda?"
      :description="hasFiredItems
        ? 'Isso descarta este atendimento e libera a comanda. O que já foi enviado à cozinha é cancelado: avise quem está lá dentro. Não dá para desfazer.'
        : 'Isso descarta este atendimento e libera a comanda. A ação não pode ser desfeita.'"
      :ui="{ content: 'sm:max-w-sm' }"
      data-pos-release-tab
      @update:open="(value: boolean) => { if (!value) confirmClear = false; }"
    >
      <template #footer>
        <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="confirmClear = false" />
          <NuxtButton color="error" label="Liberar comanda" :disabled="loading" @click="runClear" />
        </div>
      </template>
    </NuxtModal>
  </div>
</template>
