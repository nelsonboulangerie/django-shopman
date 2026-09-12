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
</script>

<template>
  <section ref="sectionRef" class="mx-auto grid max-w-2xl gap-5 p-4 md:p-8" aria-label="Preparar encomenda">
    <div class="grid gap-1">
      <h1 class="text-xl font-semibold">{{ itemCount ? "Preparar encomenda" : "Nova encomenda" }}</h1>
      <p class="text-sm text-muted-foreground">Combine quem recebe, como e quando. Depois, monte o pedido.</p>
    </div>
    <p v-if="itemCount" class="rounded-md border bg-muted/30 px-3 py-2 text-sm">{{ itemCount }} {{ itemCount === 1 ? "item preservado" : "itens preservados" }}. Complete os dados para continuar.</p>
    <ol class="grid gap-3">
      <li class="flex items-center gap-3 rounded-lg border bg-card p-4">
        <Icon :name="customerReady ? 'lucide:check-circle' : 'lucide:user'" class="size-5 shrink-0" />
        <div class="min-w-0 flex-1"><h2 class="font-medium">1. Cliente</h2><p class="text-sm text-muted-foreground">{{ customerReady ? customerName : 'Identifique o cliente no cadastro.' }}</p></div>
        <UiButton variant="outline" :disabled="loading" @click="emit('customer')">{{ customerReady ? 'Alterar' : 'Identificar cliente' }}</UiButton>
      </li>
      <li class="flex items-center gap-3 rounded-lg border bg-card p-4">
        <Icon :name="fulfillmentReady ? 'lucide:check-circle' : 'lucide:package'" class="size-5 shrink-0" />
        <div class="min-w-0 flex-1"><h2 class="font-medium">2. Entrega ou retirada</h2><p class="text-sm text-muted-foreground">{{ issue === 'address' ? 'Complete o endereço de entrega.' : fulfillmentReady ? fulfillmentLabel : 'Escolha como o cliente vai receber.' }}</p></div>
        <UiButton variant="outline" :disabled="loading || !customerReady" @click="emit('fulfillment')">{{ fulfillmentReady ? 'Alterar' : 'Escolher recebimento' }}</UiButton>
      </li>
      <li class="flex items-center gap-3 rounded-lg border bg-card p-4">
        <Icon :name="!issue ? 'lucide:check-circle' : 'lucide:calendar-clock'" class="size-5 shrink-0" />
        <div class="min-w-0 flex-1"><h2 class="font-medium">3. Data e horário</h2><p class="text-sm text-muted-foreground">{{ !issue ? scheduleLabel : 'Combine a data e o horário do pedido.' }}</p></div>
        <UiButton variant="outline" :disabled="loading || !fulfillmentReady" @click="emit('schedule')">{{ !issue ? 'Alterar' : 'Escolher data e horário' }}</UiButton>
      </li>
    </ol>
    <UiButton size="lg" :disabled="loading || Boolean(issue)" @click="emit('complete')">Montar encomenda <Icon name="lucide:arrow-right" class="ml-2 size-4" /></UiButton>
  </section>
</template>
