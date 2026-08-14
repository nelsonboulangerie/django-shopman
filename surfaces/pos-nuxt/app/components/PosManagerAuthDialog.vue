<script setup lang="ts">
// Manager authorization (spec §1.4/§3): a focused PIN screen — like the operator
// lock, but flagged as an AUTHORIZATION — that appears when the review demands
// `requires_manager_approval`. The operator names the manager and keys the PIN on
// the same pad; the orchestrator verifies it (doorman `verify_manager_pin`).
import { formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  open: boolean;
  thresholdQ?: number;
  /** Códigos vindos da review (`approval_reasons`) — dizem POR QUE o gerente foi chamado. */
  reasons?: string[];
  /** Texto pronto, para quem não vem de uma venda (retirada de gaveta). */
  reasonText?: string;
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  authorize: [string, string];
}>();

const username = ref("");
const pin = ref("");
// O motivo sai do servidor, não de um chute da tela: o mesmo diálogo cobre
// desconto acima do teto, exceção de D-1, preço alterado à mão e retirada de
// gaveta. Antes ele afirmava "descontos acima de R$ X" em todos os casos, e o
// gerente autorizava sem saber o que estava assinando.
const REASON_COPY: Record<string, (thresholdQ: number) => string> = {
  discount_over_threshold: (q) => `Desconto acima de ${formatBRL(q)}.`,
  price_override: () => "Preço alterado à mão.",
};
const reason = computed(() => {
  if (props.reasonText) return props.reasonText;
  const listed = (props.reasons ?? [])
    .map((code) => REASON_COPY[code]?.(props.thresholdQ ?? 0))
    .filter(Boolean);
  if (listed.length) return listed.join(" ");
  return "Esta operação precisa da autorização de um gerente.";
});

// Campos limpos a cada abertura. Quando o servidor recusa, some só o PIN: o nome
// do gerente continua na tela, senão ele redigita o próprio nome a cada tentativa.
watch(() => props.open, (open) => {
  if (!open) return;
  pin.value = "";
  // Reabertura por recusa preserva o nome; abertura nova começa em branco.
  if (!props.error) username.value = "";
});
watch(() => props.error, (e) => { if (e) pin.value = ""; });

function confirm() {
  if (!username.value.trim() || pin.value.length === 0 || props.busy) return;
  emit("authorize", username.value.trim(), pin.value);
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-warning/40 bg-warning/10 text-amber-600">
          <Icon name="lucide:shield-check" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">Autorização do gerente</UiDialogTitle>
        <UiDialogDescription>{{ reason }}</UiDialogDescription>
      </UiDialogHeader>

      <div class="flex flex-col items-center gap-4 pb-1">
        <UiInput
          v-model="username"
          placeholder="Nome do gerente"
          autocomplete="off"
          class="h-11 w-full max-w-60 text-center text-base"
          autofocus
        />
        <p v-if="error" class="text-center text-sm font-medium text-destructive" role="alert">{{ error }}</p>
        <PosPinPad v-model="pin" :disabled="busy" @submit="confirm" />
        <p class="text-center text-xs text-muted-foreground">Informe o gerente e o PIN, depois confirme.</p>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
