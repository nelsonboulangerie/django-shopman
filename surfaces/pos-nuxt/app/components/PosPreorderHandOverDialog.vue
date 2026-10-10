<script setup lang="ts">
// Receber e entregar uma encomenda no balcão — um diálogo, um toque de
// confirmação. Com saldo: a forma (dinheiro com troco, ou cartão na maquininha)
// e o valor já prontos; sem saldo: só a confirmação da entrega. O que falta
// receber, e se pode entregar, vem do servidor (`hand_over`); aqui mora a
// escolha da forma e a conta do troco (`presentation/preorderActions`).
import {
  COUNTER_METHODS,
  changeLine,
  checkReceive,
  handOverBody,
  initialMethod,
  receiveConfirmLabel,
  type HandOverBody,
} from "~/presentation/preorderActions";
import type { CounterMethod, PreorderHandOver } from "~/types/preorders";

const props = defineProps<{
  open: boolean;
  handOver: PreorderHandOver;
  customerName: string;
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [HandOverBody];
}>();

const method = ref<CounterMethod>(initialMethod(props.handOver));
const received = ref("");

// Cada abertura começa do combinado: a forma que o cliente escolheu e o campo
// de dinheiro vazio (= valor exato, sem troco).
watch(() => props.open, (open) => {
  if (!open) return;
  method.value = initialMethod(props.handOver);
  received.value = "";
});

const check = computed(() => checkReceive(method.value, props.handOver.amount_q, received.value));
const methodOptions = COUNTER_METHODS.map((option) => ({ value: option.key, label: option.label }));

function confirm() {
  if (props.busy || !check.value.ok) return;
  emit("confirm", handOverBody(props.handOver, method.value, check.value));
}
</script>

<template>
  <NuxtModal
    :open="open"
    :title="handOver.needs_payment ? 'Receber e entregar' : 'Entregar a encomenda'"
    :description="handOver.needs_payment
      ? `Falta receber ${handOver.amount_display} de ${customerName}. A encomenda é entregue assim que o pagamento for registrado.`
      : `A encomenda de ${customerName} já está paga. Confirme a entrega.`"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <form class="grid gap-4" data-preorder-hand-over-dialog @submit.prevent="confirm">
        <NuxtAlert
          v-if="handOver.needs_payment && handOver.digital_charge_notice"
          color="warning"
          variant="subtle"
          icon="i-lucide-link-2-off"
          :title="handOver.digital_charge_notice"
          data-preorder-digital-charge-notice
        />

        <template v-if="handOver.needs_payment">
          <NuxtFormField label="Forma de pagamento">
            <NuxtRadioGroup
              v-model="method"
              orientation="horizontal"
              variant="card"
              :items="methodOptions"
              data-preorder-method
            />
          </NuxtFormField>

          <NuxtFormField v-if="method === 'cash'" label="Valor recebido em dinheiro">
            <NuxtInput
              v-model="received"
              class="w-full"
              inputmode="decimal"
              autocomplete="off"
              :ui="{ base: 'tabular-nums' }"
              :placeholder="handOver.amount_display.replace('R$ ', '')"
              data-preorder-received
            />
            <template #help>
              <span class="tabular-nums" :class="check.ok ? 'text-muted' : 'text-error'" data-preorder-change>
                {{ check.ok ? changeLine(check.changeQ) : check.message }}
              </span>
            </template>
          </NuxtFormField>
          <p v-else class="text-sm text-muted">
            Passe {{ handOver.amount_display }} na maquininha e confirme quando o pagamento for aprovado.
          </p>
        </template>

        <div class="flex justify-end gap-2">
          <NuxtButton type="button" color="neutral" variant="outline" label="Voltar" @click="emit('update:open', false)" />
          <NuxtButton
            type="submit"
            :disabled="busy || !check.ok"
            :loading="busy"
            :label="handOver.needs_payment ? receiveConfirmLabel(method, handOver.amount_display) : 'Entregar'"
            data-preorder-hand-over-confirm
          />
        </div>
      </form>
    </template>
  </NuxtModal>
</template>
