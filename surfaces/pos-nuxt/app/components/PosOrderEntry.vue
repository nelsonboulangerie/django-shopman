<script setup lang="ts">
import type { POSFulfillmentOptionProjection, SavedAddressProjection } from "~/types/pos";
import type { ScheduleWindow } from "~/presentation/schedule";
import {
  firstPendingStep,
  nextOrderSetupStep,
  orderSetupStepEnabled,
  orderSetupSteps,
  type OrderSetupIssue,
  type OrderSetupStepKey,
} from "~/presentation/orderSetup";
import { globalKeysBlocked } from "~/utils/keyboardGuard";

// O ASSISTENTE DA ENCOMENDA. Uma etapa por vez, na ordem da regra: cliente,
// data, recebimento e endereço (só na entrega). "Para quando" vem em segundo
// porque é a data que diz o que a casa pode prometer (decisão do dono,
// 19/11/2026, #2754). O molde é o do `CampaignForm` do Marketing: trilha de
// etapas com `aria-current="step"`, uma seção visível por vez (`v-show`, para
// nada perder estado ao ir e voltar) e o rodapé "Etapa X de N" com Voltar e
// Continuar.
//
// A PRONTIDÃO NÃO É DESTE COMPONENTE. Ele recebe o `issue` de
// `orderSetupIssue` (o mesmo que o servidor cobra em `validate_sales_mode`) e
// só o traduz em etapas (`presentation/orderSetup`). Por isso as invalidações
// chegam sem código aqui: o cliente sai, a etapa 1 volta a ser a vez; a
// retirada vira entrega sem endereço, a etapa do endereço aparece pendente.
//
// O ASSISTENTE PERGUNTA NO PRÓPRIO CARTÃO (P2-8 do laudo de 16/11). Recebimento
// e data eram um botão que abria um diálogo por cima do assistente; agora a
// escolha mora na etapa: Retirada ou Entrega são os dois botões da etapa, e o
// dia e o horário são o `PosSchedulePicker` (a mesma peça do diálogo "Quando" e
// do reagendar), montado aqui sem moldura. O cliente continua na busca de
// cliente do cabeçalho (a mesma de toda a venda). O endereço JÁ CADASTRADO se
// escolhe aqui mesmo, numa lista de linha inteira com o padrão já marcado (Enter
// aceita e segue, as setas trocam); só o endereço NOVO vai ao formulário de
// entrega (CEP, mapa e taxa), que não cabe num cartão.
const props = defineProps<{
  issue: OrderSetupIssue;
  /** Entrega escolhida: só então o endereço é etapa. */
  delivery?: boolean;
  customerName: string;
  itemCount?: number;
  scheduleLabel: string;
  /** A janela combinada. Vazia = horário a combinar (trocar o dia a limpa). */
  scheduleWindow?: string;
  loading: boolean;
  /** As formas de receber que a loja oferece (retirada, entrega). */
  fulfillmentOptions?: POSFulfillmentOptionProjection[];
  /** A forma já escolhida pelo operador; vazia enquanto ele não escolheu. */
  chosenFulfillment?: "pickup" | "delivery" | "";
  /** Os endereços já cadastrados do cliente (o padrão primeiro). */
  savedAddresses?: SavedAddressProjection[];
  /** Qual deles é o da entrega em edição ("" quando nenhum). */
  chosenAddress?: string;
  /** O endereço da entrega em edição, numa linha ("" enquanto não há). */
  addressSummary?: string;
  /** O dia e a janela escolhidos (vazios até o operador escolher). */
  scheduleDate?: string;
  scheduleTimeSlot?: string;
  /** O que o `PosSchedulePicker` precisa: a mesma resposta do diálogo "Quando". */
  schedule?: {
    today: string;
    availableDates: string[];
    maxDate: string;
    windows: ScheduleWindow[];
    bottleneckName: string;
    readyAt: string;
    pending: boolean;
    failed: boolean;
  };
}>();
const emit = defineEmits<{
  customer: [];
  /** Um endereço que não está na lista: abre o formulário de entrega. */
  fulfillment: [];
  /** Um endereço do cadastro, escolhido na lista. */
  pickAddress: [SavedAddressProjection];
  /** Tira o endereço da entrega em edição (o cadastro do cliente não muda). */
  clearAddress: [];
  /** Retirada ou entrega, escolhida no cartão. */
  pickFulfillment: ["pickup" | "delivery"];
  /** A etapa da data ficou à vista: a agenda precisa ser buscada. */
  schedule: [];
  "update:scheduleDate": [string];
  "update:scheduleTimeSlot": [string];
  complete: [];
}>();

const steps = computed(() => orderSetupSteps(props.issue, Boolean(props.delivery)));
const current = ref<OrderSetupStepKey>(firstPendingStep(steps.value));
const currentIndex = computed(() => Math.max(0, steps.value.findIndex((step) => step.key === current.value)));
const currentStep = computed(() => steps.value[currentIndex.value]!);
let currentWasReady = currentStep.value.ready;

// A regra mudou (o operador escolheu num diálogo, ou desfez algo). Quem decide
// para onde ir é `nextOrderSetupStep`; o foco só anda quando o diálogo fecha
// (`focusCurrent`, chamado pela página), para não puxar o foco de trás dele.
watch(steps, (next, previous) => {
  const hasAddress = (list: typeof next) => list.some((step) => step.key === "address");
  current.value = nextOrderSetupStep({
    steps: next,
    current: current.value,
    wasReady: currentWasReady,
    addressIsNew: hasAddress(next) && !hasAddress(previous),
  });
  currentWasReady = next.find((step) => step.key === current.value)?.ready ?? false;
});

// A data só se escolhe com a agenda na mão: a etapa à vista pede a busca.
watch(current, (key) => {
  if (key === "schedule") emit("schedule");
}, { immediate: true });

const { reveal } = useNextFocus();
const focusKey = (key: OrderSetupStepKey) => `order-step-${key}`;
const hasSavedAddresses = computed(() => Boolean(props.savedAddresses?.length));
const addressListRef = ref<{ focusTarget: () => HTMLElement | null } | null>(null);
function focusCurrent() {
  // Na etapa do endereço com lista, o foco cai no endereço marcado: o Enter
  // aceita e segue sem o operador procurar onde está.
  if (current.value === "address" && hasSavedAddresses.value) {
    reveal(() => addressListRef.value?.focusTarget(), { align: "center" });
    return;
  }
  reveal(focusKey(current.value));
}
// O operador tocou em Entrega NO CARTÃO e a etapa do endereço chegou: o foco vai
// para ela (na lista, o endereço padrão já vem marcado, e o Enter aceita). Com
// um diálogo aberto por cima, quem move o foco é a página, quando ele fechar.
watch(current, (key, previous) => {
  if (key === "address" && previous === "fulfillment" && !globalKeysBlocked()) focusCurrent();
}, { flush: "post" });

// O diálogo "Quando" (chip da barra, F7) tem o seu próprio Confirmar: a data
// combinada lá não pede outro Continuar aqui. A página avisa quando ele fecha.
function scheduleConfirmed() {
  if (current.value !== "schedule" || !isReady("schedule")) return;
  current.value = firstPendingStep(steps.value);
  currentWasReady = isReady(current.value);
}
defineExpose({ focusCurrent, scheduleConfirmed });

function goToStep(index: number) {
  if (!orderSetupStepEnabled(steps.value, index)) return;
  current.value = steps.value[index]!.key;
  currentWasReady = steps.value[index]!.ready;
  focusCurrent();
}
const isLast = computed(() => currentIndex.value === steps.value.length - 1);
const allReady = computed(() => !props.issue);

// O endereço novo mora no formulário de entrega: a etapa abre esse formulário.
function act(key: OrderSetupStepKey) {
  if (key === "customer") emit("customer");
  else emit("fulfillment");
}
// Enter no endereço marcado: o mesmo caminho do botão do rodapé.
function acceptAddress() {
  if (props.loading || !isReady("address")) return;
  if (!isLast.value) goToStep(currentIndex.value + 1);
  else if (allReady.value) emit("complete");
}
// O endereço da entrega em edição só é dito por extenso quando não é nenhum da
// lista (foi digitado na hora): os da lista se dizem sozinhos, com a marcação.
const typedAddress = computed(() => (props.chosenAddress ? "" : (props.addressSummary || "").trim()));
function fulfillmentChosen(ref: string) {
  return Boolean(props.chosenFulfillment) && props.chosenFulfillment === ref;
}
function isReady(key: OrderSetupStepKey) {
  return steps.value.find((step) => step.key === key)?.ready ?? false;
}

// "Hoje, o quanto antes" já diz; um dia futuro sem janela, não.
const windowPending = computed(() => !props.scheduleWindow?.trim() && !props.scheduleLabel.includes("o quanto antes"));
</script>

<template>
  <section class="mx-auto grid w-full max-w-2xl gap-5 p-4 md:p-8" aria-label="Preparar encomenda">
    <div class="grid gap-1">
      <h1 class="text-xl font-semibold">{{ itemCount ? "Preparar encomenda" : "Nova encomenda" }}</h1>
      <p class="text-sm text-muted-foreground">Combine quem recebe, para quando e como. Depois, monte o pedido.</p>
    </div>
    <p v-if="itemCount" class="rounded-md border bg-muted/30 px-3 py-2 text-sm">{{ itemCount }} {{ itemCount === 1 ? "item preservado" : "itens preservados" }}. Complete os dados para continuar.</p>

    <nav aria-label="Etapas da encomenda">
      <ol class="grid gap-1 rounded-lg border bg-muted/30 p-1" :style="{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }">
        <li v-for="(step, index) in steps" :key="step.key">
          <NuxtButton
            color="neutral"
            variant="ghost"
            data-order-step-nav
            class="flex min-h-8 w-full items-center justify-center gap-2 rounded-md px-2 text-xs font-medium transition sm:justify-start"
            :class="step.key === current ? 'bg-background text-foreground shadow-sm' : step.ready ? 'text-success' : 'text-muted-foreground'"
            :disabled="loading || !orderSetupStepEnabled(steps, index)"
            :aria-current="step.key === current ? 'step' : undefined"
            :aria-label="`${index + 1}. ${step.label}${step.ready ? ', pronta' : ''}`"
            @click="goToStep(index)"
          >
            <span
              class="grid size-6 shrink-0 place-items-center rounded-full border text-xs"
              :class="step.key === current ? 'border-primary bg-primary text-primary-foreground' : step.ready ? 'border-success text-success' : 'border-border'"
            >
              <Icon v-if="step.ready" name="lucide:check" class="size-3.5" />
              <template v-else>{{ index + 1 }}</template>
            </span>
            <span class="hidden truncate text-left sm:inline">{{ step.label }}</span>
          </NuxtButton>
        </li>
      </ol>
    </nav>

    <!-- Uma seção por etapa, todas montadas: `v-show`, nunca `v-if`. -->
    <div v-show="current === 'customer'" data-order-step="customer" :data-focus-target="focusKey('customer')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('customer') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Quem é o cliente?</h2>
      <p class="text-sm text-muted-foreground">{{ isReady('customer') ? customerName : "Quem vai receber ou buscar. É o contato se algo mudar até a data." }}</p>
      <NuxtButton data-focus-control class="justify-self-start" :color="isReady('customer') ? 'neutral' : 'primary'" :variant="isReady('customer') ? 'outline' : 'solid'" :disabled="loading" @click="act('customer')">{{ isReady('customer') ? "Trocar cliente" : "Identificar cliente" }}</NuxtButton>
    </div>

    <div v-show="current === 'schedule'" data-order-step="schedule" :data-focus-target="focusKey('schedule')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('schedule') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Para quando?</h2>
      <p class="text-sm text-muted-foreground">{{ isReady('schedule') ? scheduleLabel : "Escolha o dia e o horário: é o que a casa promete ao cliente." }}</p>
      <PosSchedulePicker
        v-if="schedule"
        :today="schedule.today"
        :date="scheduleDate || ''"
        :time-slot="scheduleTimeSlot || ''"
        :available-dates="schedule.availableDates"
        :max-date="schedule.maxDate"
        :windows="schedule.windows"
        :bottleneck-name="schedule.bottleneckName"
        :ready-at="schedule.readyAt"
        :pending="schedule.pending"
        :failed="schedule.failed"
        day-label="Dia da encomenda"
        @update:date="emit('update:scheduleDate', $event)"
        @update:time-slot="emit('update:scheduleTimeSlot', $event)"
      />
      <p v-if="isReady('schedule') && windowPending" data-schedule-window-pending class="text-sm text-muted-foreground">Horário a combinar.</p>
    </div>

    <div v-show="current === 'fulfillment'" data-order-step="fulfillment" :data-focus-target="focusKey('fulfillment')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('fulfillment') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Entrega ou retirada?</h2>
      <div role="radiogroup" aria-label="Como o cliente recebe" class="grid grid-cols-2 gap-2">
        <NuxtButton
          v-for="(option, index) in fulfillmentOptions || []"
          :key="option.ref"
          :data-focus-control="index === 0 ? '' : undefined"
          role="radio"
          :aria-checked="fulfillmentChosen(option.ref)"
          :data-order-fulfillment="option.ref"
          color="neutral"
          variant="outline"
          class="h-auto min-h-control justify-start whitespace-normal px-3 py-2 text-left"
          :class="fulfillmentChosen(option.ref) ? 'border-primary bg-primary/5' : 'bg-background'"
          :disabled="loading"
          @click="emit('pickFulfillment', option.ref)"
        >
          <span>
            <span class="block text-sm font-semibold" :class="fulfillmentChosen(option.ref) ? 'text-primary' : ''">{{ option.label }}</span>
            <span class="block text-xs text-muted-foreground">{{ option.description }}</span>
          </span>
        </NuxtButton>
      </div>
    </div>

    <div v-show="current === 'address'" data-order-step="address" :data-focus-target="focusKey('address')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('address') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Onde entregar?</h2>
      <template v-if="hasSavedAddresses">
        <PosSavedAddressList
          ref="addressListRef"
          :addresses="savedAddresses || []"
          :selected="chosenAddress || ''"
          :disabled="loading"
          @pick="emit('pickAddress', $event)"
          @accept="acceptAddress"
        />
        <p v-if="typedAddress" class="text-sm" data-order-address-typed>Endereço desta entrega: {{ typedAddress }}</p>
        <p v-else-if="!isReady('address')" class="text-sm text-muted-foreground">Escolha um endereço do cliente ou informe outro.</p>
      </template>
      <p v-else class="text-sm text-muted-foreground">{{ isReady('address') ? addressSummary : "Falta o endereço de entrega." }}</p>
      <div class="flex flex-wrap gap-2">
        <NuxtButton
          :data-focus-control="hasSavedAddresses ? undefined : ''"
          :color="isReady('address') || hasSavedAddresses ? 'neutral' : 'primary'"
          :variant="isReady('address') || hasSavedAddresses ? 'outline' : 'solid'"
          :disabled="loading"
          data-order-address-other
          @click="act('address')"
        >{{ hasSavedAddresses ? "Informar outro endereço" : isReady('address') ? "Trocar endereço" : "Informar endereço" }}</NuxtButton>
        <NuxtButton
          v-if="isReady('address')"
          color="neutral"
          variant="ghost"
          :disabled="loading"
          title="O endereço continua no cadastro do cliente"
          data-order-address-clear
          @click="emit('clearAddress')"
        >Tirar o endereço desta entrega</NuxtButton>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2 border-t pt-4">
      <NuxtButton v-if="currentIndex > 0" variant="outline" :disabled="loading" @click="goToStep(currentIndex - 1)">Voltar</NuxtButton>
      <span class="min-w-0 flex-1 text-center text-xs text-muted-foreground" role="status">Etapa {{ currentIndex + 1 }} de {{ steps.length }}: {{ currentStep.label }}</span>
      <NuxtButton v-if="!isLast" :disabled="loading || !currentStep.ready" @click="goToStep(currentIndex + 1)">Continuar</NuxtButton>
      <NuxtButton v-else :disabled="loading || !allReady" @click="emit('complete')">Montar encomenda <Icon name="lucide:arrow-right" class="ml-2 size-4" /></NuxtButton>
    </div>
  </section>
</template>
