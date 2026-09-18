<script setup lang="ts">
const props = defineProps<{
  issue: "customer" | "fulfillment" | "address" | "schedule" | "";
  customerName: string;
  itemCount?: number;
  fulfillmentLabel: string;
  scheduleLabel: string;
  loading: boolean;
}>();
const emit = defineEmits<{ customer: []; fulfillment: []; schedule: []; complete: [] }>();
const sectionRef = ref<HTMLElement | null>(null);
defineExpose({ focusCurrent: () => {
  const index = props.issue === "customer" ? 0 : ["fulfillment", "address"].includes(props.issue) ? 1 : props.issue === "schedule" ? 2 : 3;
  sectionRef.value?.querySelectorAll("button")[index]?.focus();
} });
const customerReady = computed(() => props.issue !== "customer");
const fulfillmentReady = computed(() => customerReady.value && !["fulfillment", "address"].includes(props.issue));
const scheduleReady = computed(() => fulfillmentReady.value && props.issue !== "schedule");

// TRÊS ESTADOS POR PASSO, e a tela DIZ qual é: feito (verde), a vez (realce
// cheio, botão cheio) e ainda não (apagado). Os três cartões eram idênticos, só
// o ícone mudava — e quem está com o cliente ao telefone olha de relance, não
// lê ícone. O passo da vez é o único com `aria-current="step"`.
type StepState = "done" | "current" | "locked";
const steps = computed<StepState[]>(() => {
  const ready = [customerReady.value, fulfillmentReady.value, scheduleReady.value];
  const currentIndex = ready.indexOf(false);
  return ready.map((done, index) => (done ? "done" : index === currentIndex ? "current" : "locked"));
});
const STEP_CLASSES: Record<StepState, string> = {
  done: "border-success/40 bg-card",
  current: "border-primary bg-primary/5 shadow-xs",
  locked: "border-dashed bg-card opacity-60",
};
</script>

<template>
  <section ref="sectionRef" class="mx-auto grid max-w-2xl gap-5 p-4 md:p-8" aria-label="Preparar encomenda">
    <div class="grid gap-1">
      <h1 class="text-xl font-semibold">{{ itemCount ? "Preparar encomenda" : "Nova encomenda" }}</h1>
      <p class="text-sm text-muted-foreground">Combine quem recebe, como e quando. Depois, monte o pedido.</p>
    </div>
    <p v-if="itemCount" class="rounded-md border bg-muted/30 px-3 py-2 text-sm">{{ itemCount }} {{ itemCount === 1 ? "item preservado" : "itens preservados" }}. Complete os dados para continuar.</p>
    <ol class="grid gap-3">
      <li class="flex items-center gap-3 rounded-lg border p-4 transition-colors" :class="STEP_CLASSES[steps[0]!]" :aria-current="steps[0] === 'current' ? 'step' : undefined">
        <Icon :name="customerReady ? 'lucide:check-circle' : 'lucide:user'" class="size-5 shrink-0" :class="customerReady ? 'text-success' : 'text-primary'" />
        <div class="min-w-0 flex-1"><h2 class="font-medium">1. Cliente</h2><p class="text-sm text-muted-foreground">{{ customerReady ? customerName : 'Quem vai receber ou buscar. É o contato se algo mudar até a data.' }}</p></div>
        <UiButton :variant="customerReady ? 'outline' : 'default'" :disabled="loading" @click="emit('customer')">{{ customerReady ? 'Alterar' : 'Identificar cliente' }}</UiButton>
      </li>
      <li class="flex items-center gap-3 rounded-lg border p-4 transition-colors" :class="STEP_CLASSES[steps[1]!]" :aria-current="steps[1] === 'current' ? 'step' : undefined">
        <Icon :name="fulfillmentReady ? 'lucide:check-circle' : 'lucide:package'" class="size-5 shrink-0" :class="fulfillmentReady ? 'text-success' : steps[1] === 'current' ? 'text-primary' : 'text-muted-foreground'" />
        <div class="min-w-0 flex-1"><h2 class="font-medium">2. Entrega ou retirada</h2><p class="text-sm text-muted-foreground">{{ issue === 'address' ? 'Complete o endereço de entrega.' : fulfillmentReady ? fulfillmentLabel : 'Escolha como o cliente vai receber.' }}</p></div>
        <UiButton :variant="fulfillmentReady || steps[1] === 'locked' ? 'outline' : 'default'" :disabled="loading || !customerReady" @click="emit('fulfillment')">{{ fulfillmentReady ? 'Alterar' : 'Escolher recebimento' }}</UiButton>
      </li>
      <li class="flex items-center gap-3 rounded-lg border p-4 transition-colors" :class="STEP_CLASSES[steps[2]!]" :aria-current="steps[2] === 'current' ? 'step' : undefined">
        <Icon :name="!issue ? 'lucide:check-circle' : 'lucide:calendar-clock'" class="size-5 shrink-0" :class="!issue ? 'text-success' : steps[2] === 'current' ? 'text-primary' : 'text-muted-foreground'" />
        <div class="min-w-0 flex-1"><h2 class="font-medium">3. Data e horário</h2><p class="text-sm text-muted-foreground">{{ !issue ? scheduleLabel : 'Combine o dia e o horário — é o que a casa promete.' }}</p></div>
        <UiButton :variant="!issue || steps[2] === 'locked' ? 'outline' : 'default'" :disabled="loading || !fulfillmentReady" @click="emit('schedule')">{{ !issue ? 'Alterar' : 'Escolher data e horário' }}</UiButton>
      </li>
    </ol>
    <UiButton size="lg" :disabled="loading || Boolean(issue)" @click="emit('complete')">Montar encomenda <Icon name="lucide:arrow-right" class="ml-2 size-4" /></UiButton>
  </section>
</template>
