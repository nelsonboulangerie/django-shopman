<script setup lang="ts">
// POS shell — com a antesala de sessão (`/session`) o PDV ganhou rotas, e o
// app.vue afinou para o chrome comum a todas: aviso de conexão, tela de senha
// (para dispositivo que ainda não é estação), overlay de identificação do operador
// (PIN/crachá) e o auto-lock de kiosk. A venda vive em `pages/index.vue`; a
// sessão de caixa em `pages/session/`. Cada página lê a Projection via
// usePosTerminal (useFetch deduplicado — uma busca só por request).
// Resiliência de rede (kit): reconciliação ao reconectar/reganhar foco — o tablet do
// balcão que dormiu não fica com dados velhos. O <OfflineBanner> (auto-import do kit)
// dá o aviso calmo enquanto offline.
const { pos, refresh } = await usePosTerminal();
const { onReconnect } = useConnectivity();
onReconnect(() => refresh());

// A tela do cliente (`/display`) é OUTRA janela do mesmo navegador, virada para
// quem compra: nada do chrome de operador sobe nela. Em especial o auto-lock —
// travar é logout no SERVIDOR, e a janela do display (que ninguém toca) o
// dispararia sozinha, derrubando o operador da estação no meio da venda.
const route = useRoute();
const isCustomerDisplay = computed(() => route.path === "/display");

// Tempo real entre estações (ADR-016): pedido de troco, devolução pendente e
// turno aberto/fechado feitos em OUTRA estação chegam por push; no evento,
// refazemos o fetch canônico da Projection (o mesmo `refresh` deduplicado que
// todas as páginas leem). Poll calmo de 60s só enquanto o SSE não conecta.
// Não na tela do cliente: ela consome só o BroadcastChannel da estação — SSE e
// poll ali seriam uma conexão e um refetch a mais sem ninguém para ler.


// Re-gate global de sessão (kit): um 401 no meio do turno (sessão expirada do
// lado do Django) sobe a tela de senha em vez de o operador bater numa sessão
// morta.
const { expired: sessionExpired, reset: resetSession } = useOperatorSession();

// Identidade do operador (PIN/crachá) pelo LOCK COMPARTILHADO do kit — o MESMO
// `useOperatorLock` + `<OperatorLock>` dos outros 4 apps de operador.
const OPERATOR_PERM = "cashman.operate_pos";
const { locked, canIdentify, stationRef, mustChange, lock } = useOperatorLock(OPERATOR_PERM);

// Tempo real entre estações (ADR-016): pedido de troco, devolução pendente e
// turno aberto/fechado feitos em OUTRA estação chegam por push; no evento,
// refazemos o fetch canônico da Projection (o mesmo refresh deduplicado que
// todas as páginas leem). Poll calmo de 60s só enquanto o SSE não conecta.
// Não na tela do cliente: ela consome só o BroadcastChannel da estação — SSE e
// poll ali seriam uma conexão e um refetch a mais sem ninguém para ler.
// O SSE só conecta com a estação identificada e desbloqueada (F3): no gate
// (login/lock) os canais são negados e o EventSource entraria no ciclo de
// reconexão com 400 — quem garante a tela ali é o poll de fallback.
if (route.path !== "/display") {
  usePosEvents(() => refresh(), { enabled: () => canIdentify.value && !locked.value });
}

// Iniciar o dispositivo: o gestor entra com senha uma vez e diz qual balcão é este.
// Enquanto ninguém fizer isso, o dispositivo não tem antessala — a loja só entra com
// senha, todo dia. A oferta é dispensável de propósito: no PC pessoal do gestor a
// resposta certa é "agora não".
const setupDismissed = ref(false);
const needsStationSetup = computed(
  () => canIdentify.value && !locked.value && !stationRef.value && !setupDismissed.value && !isCustomerDisplay.value,
);

// Auto-lock por ociosidade é a única particularidade de kiosk do PDV (os outros apps
// não auto-travam). Vale em qualquer rota (venda ou antesala) — MENOS na tela do
// cliente: `0` desliga o timer (ver isIdleBeyond) na janela que ninguém toca.
// `holdWhen`: a tela de venda liga este sinal enquanto há pagamento em curso
// (checkout aberto ou PIX aguardando) — o PDV não trava no meio do gesto.
const paymentHold = useState("pos-payment-hold", () => false);
usePosAutoLock({
  locked,
  lock,
  autoLockSeconds: () => (isCustomerDisplay.value ? 0 : pos.value?.auto_lock_seconds ?? 60),
  holdWhen: () => paymentHold.value,
});

// A tela de SENHA sobe só quando o dispositivo não é uma estação reconhecida (a
// antessala respondeu 403), ou quando a sessão expirou no meio do turno. Estação
// reconhecida e sem ninguém identificado → `<OperatorLock>` (PIN/crachá), nunca
// a tela de senha: senão a loja pediria credencial de gestor toda manhã.
// Na tela do cliente, nunca: formulário de login na parede não identifica ninguém.
const needsLogin = computed(() => !isCustomerDisplay.value && (!canIdentify.value || sessionExpired.value));

// Login com SENHA no próprio caixa (sem bounce pro Django admin): é o caminho de
// quem provisiona a estação e o do dispositivo pessoal. Uma tela, um submit.
const loginUser = ref("");
const loginPass = ref("");
const loginPending = ref(false);
const loginError = ref("");
// Foco no "Usuário" assim que a tela de senha aparece (na carga ou quando a
// sessão expira no meio do turno): a primeira ação é sempre digitar ali.
const loginUserRef = ref<HTMLInputElement | null>(null);
watch(needsLogin, async (needs) => {
  if (!needs || !import.meta.client) return;
  await nextTick();
  loginUserRef.value?.focus();
}, { immediate: true });
// Recarrega depois de virar estação: toda leitura muda de mundo (a antessala
// passa a existir, o terminal passa a ser este), e reconciliar peça por peça é
// mais caminho para dar errado do que um reload numa tela que acontece uma vez.
function reloadIntoStation() {
  if (import.meta.client) window.location.reload();
}

async function submitLogin() {
  if (loginPending.value) return;
  loginError.value = "";
  loginPending.value = true;
  try {
    await $fetch("/api/v1/backstage/operator/login/", {
      method: "POST",
      body: { username: loginUser.value.trim(), password: loginPass.value },
    });
    resetSession(); // sessão re-estabelecida antes do reload
    if (import.meta.client) window.location.reload();
  } catch (error) {
    loginError.value = httpErrorMessage(error, "Não foi possível entrar. Confira usuário e senha.");
    loginPending.value = false;
  }
}
</script>

<template>
  <div class="min-h-dvh bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit): fixed no topo, só aparece offline. -->
    <OfflineBanner />

    <!-- Identificação unificada (PIN ou CRACHÁ): o mesmo overlay dos outros 4 apps.
         Nunca na tela do cliente: o overlay cobriria a parede que o cliente vê. -->
    <OperatorLock
      v-if="!isCustomerDisplay && canIdentify && (locked || mustChange)"
      :perm="OPERATOR_PERM"
    />

    <div v-if="needsLogin" class="grid min-h-dvh place-items-center p-4">
      <form class="grid w-full max-w-sm gap-4 text-center" @submit.prevent="submitLogin">
        <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
          <Icon name="lucide:lock-keyhole" class="size-7 text-muted-foreground" />
        </div>
        <div class="grid gap-1.5">
          <h2 class="text-lg font-semibold">{{ sessionExpired ? "Sua sessão expirou" : "Entre para operar o caixa" }}</h2>
          <p class="text-sm text-muted-foreground">
            {{ sessionExpired ? "Entre de novo para continuar de onde parou." : "Acesse com sua conta autorizada a operar o caixa." }}
          </p>
        </div>
        <div class="grid gap-2.5 text-left">
          <input
            ref="loginUserRef"
            v-model="loginUser"
            type="text"
            autocomplete="username"
            autocapitalize="none"
            autocorrect="off"
            placeholder="Usuário"
            aria-label="Usuário"
            :disabled="loginPending"
            class="h-12 w-full rounded-md border bg-background px-3 text-base outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
          >
          <input
            v-model="loginPass"
            type="password"
            autocomplete="current-password"
            placeholder="Senha"
            aria-label="Senha"
            :disabled="loginPending"
            class="h-12 w-full rounded-md border bg-background px-3 text-base outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
          >
          <p v-if="loginError" class="text-sm text-destructive" role="alert">{{ loginError }}</p>
        </div>
        <UiButton type="submit" size="lg" :disabled="loginPending || !loginUser.trim() || !loginPass">
          <Icon :name="loginPending ? 'line-md:loading-loop' : 'lucide:log-in'" class="size-5" />
          {{ loginPending ? "Entrando…" : "Entrar" }}
        </UiButton>
      </form>
    </div>

    <OperatorStationSetup
      v-else-if="needsStationSetup"
      @done="reloadIntoStation"
      @dismiss="setupDismissed = true"
    />

    <NuxtPage v-else />

    <UiSonner />
  </div>
</template>
