<script setup lang="ts">
// Autorização do gerente (spec §1.4/§3): a tela focada que sobe quando a review
// exige `requires_manager_approval`.
//
// ⚠️ A identificação NÃO mora aqui. Crachá, lista e teclado de PIN vêm do
// `OperatorIdentify` do operator-kit — a MESMA peça que a tela de bloqueio usa.
//
// Antes eram dois componentes desenhando o mesmo seletor e o mesmo teclado, e o
// custo não era código repetido: era que só um deles sabia ler crachá. Sangria e
// pedido de troco são a hora em que o gerente mais aparece no balcão, e era
// exatamente ali que o crachá no pescoço dele não servia para nada.
//
// O gerente é ESCOLHIDO NUMA LISTA, não digitado. O nome nunca foi decoração: o
// servidor resolve o usuário por `username`, confere `cashman.adjust_shift` e
// valida contra a credencial daquela pessoa. Nome errado grava a assinatura
// errada em `Entry.approved_by` — justamente a segunda assinatura que a sangria
// existe para ter.
//
// O campo de texto continua vivo como ÚNICA porta quando a lista chega vazia
// (leitura negada, nenhum gerente com PIN provisionado): esconder a única porta
// deixaria o balcão sem saída no meio de uma sangria.
import { managerAuthReason } from "~/presentation/managerAuth";
import type { POSManagerProjection } from "~/types/pos";

const props = defineProps<{
  open: boolean;
  thresholdQ?: number;
  /** Códigos vindos da review (`approval_reasons`) — dizem POR QUE o gerente foi chamado. */
  reasons?: string[];
  /** Texto pronto, para quem não vem de uma venda (retirada de gaveta). */
  reasonText?: string;
  /** Quem pode assinar (`POSProjection.managers`). Vazio cai no campo livre. */
  managers?: POSManagerProjection[];
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  /** PIN: `(username, pin)`. Crachá: `(  "", "", token)`. Ver `authorizePayload`. */
  authorize: [string, string];
  authorizeBadge: [string];
}>();

const identify = ref<{ reset: (keepPicked?: boolean) => void } | null>(null);

const managers = computed(() => props.managers ?? []);
const reason = computed(() =>
  managerAuthReason({
    reasonText: props.reasonText,
    reasons: props.reasons,
    thresholdQ: props.thresholdQ,
  }),
);

// Campos limpos a cada abertura. Quando o servidor recusa, some só o PIN: quem
// foi escolhido continua escolhido, senão o gerente reescolheria o próprio nome
// a cada erro de digitação.
watch(() => props.open, (open) => {
  if (!open) return;
  identify.value?.reset(Boolean(props.error));
});

function onPin(payload: { username: string; pin: string }) {
  if (props.busy || !payload.username || !payload.pin) return;
  emit("authorize", payload.username, payload.pin);
}

function onBadge(token: string) {
  if (props.busy) return;
  emit("authorizeBadge", token);
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-warning/40 bg-warning/10 text-amber-600 dark:text-amber-400">
          <Icon name="lucide:shield-check" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">Autorização do gerente</UiDialogTitle>
        <UiDialogDescription>{{ reason }}</UiDialogDescription>
      </UiDialogHeader>

      <div class="flex flex-col items-center gap-4 pb-1">
        <OperatorIdentify
          ref="identify"
          :people="managers"
          :busy="busy"
          :error="error"
          :badge-enabled="open"
          allow-typed-name
          name-label="Nome do gerente"
          prompt="Quem autoriza?"
          change-label="Trocar gerente"
          @pin="onPin"
          @badge="onBadge"
        />
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
