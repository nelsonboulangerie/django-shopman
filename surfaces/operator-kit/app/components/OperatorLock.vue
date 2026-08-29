<script setup lang="ts">
// Operator lock overlay (Opção C). Shown when the gate is on and nobody is
// operating. Two ways in: scan a badge (a barcode scanner types the token fast
// and ends with Enter, captured anywhere on the overlay), or pick yourself and
// type your PIN. The surface permission scopes who appears + who may unlock.
//
// A identificação (crachá, lista, PIN) mora no `OperatorIdentify`, compartilhado
// com o diálogo de autorização do gerente. Aqui fica só o que é do BLOQUEIO: a
// moldura de tela cheia e os dois fluxos de troca de PIN.
//
// Two PIN-change flows share this overlay: a FORCED change after a manager reset
// (must_change — the operator can't operate until they rotate the temp PIN), and
// a VOLUNTARY "Trocar PIN" from the pad. Both prove the current PIN (the backend
// authorizes on that), so no manager is needed for a routine change.
// Import explícito (não auto-import): o POS mantém um lock próprio (usePosOperatorLock)
// e este overlay é construído SOBRE o composable do kit, independente do app hospedeiro.
import { useOperatorLock } from "../composables/useOperatorLock";
import type { OperatorCard } from "../types/operator";
import type { IdentifiablePerson } from "./OperatorIdentify.vue";

const props = defineProps<{ perm: string }>();

const {
  eligible,
  loadEligible,
  unlock,
  changePin,
  changeError,
  reportBadgeLost,
  lostBadgeError,
  operator,
  mustChange,
  busy,
} = useOperatorLock(props.perm);

// Quem foi escolhido no `OperatorIdentify`. Guardado aqui porque a troca
// voluntária de PIN precisa saber de QUEM é o PIN que está sendo trocado.
const picked = ref<OperatorCard | null>(null);
const changing = ref(false); // voluntary "Trocar PIN" mode (an operator is picked)
const lostBadge = ref(false); // "Perdi meu crachá" mode
const identify = ref<{ reset: (keepPicked?: boolean) => void } | null>(null);

onMounted(loadEligible);

async function onPin(payload: { person: IdentifiablePerson | null; username: string; pin: string }) {
  // A peça compartilhada devolve o mínimo comum (`username`, `name`). Aqui o
  // bloqueio precisa do ID numérico, então recupera o card completo da lista —
  // é o que evita a peça ter de conhecer o formato de cada consumidor.
  const card = eligible.value.find((op) => op.username === payload.username) ?? null;
  if (!card) return;
  picked.value = card;
  const ok = await unlock({ operatorId: card.id, pin: payload.pin });
  // Recusa apaga o PIN e mantém a pessoa: ela erra o dedo, não a identidade.
  if (!ok) identify.value?.reset(true);
}

function startChange() {
  changing.value = true;
}

// ── Voluntary change (an operator picked themselves and taps "Trocar PIN") ──
async function submitVoluntaryChange(payload: {
  currentPin: string;
  newPin: string;
}) {
  if (!picked.value) return;
  const ok = await changePin({ operatorId: picked.value.id, ...payload });
  if (ok) {
    changing.value = false;
    identify.value?.reset(true);
    useSonner.success("PIN atualizado. Entre com o novo PIN.");
  }
}

// ── "Perdi meu crachá" ──
// Reusa o `OperatorIdentify` em vez de um seletor próprio: mesma lista, mesmo
// pad, e o leitor de crachá desligado — quem está aqui não tem o crachá.
async function submitLostBadge(payload: { username: string; pin: string }) {
  const card = eligible.value.find((op) => op.username === payload.username);
  if (!card) return;
  const ok = await reportBadgeLost({ operatorId: card.id, pin: payload.pin });
  if (ok) {
    lostBadge.value = false;
    useSonner.success("Crachá invalidado. Seu PIN continua valendo.");
  }
}

// ── Forced change (must_change after a manager reset) ──
async function submitForcedChange(payload: {
  currentPin: string;
  newPin: string;
}) {
  if (!operator.value) return;
  const ok = await changePin({ operatorId: operator.value.id, ...payload });
  if (ok) useSonner.success("PIN atualizado.");
  // success → session refresh clears must_change → the overlay closes on its own.
}
</script>

<template>
  <!-- `data-operator-lock`: marca DOM estável para as telas por baixo saberem que
       o terminal está travado (os atalhos globais do PDV se desligam por ela). -->
  <div
    data-operator-lock
    class="fixed inset-0 z-[100] grid place-items-center bg-background/95 p-4 backdrop-blur-sm"
  >
    <div class="w-full max-w-md rounded-xl border bg-card p-5 shadow-lg">
      <!-- Forced change: manager reset the operator's PIN; rotate before operating. -->
      <OperatorPinChange
        v-if="mustChange && operator"
        :operator-name="operator.name"
        forced
        :busy="busy"
        :error="changeError"
        @submit="submitForcedChange"
        @cancel="() => {}"
      />

      <!-- Voluntary change: the picked operator rotates their own PIN. -->
      <OperatorPinChange
        v-else-if="changing && picked"
        :operator-name="picked.name"
        :busy="busy"
        :error="changeError"
        @submit="submitVoluntaryChange"
        @cancel="changing = false"
      />

      <!-- "Perdi meu crachá": o crachá morre agora. A tela É a confirmação —
           diz o que acontece e só age depois do PIN. -->
      <template v-else-if="lostBadge">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="lucide:badge-x" class="size-5 text-muted-foreground" />
          <h2 class="text-lg font-bold">Perdi meu crachá</h2>
        </div>
        <div class="mb-4 space-y-1 rounded-lg border border-dashed p-3 text-sm">
          <p>Seu crachá para de funcionar agora.</p>
          <p>Seu PIN continua valendo — você segue trabalhando.</p>
          <p class="text-muted-foreground">Um gerente emite outro crachá.</p>
        </div>

        <!-- O erro é desenhado pelo `OperatorIdentify` (que também limpa o PIN
             quando ele muda): repeti-lo aqui daria a mesma frase duas vezes. -->
        <OperatorIdentify
          :people="eligible"
          :busy="busy"
          :badge-enabled="false"
          :error="lostBadgeError"
          prompt="Quem perdeu o crachá?"
          change-label="Trocar operador"
          @pin="submitLostBadge"
        />

        <button
          type="button"
          class="mt-3 inline-flex w-full items-center justify-center text-sm text-muted-foreground hover:text-foreground"
          @click="lostBadge = false"
        >
          Cancelar
        </button>
      </template>

      <template v-else>
        <!-- ⚠️ Esta tela se confunde com a AUTORIZAÇÃO DO GERENTE, não com o
             login: as duas aparecem no meio do expediente, as duas são um
             teclado de PIN e as duas interrompem quem está atendendo. A linha
             abaixo é metade de um par — a outra metade, no diálogo de
             autorização, diz "Você continua como <fulano>".

               aqui         → você ASSUME o balcão (a sessão troca)
               autorização  → você CONTINUA quem era (o gerente só assina) -->
        <div class="mb-4 flex items-center gap-2">
          <Icon name="lucide:lock" class="size-5 text-muted-foreground" />
          <h2 class="text-lg font-bold">Identifique-se para operar</h2>
        </div>
        <p class="-mt-3 mb-4 text-sm text-muted-foreground">Você assume o balcão.</p>

        <div
          v-if="!eligible.length"
          class="grid place-items-center gap-1.5 rounded-lg border border-dashed py-8 text-center text-muted-foreground"
        >
          <Icon name="lucide:user-x" class="size-6" />
          <p class="text-sm">Nenhum operador habilitado para esta tela.</p>
        </div>

        <!-- A identificação inteira (crachá, lista, PIN) mora no
             `OperatorIdentify`, e o diálogo de autorização do gerente usa a
             MESMA peça. Aqui sobra só o que é do bloqueio: a moldura de tela
             cheia e os dois fluxos de troca de PIN. -->
        <OperatorIdentify
          v-else
          ref="identify"
          :people="eligible"
          :busy="busy"
          :badge-enabled="!changing && !mustChange && !lostBadge"
          prompt="Quem está operando?"
          change-label="Trocar operador"
          @pin="onPin"
          @badge="(token: string) => unlock({ badge: token })"
        >
          <template #footer>
            <!-- Discreto, mas não escondido: quem perdeu o crachá precisa achar
                 sozinho, então é texto legível ao lado do irmão, e não um menu. -->
            <div class="flex items-center justify-center gap-4">
              <button
                type="button"
                class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                @click="startChange"
              >
                <Icon name="lucide:key-round" class="size-4" /> Trocar meu PIN
              </button>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                @click="lostBadge = true"
              >
                <Icon name="lucide:badge-x" class="size-4" /> Perdi meu crachá
              </button>
            </div>
          </template>
        </OperatorIdentify>
      </template>
    </div>
  </div>
</template>
