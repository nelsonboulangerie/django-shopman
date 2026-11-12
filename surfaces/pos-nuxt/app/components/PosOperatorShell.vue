<script setup lang="ts">
// SHELL DE OPERADOR do PDV — o chrome comum a toda tela que alguém OPERA: aviso
// de conexão, tela de senha (para dispositivo que ainda não é estação), overlay
// de identificação do operador (PIN/crachá), setup de estação e o auto-lock de
// kiosk. A venda vive em `pages/index.vue`; a sessão de caixa em `pages/session/`.
//
// A navegação é a da suíte (fase 2): o `OperatorSuiteShell` do kit (barra lateral em
// três estados na mesa, gaveta pelo ☰ e barra inferior abaixo de `lg`), montado UMA
// vez aqui, com as seções de `usePosShell`. Exceção declarada (WP-FASE2 §7): os
// corredores (Fim do dia e o Relatório de caixa) sobem sem barra lateral e sem barra
// inferior; a saída deles é o "Sair" (ou o voltar) da própria tela.
// Cada página lê a Projection via usePosTerminal (useFetch deduplicado — uma
// busca só por request).
//
// Este shell só sobe nas rotas de operador. A tela do cliente (`/display`) tem
// shell próprio (`PosCustomerDisplayShell`) e NUNCA passa por aqui — ver a
// decisão em `app.vue`. Nada aqui deve voltar a conhecer o display: se uma regra
// precisa de "menos na tela do cliente", o lugar dela não é este arquivo.
//
import { refreshScopeForChannel } from "~/presentation/events";
import { posSupportContext } from "~/presentation/supportContext";
import { posCorridorRoute } from "~/presentation/sections";

// Resiliência de rede (kit): reconciliação ao reconectar/reganhar foco — o tablet do
// balcão que dormiu não fica com dados velhos. O <OfflineBanner> (auto-import do kit)
// dá o aviso calmo enquanto offline.
const { pos, refresh, refreshTabs } = await usePosTerminal();
const { onReconnect } = useConnectivity();

// Re-gate global de sessão (kit): um 401 no meio do turno (sessão expirada do
// lado do Django) sobe a tela de senha em vez de o operador bater numa sessão
// morta.
const { expired: sessionExpired } = useOperatorSession();

// Identidade do operador (PIN/crachá) pelo LOCK COMPARTILHADO do kit — o MESMO
// `useOperatorLock` + `<OperatorLock>` dos outros 4 apps de operador.
const OPERATOR_PERM = "cashman.operate_pos";
// `refreshOperatorSession` e não `refresh`: `refresh` aqui já é o da Projection
// do terminal (`usePosTerminal`, linha 17). São duas leituras diferentes.
const {
  locked,
  canIdentify,
  sessionState,
  sessionUnavailable,
  refresh: refreshOperatorSession,
  stationRef,
  mustChange,
  lock,
  operator,
} = useOperatorLock(OPERATOR_PERM);
// Destravou: toda leitura feita com a tela travada voltou 403 `station_locked`, e
// a tela ficava nesse erro com alguém já identificado ("Estação travada.
// Identifique-se…" nas Encomendas) e o rail sem "Encomendas", que leu a recusa
// como falta de permissão (beta 07/11). Ao destravar, relê tudo o que a tela lê.
watch(locked, (now, before) => {
  if (before && !now) void refreshNuxtData();
});
// O mesmo portão dos outros apps (beta 05/11, CEN-03). Sem ele, quem não opera o
// caixa (a Cozinha, digitando o endereço) via a casca do PDV com "Não foi possível
// ler as comandas agora", sem saída, e o servidor recebia o mesmo 403 em sequência.
// Do portão o PDV usa só a recusa: a trava continua sobreposta à venda (ela não
// derruba a tela por baixo), e a tela de senha tem a regra própria logo abaixo.
const surface = computed(() =>
  operatorSurfaceGate({
    sessionState: sessionState.value,
    canIdentify: canIdentify.value,
    sessionUnavailable: sessionUnavailable.value,
    locked: locked.value,
    mustChange: mustChange.value,
    harness: false,
  }),
);
const forbidden = computed(() => surface.value.showForbidden);

// Tempo real entre estações (ADR-016): pedido de troco, devolução pendente e
// turno aberto/fechado feitos em OUTRA estação chegam por push; no evento,
// refazemos o fetch canônico da Projection (o mesmo `refresh` deduplicado que
// todas as páginas leem). Poll calmo de 60s só enquanto o SSE não conecta.
// O SSE só conecta com a estação identificada e desbloqueada (F3): no gate
// (login/lock) os canais são negados e o EventSource entraria no ciclo de
// reconexão com 400 — quem garante a tela ali é o poll de fallback.
// O aviso de comanda relê só o quadro (`refreshTabs`); o do caixa, o poll e a
// volta à aba relêem a projeção inteira.
// Recusado não relê: a resposta seria o mesmo 403.
const { realtime } = usePosEvents(
  (channel) => {
    if (forbidden.value) return;
    return refreshScopeForChannel(channel?.path) === "tabs" ? refreshTabs() : refresh();
  },
  { enabled: () => canIdentify.value && !locked.value && !forbidden.value },
);
// O "ao vivo" dos cabeçalhos (camada da suíte) lê daqui: o estado do push e a hora
// da última leitura da Projection.
onReconnect(() => {
  if (!forbidden.value) void refresh();
});
const live = usePosLiveState();
watch(realtime, (value) => { live.value.realtime = value; }, { immediate: true });
watch(pos, () => { live.value.lastRead = new Date().toISOString(); }, { immediate: true });

// Leitor de código da bancada (HID, modo teclado): lê o QR da Via Cozinha em
// qualquer tela do PDV e dá o pronto do ticket da estação sem tela (decisão do
// dono, 26/09/2026). Só com alguém identificado — com a tela travada, as teclas
// são do PIN/crachá, e o pronto precisa de um operador para assinar.
useKitchenTicketScanner({ enabled: () => canIdentify.value && !locked.value && !forbidden.value });

// Comanda pronta: a cozinha terminou tudo o que foi disparado e o balcão ouve, em
// qualquer tela do PDV (decisão do dono, 13/10/2026). O selo e o topo são do quadro.
usePosKitchenReadyAlert(usePosTabsState());

// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): o gestor entra
// com senha uma vez e diz em que posto ele fica. Enquanto ninguém fizer isso, o
// dispositivo não tem antessala. A oferta é dispensável de propósito: no PC pessoal
// do gestor a resposta certa é "usar sem vincular".
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

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
//
// ⚠️ `sessionUnavailable` entra aqui, e não é detalhe: `canIdentify` é só
// `session !== null`, então QUALQUER falha da consulta (502/503 no redeploy,
// rede caindo) zerava a resposta e subia a tela de senha no balcão — com a
// sessão viva. Provado em runtime com o servidor devolvendo 503: a tela pedia
// usuário e senha. Erro de rede não é sessão morta.
const needsLogin = computed(
  () => (!canIdentify.value && !sessionUnavailable.value) || sessionExpired.value,
);

const { sections, switcherSections, current, select } = usePosShell(pos);
const route = useRoute();
const corridor = computed(() => posCorridorRoute(route.path));

// O que o chamado leva junto: app, tela, posto e terminal. Refs, nunca PII.
const supportContext = computed(() =>
  posSupportContext({
    route: route.path,
    station: stationRef.value,
    terminal: pos.value?.terminal_ref ?? "",
  }),
);

</script>

<template>
  <!-- `data-suite="v3"`: o PDV veste a camada visual da suíte (onda V4). Os primitivos
       do kit leem esse atributo para vestir o visual das prévias. -->
  <div class="min-h-dvh bg-background text-foreground" data-pos-shell="operator" data-suite="v3">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit): fixed no topo, só aparece offline. -->
    <OfflineBanner />

    <!-- Identificação unificada (PIN ou CRACHÁ): o mesmo overlay dos outros 4 apps. -->
    <OperatorLock
      v-if="canIdentify && (locked || mustChange)"
      :perm="OPERATOR_PERM"
    />

    <OperatorSessionUnavailable
      v-if="sessionUnavailable"
      scope="o caixa"
      @retry="refreshOperatorSession()"
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

    <OperatorSurfaceForbidden v-else-if="forbidden" :perm="OPERATOR_PERM" />

    <OperatorStationSetup
      v-else-if="stationSetup.offer.value"
      @done="stationSetup.done()"
      @dismiss="stationSetup.dismiss()"
      @unavailable="stationSetup.dismiss({ remember: false })"
    />

    <!-- Corredor (Fim do dia, Relatório): a tela inteira, sem navegação. -->
    <div v-else-if="corridor" class="flex min-h-dvh flex-col" data-pos-corridor>
      <NuxtPage />
    </div>

    <OperatorSuiteShell
      v-else
      storage-key="pos"
      :sections="sections"
      :current="current"
      :switcher-sections="switcherSections"
      default-form="floor"
      floor-bar
      label="Seções do PDV"
      :operator-name="operator?.name"
      @select="select"
      @lock="lock()"
    >
      <template #rail-actions>
        <SupportTrigger :context="supportContext" size="sm" variant="ghost" block />
      </template>
      <NuxtPage />
    </OperatorSuiteShell>

    <OperatorSonner />
  </div>
</template>
