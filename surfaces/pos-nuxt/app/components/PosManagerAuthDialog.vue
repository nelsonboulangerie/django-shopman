<script setup lang="ts">
// Autorização do gerente (spec §1.4/§3): uma tela focada de PIN — como o lock do
// operador, mas marcada como AUTORIZAÇÃO — que sobe quando a review exige
// `requires_manager_approval`.
//
// O gerente é ESCOLHIDO NUMA LISTA, não digitado. O nome nunca foi decoração: o
// servidor resolve o usuário por `username`, confere `cashman.adjust_shift`
// e valida o PIN contra a credencial daquela pessoa (`PinCredential`, por usuário).
// Nome digitado erra, e nome errado grava a assinatura errada em
// `Entry.approved_by` do livro do turno — justamente a segunda assinatura que a
// sangria existe para ter. O contrato do servidor segue `{username, pin}`; o que mudou é
// só COMO a tela descobre o username.
//
// O campo de texto continua vivo como ÚNICA porta quando a lista chega vazia
// (leitura negada, nenhum gerente com PIN provisionado). Esconder a única porta
// deixaria o balcão sem saída no meio de uma sangria.
import { canAuthorize, managerAuthReason } from "~/presentation/managerAuth";
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
  authorize: [string, string];
}>();

const picked = ref<POSManagerProjection | null>(null);
const typedUsername = ref("");
const pin = ref("");

const managers = computed(() => props.managers ?? []);
const hasList = computed(() => managers.value.length > 0);
const username = computed(() => (picked.value?.username ?? typedUsername.value).trim());
// Com lista, o pad só aparece depois de escolher quem assina: o nome fica na tela
// acima do teclado, para o gerente ver o que está prestes a assinar em seu nome.
const showPad = computed(() => !hasList.value || picked.value !== null);
const reason = computed(() =>
  managerAuthReason({
    reasonText: props.reasonText,
    reasons: props.reasons,
    thresholdQ: props.thresholdQ,
  }),
);

// Campos limpos a cada abertura. Quando o servidor recusa, some só o PIN: quem foi
// escolhido continua escolhido, senão o gerente reescolheria o próprio nome a cada
// erro de digitação do teclado numérico.
watch(() => props.open, (open) => {
  if (!open) return;
  pin.value = "";
  if (props.error) return; // reabertura por recusa preserva a escolha
  picked.value = null;
  typedUsername.value = "";
});
watch(() => props.error, (e) => { if (e) pin.value = ""; });

function pick(manager: POSManagerProjection) {
  picked.value = manager;
  pin.value = "";
}

function unpick() {
  picked.value = null;
  pin.value = "";
}

function confirm() {
  if (props.busy || !canAuthorize(username.value, pin.value)) return;
  emit("authorize", username.value, pin.value);
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
        <!-- Escolha do gerente -->
        <template v-if="hasList && !picked">
          <p class="text-center text-sm text-muted-foreground">Quem autoriza?</p>
          <div class="grid w-full grid-cols-2 gap-2" role="group" aria-label="Gerentes">
            <UiButton
              v-for="manager in managers"
              :key="manager.username"
              variant="outline"
              class="h-12 justify-start px-3 text-left text-sm font-medium"
              @click="pick(manager)"
            >
              {{ manager.name }}
            </UiButton>
          </div>
          <p v-if="error" class="text-center text-sm font-medium text-destructive" role="alert">{{ error }}</p>
        </template>

        <!-- PIN. Com lista, o gerente escolhido fica visível e trocável. -->
        <template v-if="showPad">
          <div v-if="picked" class="grid w-full gap-1">
            <UiButton
              variant="ghost"
              size="sm"
              class="justify-start px-2 text-sm text-muted-foreground"
              @click="unpick"
            >
              <Icon name="lucide:chevron-left" class="size-4" />
              Trocar gerente
            </UiButton>
            <p class="text-center text-sm font-semibold">{{ picked.name }}</p>
          </div>
          <UiInput
            v-else
            v-model="typedUsername"
            placeholder="Nome do gerente"
            aria-label="Nome do gerente"
            autocomplete="off"
            class="h-11 w-full max-w-60 text-center text-base"
            autofocus
          />
          <p v-if="error" class="text-center text-sm font-medium text-destructive" role="alert">{{ error }}</p>
          <PosPinPad v-model="pin" :disabled="busy" @submit="confirm" />
          <p class="text-center text-xs text-muted-foreground">
            {{ picked ? "Digite o PIN e confirme." : "Informe o gerente e o PIN, depois confirme." }}
          </p>
        </template>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
