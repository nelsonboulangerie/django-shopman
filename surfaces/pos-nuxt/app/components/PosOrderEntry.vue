<script setup lang="ts">
import {
  firstPendingStep,
  nextOrderSetupStep,
  orderSetupStepEnabled,
  orderSetupSteps,
  type OrderSetupIssue,
  type OrderSetupStepKey,
} from "~/presentation/orderSetup";

// O ASSISTENTE DA ENCOMENDA. Uma etapa por vez, na ordem da regra: cliente,
// recebimento, endereço (só na entrega) e data. O molde é o do `CampaignForm`
// do Marketing: trilha de etapas com `aria-current="step"`, uma seção visível
// por vez (`v-show`, para nada perder estado ao ir e voltar) e o rodapé
// "Etapa X de N" com Voltar e Continuar.
//
// A PRONTIDÃO NÃO É DESTE COMPONENTE. Ele recebe o `issue` de
// `orderSetupIssue` (o mesmo que o servidor cobra em `validate_sales_mode`) e
// só o traduz em etapas (`presentation/orderSetup`). Por isso as invalidações
// chegam sem código aqui: o cliente sai, a etapa 1 volta a ser a vez; a
// retirada vira entrega sem endereço, a etapa do endereço aparece pendente.
//
// Cada etapa resolve com o MESMO diálogo de sempre (cliente, recebimento,
// agenda). O assistente não reabre a pergunta: ele diz qual é a vez.
const props = defineProps<{
  issue: OrderSetupIssue;
  /** Entrega escolhida: só então o endereço é etapa. */
  delivery?: boolean;
  customerName: string;
  itemCount?: number;
  fulfillmentLabel: string;
  scheduleLabel: string;
  /** A janela combinada. Vazia = horário a combinar (trocar o dia a limpa). */
  scheduleWindow?: string;
  loading: boolean;
}>();
const emit = defineEmits<{ customer: []; fulfillment: []; schedule: []; complete: [] }>();

const steps = computed(() => orderSetupSteps(props.issue, Boolean(props.delivery)));
const current = ref<OrderSetupStepKey>(firstPendingStep(steps.value));
const currentIndex = computed(() => Math.max(0, steps.value.findIndex((step) => step.key === current.value)));
const currentStep = computed(() => steps.value[currentIndex.value]!);
let currentWasReady = currentStep.value.ready;

// A regra mudou (o operador escolheu num diálogo, ou desfez algo). Quem decide
// para onde ir é `nextOrderSetupStep`; o foco só anda quando o diálogo fecha
// (`focusCurrent`, chamado pela página), para não puxar o foco de trás dele.
watch(steps, (next) => {
  current.value = nextOrderSetupStep({ steps: next, current: current.value, wasReady: currentWasReady });
  currentWasReady = next.find((step) => step.key === current.value)?.ready ?? false;
});

const { reveal } = useNextFocus();
const focusKey = (key: OrderSetupStepKey) => `order-step-${key}`;
function focusCurrent() {
  reveal(focusKey(current.value));
}
defineExpose({ focusCurrent });

function goToStep(index: number) {
  if (!orderSetupStepEnabled(steps.value, index)) return;
  current.value = steps.value[index]!.key;
  currentWasReady = steps.value[index]!.ready;
  focusCurrent();
}
const isLast = computed(() => currentIndex.value === steps.value.length - 1);
const allReady = computed(() => !props.issue);

// O endereço mora no diálogo do recebimento: a etapa 3 abre o mesmo diálogo.
function act(key: OrderSetupStepKey) {
  if (key === "customer") emit("customer");
  else if (key === "schedule") emit("schedule");
  else emit("fulfillment");
}
function isReady(key: OrderSetupStepKey) {
  return steps.value.find((step) => step.key === key)?.ready ?? false;
}

// "Hoje · horário a combinar" já diz; um dia futuro sem janela, não.
const windowPending = computed(() => !props.scheduleWindow?.trim() && !props.scheduleLabel.includes("a combinar"));
</script>

<template>
  <section class="mx-auto grid w-full max-w-2xl gap-5 p-4 md:p-8" aria-label="Preparar encomenda">
    <div class="grid gap-1">
      <h1 class="text-xl font-semibold">{{ itemCount ? "Preparar encomenda" : "Nova encomenda" }}</h1>
      <p class="text-sm text-muted-foreground">Combine quem recebe, como e quando. Depois, monte o pedido.</p>
    </div>
    <p v-if="itemCount" class="rounded-md border bg-muted/30 px-3 py-2 text-sm">{{ itemCount }} {{ itemCount === 1 ? "item preservado" : "itens preservados" }}. Complete os dados para continuar.</p>

    <nav aria-label="Etapas da encomenda">
      <ol class="grid gap-1 rounded-lg border bg-muted/30 p-1" :style="{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }">
        <li v-for="(step, index) in steps" :key="step.key">
          <button
            type="button"
            data-order-step-nav
            class="flex min-h-11 w-full items-center justify-center gap-2 rounded-md px-2 text-xs font-medium transition sm:justify-start"
            :class="step.key === current ? 'bg-background text-foreground shadow-sm' : step.ready ? 'text-success' : 'text-muted-foreground'"
            :disabled="loading || !orderSetupStepEnabled(steps, index)"
            :aria-current="step.key === current ? 'step' : undefined"
            :aria-label="`${index + 1}. ${step.label}${step.ready ? ', pronta' : ''}`"
            @click="goToStep(index)"
          >
            <span
              class="grid size-6 shrink-0 place-items-center rounded-full border text-[11px]"
              :class="step.key === current ? 'border-primary bg-primary text-primary-foreground' : step.ready ? 'border-success text-success' : 'border-border'"
            >
              <Icon v-if="step.ready" name="lucide:check" class="size-3.5" />
              <template v-else>{{ index + 1 }}</template>
            </span>
            <span class="hidden truncate text-left sm:inline">{{ step.label }}</span>
          </button>
        </li>
      </ol>
    </nav>

    <!-- Uma seção por etapa, todas montadas: `v-show`, nunca `v-if`. -->
    <div v-show="current === 'customer'" data-order-step="customer" :data-focus-target="focusKey('customer')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('customer') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Quem é o cliente?</h2>
      <p class="text-sm text-muted-foreground">{{ isReady('customer') ? customerName : "Quem vai receber ou buscar. É o contato se algo mudar até a data." }}</p>
      <UiButton data-focus-control class="justify-self-start" :variant="isReady('customer') ? 'outline' : 'default'" :disabled="loading" @click="act('customer')">{{ isReady('customer') ? "Trocar cliente" : "Identificar cliente" }}</UiButton>
    </div>

    <div v-show="current === 'fulfillment'" data-order-step="fulfillment" :data-focus-target="focusKey('fulfillment')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('fulfillment') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Entrega ou retirada?</h2>
      <p class="text-sm text-muted-foreground">{{ isReady('fulfillment') ? fulfillmentLabel : "Escolha como o cliente vai receber." }}</p>
      <UiButton data-focus-control class="justify-self-start" :variant="isReady('fulfillment') ? 'outline' : 'default'" :disabled="loading" @click="act('fulfillment')">{{ isReady('fulfillment') ? "Trocar entrega ou retirada" : "Escolher entrega ou retirada" }}</UiButton>
    </div>

    <div v-show="current === 'address'" data-order-step="address" :data-focus-target="focusKey('address')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('address') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Onde entregar?</h2>
      <p class="text-sm text-muted-foreground">{{ isReady('address') ? fulfillmentLabel : "Falta o endereço de entrega." }}</p>
      <UiButton data-focus-control class="justify-self-start" :variant="isReady('address') ? 'outline' : 'default'" :disabled="loading" @click="act('address')">{{ isReady('address') ? "Trocar endereço" : "Informar endereço" }}</UiButton>
    </div>

    <div v-show="current === 'schedule'" data-order-step="schedule" :data-focus-target="focusKey('schedule')" class="grid scroll-mt-4 gap-3 rounded-lg border p-4 outline-none" :class="isReady('schedule') ? 'border-success/40' : 'border-primary bg-primary/5'">
      <h2 class="font-medium">Para quando?</h2>
      <p class="text-sm text-muted-foreground">{{ isReady('schedule') ? scheduleLabel : "Combine o dia e o horário: é o que a casa promete ao cliente." }}</p>
      <p v-if="isReady('schedule') && windowPending" data-schedule-window-pending class="text-sm text-muted-foreground">Horário a combinar.</p>
      <UiButton data-focus-control class="justify-self-start" :variant="isReady('schedule') ? 'outline' : 'default'" :disabled="loading" @click="act('schedule')">{{ isReady('schedule') ? "Trocar data e horário" : "Escolher data e horário" }}</UiButton>
    </div>

    <div class="flex flex-wrap items-center gap-2 border-t pt-4">
      <UiButton v-if="currentIndex > 0" variant="outline" :disabled="loading" @click="goToStep(currentIndex - 1)">Voltar</UiButton>
      <span class="min-w-0 flex-1 text-center text-xs text-muted-foreground" role="status">Etapa {{ currentIndex + 1 }} de {{ steps.length }}: {{ currentStep.label }}</span>
      <UiButton v-if="!isLast" :disabled="loading || !currentStep.ready" @click="goToStep(currentIndex + 1)">Continuar</UiButton>
      <UiButton v-else :disabled="loading || !allReady" @click="emit('complete')">Montar encomenda <Icon name="lucide:arrow-right" class="ml-2 size-4" /></UiButton>
    </div>
  </section>
</template>
