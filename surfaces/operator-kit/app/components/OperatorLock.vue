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
import { alertActions } from "../utils/alertActions";
import type { OperatorCard } from "../types/operator";
import type { IdentifiablePerson } from "./OperatorIdentify.vue";

const props = withDefaults(
  defineProps<{
    perm: string;
    /** A linha abaixo do título. Neutra por padrão (vale em qualquer app); o app
     *  que tiver frase melhor para o seu momento passa a dele (beta 05/11). */
    subtitle?: string;
  }>(),
  { subtitle: "Você assume este dispositivo." },
);

const {
  eligible,
  eligibleStatus,
  loadEligible,
  unlock,
  unlockError,
  changePin,
  changeError,
  reportBadgeLost,
  lostBadgeError,
  operator,
  mustChange,
  busy,
} = useOperatorLock(props.perm);

// Quem está escolhido no `OperatorIdentify`, AGORA (o evento `pick`). Guardado
// aqui porque a troca voluntária de PIN precisa saber de QUEM é o PIN que está
// sendo trocado. Era preenchido só no PIN digitado: "Trocar meu PIN" logo depois
// de escolher o nome não fazia nada, deixava a troca ligada, e o próximo PIN
// errado abria a troca do PIN de quem tinha sido escolhido ANTES (beta 05/11,
// CEN-02 e PDV-03).
const picked = ref<OperatorCard | null>(null);
const changing = ref(false); // voluntary "Trocar PIN" mode (an operator is picked)
const lostBadge = ref(false); // "Perdi meu crachá" mode
const withPassword = ref(false); // "Entrar com senha" (quem não tem PIN aqui)
const identify = ref<{ reset: (keepPicked?: boolean) => void } | null>(null);

onMounted(loadEligible);

// A lista ainda chegando não é lista vazia (beta 05/11, PDV2-16). A segunda trava
// em diante já abre com a lista de antes, e aí não há o que esperar.
const eligibleLoading = computed(
  () => !eligible.value.length && ["idle", "pending"].includes(eligibleStatus.value),
);
const eligibleFailed = computed(
  () => !eligible.value.length && eligibleStatus.value === "error",
);

function onPick(person: IdentifiablePerson | null) {
  picked.value = person
    ? (eligible.value.find((op) => op.username === person.username) ?? null)
    : null;
  // Trocou de pessoa (ou voltou à lista): a troca de PIN e a recusa eram da outra.
  changing.value = false;
  unlockError.value = "";
}

// ── O teclado é da trava desde o primeiro instante ──
// A trava sobe por cima de uma tela viva: no PDV, por ociosidade, com a busca de
// produto focada (ela nasce com `autofocus`). O foco ficava lá atrás, e o PIN
// digitado sem tocar na tela não chegava à identificação: era preciso tocar no
// overlay primeiro para "pegar" o teclado (dono, 03/10/2026). A captura já não
// entrega tecla a campo de fora da moldura (`useIdentityCapture`, `frame`); aqui
// a trava também TOMA o foco, para nada lá atrás reagir (Tab, letras, o cursor
// piscando na busca). E toma de novo quando a janela volta a ter foco: o kiosk
// que ficou atrás de outra janela, ou a aba que voltou a ficar visível.
const overlay = ref<HTMLElement | null>(null);

function claimFocus() {
  const el = overlay.value;
  if (!el || typeof document === "undefined") return;
  const active = document.activeElement as HTMLElement | null;
  // Foco já dentro da trava (um campo da troca de PIN, um botão) é do operador.
  if (active && active !== document.body && el.contains(active)) return;
  active?.blur?.();
  el.focus({ preventScroll: true });
}

function onVisibility() {
  if (document.visibilityState === "visible") claimFocus();
}

onMounted(() => {
  claimFocus();
  window.addEventListener("focus", claimFocus);
  document.addEventListener("visibilitychange", onVisibility);
});
onBeforeUnmount(() => {
  window.removeEventListener("focus", claimFocus);
  document.removeEventListener("visibilitychange", onVisibility);
});

async function onPin(payload: {
  person: IdentifiablePerson | null;
  username: string;
  pin: string;
}) {
  // A peça compartilhada devolve o mínimo comum (`username`, `name`). Aqui o
  // bloqueio precisa do ID numérico, então recupera o card completo da lista —
  // é o que evita a peça ter de conhecer o formato de cada consumidor.
  const card =
    eligible.value.find((op) => op.username === payload.username) ?? null;
  if (!card) return;
  const ok = await unlock({ operatorId: card.id, pin: payload.pin });
  // Recusa apaga o PIN e mantém a pessoa: ela erra o dedo, não a identidade.
  if (!ok) identify.value?.reset(true);
}

// As duas portas do rodapé da trava, só texto: discretas, e o nome inteiro cabe
// na coluna do teclado. Apertou, "Trocar meu PIN" cai para o curto da própria
// ação; sem ícone, o último texto quebra linha em vez de virar símbolo mudo.
const footerActions = [
  { label: "Trocar meu PIN", shortLabel: "Trocar PIN" },
  { label: "Perdi meu crachá" },
] as const;

function startChange() {
  // O botão só existe com alguém escolhido (mora no rodapé do teclado). A guarda
  // fica para a troca nunca ligar sem dono.
  if (!picked.value) return;
  changeError.value = "";
  changing.value = true;
}

// Sair da troca remonta a identificação do zero (lista de nomes): a escolha de
// antes não pode ficar guardada aqui como se ainda valesse.
function cancelChange() {
  changing.value = false;
  changeError.value = "";
  picked.value = null;
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
    picked.value = null;
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
  <!-- `tabindex="-1"`: a moldura recebe o foco por programa (ver `claimFocus`)
       sem entrar na ordem do Tab, e sem anel visível (não é um controle). -->
  <div
    ref="overlay"
    data-operator-lock
    tabindex="-1"
    class="fixed inset-0 top-[var(--operator-offline-inset,0px)] outline-none z-[100] grid place-items-center overflow-y-auto bg-background/95 p-4 backdrop-blur-sm"
  >
    <!-- O cartão tem a largura do teclado: a lista de nomes, o campo do PIN, o
         teclado e os avisos são UMA coluna e batem borda com borda (dono,
         10/10/2026). -->
    <NuxtCard class="w-full max-w-xs">
      <!-- Tela baixa (até 700 px de altura, o celular com a barra do navegador):
           sem o cadeado e com respiro menor, para a trava caber sem rolar. -->
      <div class="grid gap-5 [@media(max-height:43.75rem)]:gap-3">
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
        @cancel="cancelChange"
      />

      <!-- "Entrar com senha": quem não tem PIN nesta tela (o dono, alguém de
           outra equipe) entra pelo usuário e senha, sem sair da trava. Antes a
           única saída era abrir o app em outro endereço (beta 05/11, BI-09). -->
      <template v-else-if="withPassword">
        <OperatorLoginForm
          heading
          title="Entrar com senha"
          description="Para quem não tem PIN nesta tela."
          icon="i-lucide-key-round"
          login-url="/api/v1/backstage/operator/login/"
        />
        <div class="flex justify-center">
          <NuxtButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-chevron-left"
            label="Voltar"
            @click="withPassword = false"
          />
        </div>
      </template>

      <!-- "Perdi meu crachá": o crachá morre agora. A tela É a confirmação —
           diz o que acontece e só age depois do PIN. -->
      <template v-else-if="lostBadge">
        <NuxtAlert
          color="warning"
          variant="subtle"
          icon="i-lucide-badge-x"
          title="Perdi meu crachá"
          description="Seu crachá para de funcionar agora. Seu PIN continua valendo: você segue trabalhando. Um gerente emite outro crachá."
        />

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

        <div class="flex justify-center">
          <NuxtButton
            color="neutral"
            variant="ghost"
            label="Cancelar"
            @click="lostBadge = false"
          />
        </div>
      </template>

      <template v-else>
        <!-- ⚠️ Esta tela se confunde com a AUTORIZAÇÃO DO GERENTE, não com o
             login: as duas aparecem no meio do expediente, as duas são um
             teclado de PIN e as duas interrompem quem está atendendo. A linha
             abaixo é metade de um par — a outra metade, no diálogo de
             autorização, diz "Você continua como <fulano>".

               aqui         → você ASSUME este dispositivo (a sessão troca)
               autorização  → você CONTINUA quem era (o gerente só assina)

             Era "Você assume o balcão." em todos os apps, inclusive na Central,
             no B.I. e no Marketing, que não têm balcão (beta 05/11). O que troca
             é a sessão do dispositivo inteiro (o destrave é login de verdade), e
             a frase diz isso em qualquer app. -->
        <!-- O título é o cabeçalho da tela de bloqueio (h2): o leitor de tela
             navega por ele. O mesmo desenho do cabeçalho do login do operador
             (`OperatorLoginForm`): o cadeado no centro, título e uma linha. -->
        <header class="grid justify-items-center gap-3 text-center">
          <NuxtAvatar size="3xl" icon="i-lucide-lock" alt="" class="[@media(max-height:43.75rem)]:hidden" />
          <div class="grid gap-1">
            <h2 class="text-lg font-semibold">Identifique-se para operar</h2>
            <p class="text-sm text-muted-foreground" data-operator-lock-subtitle>{{ subtitle }}</p>
          </div>
        </header>

        <!-- A lista chegando: o lugar dos nomes, e não "ninguém habilitado". -->
        <div
          v-if="eligibleLoading"
          class="grid gap-2"
          role="status"
          aria-busy="true"
          data-operator-lock-loading
        >
          <p class="text-center text-sm text-muted-foreground">Carregando operadores…</p>
          <div class="grid grid-cols-2 gap-2" aria-hidden="true">
            <NuxtSkeleton v-for="n in 4" :key="n" class="h-14" />
          </div>
        </div>

        <!-- Falha de rede não é lista vazia: diz que não leu e oferece ler de novo. -->
        <NuxtAlert
          v-else-if="eligibleFailed"
          color="error"
          variant="subtle"
          icon="i-lucide-wifi-off"
          title="Não foi possível carregar os operadores."
          :actions="alertActions('error', [{ label: 'Tentar de novo', onClick: loadEligible }])"
          data-operator-lock-eligible-error
        />

        <!-- Dentro do cartão, `soft`: sem borda (cartão dentro de cartão, dono 08/10). -->
        <NuxtEmpty
          v-else-if="!eligible.length"
          variant="soft"
          icon="i-lucide-user-x"
          title="Nenhum operador habilitado para esta tela"
        />

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
          :error="unlockError"
          prompt="Quem está operando?"
          change-label="Trocar operador"
          @pick="onPick"
          @pin="onPin"
          @badge="(token: string) => unlock({ badge: token })"
        >
          <template #footer>
            <!-- Discreto, mas não escondido: quem perdeu o crachá precisa achar
                 sozinho, então é texto legível ao lado do irmão, e não um menu. -->
            <!-- Uma linha no meio da coluna, cada uma do tamanho do próprio nome
                 (rótulo que cabe: apertou, cai para o curto; não coube, desce). -->
            <OperatorFitGroup :actions="footerActions" class="flex flex-wrap justify-center gap-2">
              <OperatorButton
                color="neutral"
                variant="ghost"
                v-bind="footerActions[0]"
                @click="startChange"
              />
              <OperatorButton
                color="neutral"
                variant="ghost"
                v-bind="footerActions[1]"
                @click="lostBadge = true"
              />
            </OperatorFitGroup>
          </template>
        </OperatorIdentify>

        <!-- Sempre à vista, inclusive com a lista vazia: é a porta de quem não
             está nela. -->
        <div class="flex justify-center">
          <NuxtButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-key-round"
            label="Entrar com senha"
            data-operator-lock-password
            @click="withPassword = true"
          />
        </div>
      </template>
      </div>
    </NuxtCard>
  </div>
</template>
