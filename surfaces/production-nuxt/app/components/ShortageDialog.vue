<script setup lang="ts">
// Material/order shortage modal. Renders the structured shortage envelope the API
// returns (409) when a finish/plan would consume more than is available, or leave
// committed orders uncovered. For a material shortage the operator can override
// (force=1) only when the server advertises that possibility. An order shortage
// offers "retry" (o operador volta ao número que digitou e corrige); confirmar o
// previsto abaixo das encomendas nunca é forçável, então ali o caminho é só esse.
import type { ProductionShortageError } from "~/types/production";
import { formatQtyUnit } from "~/presentation/production";

const props = defineProps<{ shortage: ProductionShortageError | null }>();
// O modal some com animação depois de `shortage` virar null. Título e frase
// saem do último envelope não nulo, para a saída não piscar outro caso com
// "lote undefined" (beta 05/11).
const last = ref<ProductionShortageError | null>(props.shortage);
watch(
  () => props.shortage,
  (value) => {
    if (value) last.value = value;
  },
);
const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [reason: string, proof: string];
  review: [];
}>();

const isMaterial = computed(() => last.value?.code === "material_shortage");
const forcePossibility = computed(() =>
  last.value?.possibilities.find(
    (possibility) => possibility.kind === "force" && possibility.enabled,
  ),
);
const retryPossibility = computed(() =>
  last.value?.possibilities.find(
    (possibility) => possibility.kind === "retry" && possibility.enabled,
  ),
);
const overrideReason = ref("");
const canConfirm = computed(
  () =>
    Boolean(forcePossibility.value?.proof) && overrideReason.value.trim().length > 0,
);

watch(
  () => props.shortage,
  () => {
    overrideReason.value = "";
  },
);

const title = computed(() =>
  isMaterial.value ? "Insumos insuficientes" : "Quantidade não cobre pedidos",
);
const description = computed(() => {
  const ref = last.value?.work_order_ref;
  if (isMaterial.value && forcePossibility.value) {
    return `Faltam insumos para concluir ${ref}. Registre o motivo real da autorização; a identidade do operador e um alerta serão preservados.`;
  }
  if (isMaterial.value) {
    return `Faltam insumos para concluir ${ref}. Peça ao gerente para registrar a entrada do que falta e confirme de novo.`;
  }
  return `O lote ${ref} tem encomendas que dependem dele, e a quantidade informada não cobre todas.`;
});

function confirmOverride() {
  const reason = overrideReason.value.trim();
  if (forcePossibility.value?.proof && reason) {
    emit("confirm", reason, forcePossibility.value.proof);
  }
}
</script>

<template>
  <NuxtModal
    :open="shortage != null"
    :title="title"
    :description="description"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <template #body>
      <div class="flex flex-col gap-3">
        <ul
          v-if="last && last.code === 'material_shortage'"
          class="divide-y rounded-md border text-sm"
        >
          <li
            v-for="item in last.missing"
            :key="item.sku"
            class="flex items-center justify-between gap-2 px-3 py-2"
            data-shortage-item
          >
            <span class="font-medium">{{ item.name || item.sku }}</span>
            <span class="tabular-nums text-muted-foreground">
              precisa
              <b class="text-foreground">{{ formatQtyUnit(item.needed, item.unit) }}</b>
              · tem {{ formatQtyUnit(item.available, item.unit) }} ·
              <span class="text-destructive"
                >faltam {{ formatQtyUnit(item.shortage, item.unit) }}</span
              >
            </span>
          </li>
        </ul>
        <template v-else-if="last && last.code === 'order_shortage'">
          <div class="rounded-md border bg-muted/40 p-3 text-sm">
            <p>
              Encomendado:
              <b class="tabular-nums">{{ last.required }}</b> un. ·
              informado: <b class="tabular-nums">{{ last.requested }}</b> un.
            </p>
            <p class="mt-1 text-muted-foreground">
              Pedidos: {{ last.order_refs.join(", ") }}
            </p>
          </div>
          <p v-if="!forcePossibility" class="text-sm">
            Confira a contagem e informe pelo menos
            <b class="tabular-nums">{{ last.required }}</b> un. Se saiu mesmo
            menos, nada foi registrado: avise quem cuida das encomendas antes de
            confirmar este lote.
          </p>
        </template>

        <NuxtFormField v-if="forcePossibility" label="Motivo da autorização">
          <NuxtTextarea
            v-model="overrideReason"
            :maxlength="500"
            :rows="3"
            required
            class="w-full"
            aria-label="Motivo da autorização para falta de insumos"
            placeholder="Descreva quem autorizou e por quê"
          />
        </NuxtFormField>
      </div>
    </template>

    <template #footer>
      <div class="flex w-full flex-wrap justify-end gap-2">
        <NuxtButton
          color="neutral"
          variant="outline"
          :label="isMaterial || retryPossibility ? 'Cancelar' : 'Entendi'"
          @click="emit('update:open', false)"
        />
        <NuxtButton
          v-if="retryPossibility && !isMaterial && forcePossibility"
          color="neutral"
          variant="outline"
          :label="retryPossibility.label"
          @click="emit('review')"
        />
        <NuxtButton
          v-else-if="retryPossibility && !isMaterial"
          :label="retryPossibility.label"
          @click="emit('review')"
        />
        <NuxtButton
          v-if="forcePossibility"
          color="primary"
          :disabled="!canConfirm"
          :label="forcePossibility.label"
          @click="confirmOverride"
        />
      </div>
    </template>
  </NuxtModal>
</template>
