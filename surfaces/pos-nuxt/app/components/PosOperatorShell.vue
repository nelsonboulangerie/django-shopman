<script setup lang="ts">
// SHELL DE OPERADOR do PDV — o chrome comum a toda tela que alguém OPERA: aviso
// de conexão, tela de senha (para dispositivo que ainda não é estação), overlay
// de identificação do operador (PIN/crachá), setup de estação e o auto-lock de
// kiosk. A venda vive em `pages/index.vue`; a sessão de caixa em `pages/session/`.
// Cada página lê a Projection via usePosTerminal (useFetch deduplicado — uma
// busca só por request).
//
// Este shell só sobe nas rotas de operador. A tela do cliente (`/display`) tem
// shell próprio (`PosCustomerDisplayShell`) e NUNCA passa por aqui — ver a
// decisão em `app.vue`. Nada aqui deve voltar a conhecer o display: se uma regra
// precisa de "menos na tela do cliente", o lugar dela não é este arquivo.
//
// Resiliência de rede (kit): reconciliação ao reconectar/reganhar foco — o tablet do
// balcão que dormiu não fica com dados velhos. O <OfflineBanner> (auto-import do kit)
// dá o aviso calmo enquanto offline.
const { pos, refresh } = await usePosTerminal();
const { onReconnect } = useConnectivity();
onReconnect(() => refresh());

// Re-gate global de sessão (kit): um 401 no meio do turno (sessão expirada do
// lado do Django) sobe a tela de senha em vez de o operador bater numa sessão
// morta.
const { expired: sessionExpired } = useOperatorSession();

// Identidade do operador (PIN/crachá) pelo LOCK COMPARTILHADO do kit — o MESMO
// `useOperatorLock` + `<OperatorLock>` dos outros 4 apps de operador.
const OPERATOR_PERM = "cashman.operate_pos";
const { locked, canIdentify, stationRef, mustChange, lock } = useOperatorLock(OPERATOR_PERM);

// Tempo real entre estações (ADR-016): pedido de troco, devolução pendente e
// turno aberto/fechado feitos em OUTRA estação chegam por push; no evento,
// refazemos o fetch canônico da Projection (o mesmo `refresh` deduplicado que
// todas as páginas leem). Poll calmo de 60s só enquanto o SSE não conecta.
// O SSE só conecta com a estação identificada e desbloqueada (F3): no gate
// (login/lock) os canais são negados e o EventSource entraria no ciclo de
// reconexão com 400 — quem garante a tela ali é o poll de fallback.
usePosEvents(() => refresh(), { enabled: () => canIdentify.value && !locked.value });

// Iniciar o dispositivo: o gestor entra com senha uma vez e diz qual balcão é este.
// Enquanto ninguém fizer isso, o dispositivo não tem antessala — a loja só entra com
// senha, todo dia. A oferta é dispensável de propósito: no PC pessoal do gestor a
// resposta certa é "agora não".
const setupDismissed = ref(false);
const needsStationSetup = computed(
  () => canIdentify.value && !locked.value && !stationRef.value && !setupDismissed.value,
);

// Auto-lock por ociosidade é a única particularidade de kiosk do PDV (os outros apps
// não auto-travam). Vale em qualquer rota de operador (venda ou antesala).
// `holdWhen`: a tela de venda liga este sinal enquanto há pagamento em curso
// (checkout aberto ou PIX aguardando) — o PDV não trava no meio do gesto.
const paymentHold = useState("pos-payment-hold", () => false);
usePosAutoLock({
  locked,
  lock,
  autoLockSeconds: () => pos.value?.auto_lock_seconds ?? 60,
  holdWhen: () => paymentHold.value,
});

// A tela de SENHA sobe só quando o dispositivo não é uma estação reconhecida (a
// antessala respondeu 403), ou quando a sessão expirou no meio do turno. Estação
// reconhecida e sem ninguém identificado → `<OperatorLock>` (PIN/crachá), nunca
// a tela de senha: senão a loja pediria credencial de gestor toda manhã.
const needsLogin = computed(() => !canIdentify.value || sessionExpired.value);

// Recarrega depois de virar estação: toda leitura muda de mundo (a antessala
// passa a existir, o terminal passa a ser este), e reconciliar peça por peça é
// mais caminho para dar errado do que um reload numa tela que acontece uma vez.
function reloadIntoStation() {
  if (import.meta.client) window.location.reload();
}

</script>

<template>
  <div class="min-h-dvh bg-background text-foreground" data-pos-shell="operator">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit): fixed no topo, só aparece offline. -->
    <OfflineBanner />

    <!-- Identificação unificada (PIN ou CRACHÁ): o mesmo overlay dos outros 4 apps. -->
    <OperatorLock
      v-if="canIdentify && (locked || mustChange)"
      :perm="OPERATOR_PERM"
    />

    <!-- 48px nos campos é deliberado no caixa: digitação rápida em tela de toque. -->
    <OperatorLogin
      v-if="needsLogin"
      mode="page"
      large-fields
      icon="lucide:lock-keyhole"
      :title="sessionExpired ? 'Sua sessão expirou' : 'Entre para operar o caixa'"
      :description="
        sessionExpired
          ? 'Entre de novo para continuar de onde parou.'
          : 'Acesse com sua conta autorizada a operar o caixa.'
      "
    />

    <OperatorStationSetup
      v-else-if="needsStationSetup"
      @done="reloadIntoStation"
      @dismiss="setupDismissed = true"
    />

    <NuxtPage v-else />

    <OperatorSonner />
  </div>
</template>
