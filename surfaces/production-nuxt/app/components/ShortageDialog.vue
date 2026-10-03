<script setup lang="ts">
// Material/order shortage modal. Renders the structured shortage envelope the API
// returns (409) when a finish/plan would consume more than is available, or leave
// committed orders uncovered. For a material shortage the operator can override
// (force=1) only when the server advertises that possibility. An order shortage
// offers "retry" (o operador volta ao número que digitou e corrige); confirmar o
// produzido abaixo das encomendas nunca é forçável, então ali o caminho é só esse.
import type { ProductionShortageError } from "~/types/production";

const props = defineProps<{ shortage: ProductionShortageError | null }>();
const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [reason: string, proof: string];
  review: [];
}>();

const isMaterial = computed(() => props.shortage?.code === "material_shortage");
const forcePossibility = computed(() =>
  props.shortage?.possibilities.find(
    (possibility) => possibility.kind === "force" && possibility.enabled,
  ),
);
const retryPossibility = computed(() =>
  props.shortage?.possibilities.find(
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

function confirmOverride() {
  const reason = overrideReason.value.trim();
  if (forcePossibility.value?.proof && reason) {
    emit("confirm", reason, forcePossibility.value.proof);
  }
}
</script>

<template>
  <UiDialog
    :open="shortage != null"
    @update:open="(v) => emit('update:open', v)"
  >
    <UiDialogContent class="sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle class="flex items-center gap-2">
          <Icon name="lucide:triangle-alert" class="size-5 text-warning" />
          {{
            isMaterial
              ? "Insumos insuficientes"
              : "Quantidade não cobre pedidos"
          }}
        </UiDialogTitle>
        <UiDialogDescription>
          <template v-if="isMaterial && forcePossibility"
            >Faltam insumos para concluir {{ shortage?.work_order_ref }}.
            Registre o motivo real da autorização; a identidade do operador e um
            alerta serão preservados.</template
          >
          <template v-else-if="isMaterial"
            >Faltam insumos para concluir {{ shortage?.work_order_ref }}. Esta
            operação não está autorizada a ignorar a falta.</template
          >
          <template v-else
            >O lote {{ shortage?.work_order_ref }} tem encomendas que dependem
            dele, e a quantidade informada não cobre todas.</template
          >
        </UiDialogDescription>
      </UiDialogHeader>

      <template v-if="shortage && shortage.code === 'material_shortage'">
        <ul class="divide-y rounded-md border text-sm">
          <li
            v-for="item in shortage.missing"
            :key="item.sku"
            class="flex items-center justify-between gap-2 px-3 py-2"
          >
            <span class="font-medium">{{ item.sku }}</span>
            <span class="tabular-nums text-muted-foreground">
              precisa <b class="text-foreground">{{ item.needed }}</b> · tem
              {{ item.available }} ·
              <span class="text-destructive"
                >faltam {{ item.shortage }}</span
              >
            </span>
          </li>
        </ul>
      </template>
      <template v-else-if="shortage && shortage.code === 'order_shortage'">
        <div class="rounded-md border bg-muted/40 p-3 text-sm">
          <p>
            Encomendado:
            <b class="tabular-nums">{{ shortage.required }}</b> un. ·
            informado: <b class="tabular-nums">{{ shortage.requested }}</b> un.
          </p>
          <p class="mt-1 text-muted-foreground">
            Pedidos: {{ shortage.order_refs.join(", ") }}
          </p>
        </div>
        <p v-if="!forcePossibility" class="text-sm">
          Confira a contagem e informe pelo menos
          <b class="tabular-nums">{{ shortage.required }}</b> un. Se saiu mesmo
          menos, nada foi registrado: avise quem cuida das encomendas antes de
          confirmar este lote.
        </p>
      </template>

      <label v-if="forcePossibility" class="grid gap-1.5 text-sm">
        <span class="font-medium">Motivo da autorização</span>
        <UiTextarea
          v-model="overrideReason"
          :maxlength="500"
          :rows="3"
          required
          class="bg-background"
          aria-label="Motivo da autorização para falta de insumos"
          placeholder="Descreva quem autorizou e por quê"
        />
      </label>

      <UiDialogFooter>
        <UiButton
          type="button"
          variant="outline"
          @click="emit('update:open', false)"
        >
          {{ isMaterial || retryPossibility ? "Cancelar" : "Entendi" }}
        </UiButton>
        <UiButton
          v-if="retryPossibility && !isMaterial"
          type="button"
          :variant="forcePossibility ? 'outline' : 'default'"
          @click="emit('review')"
        >
          {{ retryPossibility.label }}
        </UiButton>
        <UiButton
          v-if="forcePossibility"
          type="button"
          class="border-transparent bg-warning text-warning-foreground hover:bg-warning/90"
          :disabled="!canConfirm"
          @click="confirmOverride"
        >
          {{ forcePossibility.label }}
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
