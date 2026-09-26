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
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-md" data-preorder-hand-over-dialog>
      <UiDialogHeader>
        <UiDialogTitle>{{ handOver.needs_payment ? "Receber e entregar" : "Entregar a encomenda" }}</UiDialogTitle>
        <UiDialogDescription>
          <template v-if="handOver.needs_payment">
            Falta receber {{ handOver.amount_display }} de {{ customerName }}. A encomenda é entregue assim que o pagamento for registrado.
          </template>
          <template v-else>
            A encomenda de {{ customerName }} já está paga. Confirme a entrega.
          </template>
        </UiDialogDescription>
      </UiDialogHeader>

      <form class="grid gap-4" @submit.prevent="confirm">
        <template v-if="handOver.needs_payment">
          <fieldset class="grid gap-2">
            <legend class="text-sm font-medium">Forma de pagamento</legend>
            <UiRadioGroup
              v-model="method"
              label="Forma de pagamento"
              orientation="horizontal"
              :options="methodOptions"
              data-preorder-method
            />
          </fieldset>

          <label v-if="method === 'cash'" class="grid gap-1.5">
            <span class="text-sm font-medium">Valor recebido em dinheiro</span>
            <UiInput
              v-model="received"
              inputmode="decimal"
              autocomplete="off"
              class="h-11 text-base tabular-nums"
              :placeholder="handOver.amount_display.replace('R$ ', '')"
              data-preorder-received
            />
            <span class="text-sm tabular-nums" :class="check.ok ? 'text-muted-foreground' : 'text-destructive'" data-preorder-change>
              {{ check.ok ? changeLine(check.changeQ) : check.message }}
            </span>
          </label>
          <p v-else class="text-sm text-muted-foreground">
            Passe {{ handOver.amount_display }} na maquininha e confirme quando o pagamento for aprovado.
          </p>
        </template>

        <UiDialogFooter>
          <UiButton type="button" variant="outline" @click="emit('update:open', false)">Voltar</UiButton>
          <UiButton type="submit" :disabled="busy || !check.ok" :loading="busy" data-preorder-hand-over-confirm>
            {{ handOver.needs_payment ? receiveConfirmLabel(method, handOver.amount_display) : "Entregar" }}
          </UiButton>
        </UiDialogFooter>
      </form>
    </UiDialogContent>
  </UiDialog>
</template>
