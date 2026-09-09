<script setup lang="ts">
// Material/order shortage modal. Renders the structured shortage envelope the API
// returns (409) when a finish/plan would consume more than is available, or leave
// committed orders uncovered. For a material shortage the operator can override
// (force=1) only when the server advertises that possibility; an order shortage
// is informational (re-plan with a higher quantity).
import type { ProductionShortageError } from "~/types/production";

const props = defineProps<{ shortage: ProductionShortageError | null }>();
const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [reason: string, proof: string];
}>();

const isMaterial = computed(() => props.shortage?.code === "material_shortage");
const forcePossibility = computed(() =>
  props.shortage?.possibilities.find(
    (possibility) => possibility.kind === "force" && possibility.enabled,
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
          <Icon name="lucide:triangle-alert" class="size-5 text-amber-600" />
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
            >A nova quantidade de {{ shortage?.work_order_ref }} deixa pedidos
            descobertos.</template
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
              <span class="text-destructive dark:text-orange-400"
                >faltam {{ item.shortage }}</span
              >
            </span>
          </li>
        </ul>
      </template>
      <template v-else-if="shortage && shortage.code === 'order_shortage'">
        <div class="rounded-md border bg-muted/40 p-3 text-sm">
          <p>
            Comprometido:
            <b class="tabular-nums">{{ shortage.required }}</b> un. ·
            solicitado: <b class="tabular-nums">{{ shortage.requested }}</b> un.
          </p>
          <p class="mt-1 text-muted-foreground">
            Pedidos: {{ shortage.order_refs.join(", ") }}
          </p>
        </div>
      </template>

      <label v-if="forcePossibility" class="grid gap-1.5 text-sm">
        <span class="font-medium">Motivo da autorização</span>
        <textarea
          v-model="overrideReason"
          maxlength="500"
          rows="3"
          required
          class="rounded-md border bg-background px-3 py-2"
          aria-label="Motivo da autorização para falta de insumos"
          placeholder="Descreva quem autorizou e por quê"
        />
      </label>

      <UiDialogFooter>
        <button
          type="button"
          class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
          @click="emit('update:open', false)"
        >
          {{ isMaterial ? "Cancelar" : "Entendi" }}
        </button>
        <button
          v-if="forcePossibility"
          type="button"
          class="rounded-md border border-transparent bg-warning px-3 py-2 text-sm font-semibold text-warning-foreground transition hover:bg-warning/90"
          :disabled="!canConfirm"
          :class="{ 'cursor-not-allowed opacity-50': !canConfirm }"
          @click="confirmOverride"
        >
          {{ forcePossibility.label }}
        </button>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
