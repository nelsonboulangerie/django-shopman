<script setup lang="ts">
// Central: a home do Shopman e o launcher pós-login, no shell da suíte (fase 2, variante
// "início", `home`: o selo do topo da barra lateral é identidade, sem "voltar à Central").
// A casca é a mesma dos apps migrados (`OperatorSuiteShell`): barra lateral em três estados
// na mesa, gaveta pelo ☰ no tablet, com "Início" como única seção (por isso sem barra
// inferior: uma vaga só não aparece, `quickBarLayout` do kit). No celular, a linha do chão
// do modelo de navegação (`OperatorCompactBar`, 31/10/2026): o selo "Central" com o ponto
// da leitura, busca, Avisos e o ⋮, e a saudação como título da página (dono, 04/11/2026);
// o selo abre a gaveta (a Central não tem
// trocador: trocar de app não passa por ela, é ela). A página é o `OperatorPageHeader`
// (saudação, selo de cadência, busca da suíte, avisos da tela e o ⋯ único) e o conteúdo:
// os apps como uma grade de ícones, na ordem de sempre, cada um só com o ícone, o nome e,
// quando algo pede alguém, o número no canto do ícone (dono, 04/11/2026: "simplifique").
// O detalhe mora dentro do app. Tudo já vem filtrado por permissão.
// Sem CRUD: cada bloco abre a superfície dedicada (ou deep-linka pro Unfold, no caso da
// Loja). Herda do kit o OfflineBanner, o re-gate de 401 (useOperatorSession) e
// httpErrorMessage.
//
// Largura: o que muda com ela é estrutura de apresentação e mora no CSS (`md:hidden`,
// `hidden md:grid`). Nada aqui decide árvore por media query, então a carga direta a 390
// px hidrata a mesma árvore que o servidor mandou, sem piscar.
import type { OperatorScreenAlert } from "../../operator-kit/app/presentation/screenState";
import type { OperatorHeaderAction } from "../../operator-kit/app/presentation/pageHeader";
import type { HubFailure } from "~/presentation/hub";
import type { HubTileProjection } from "~/types/hub";
import type { OperatorSession } from "../../operator-kit/app/types/operator";
import { useNow } from "@vueuse/core";
import { countChipProps } from "../../operator-kit/app/presentation/countChip";
import {
  HUB_NAMED_OF,
  HUB_REFRESH_LABEL,
  HUB_REFRESH_SHORT_LABEL,
  HUB_SECTIONS,
  hubBrandLine,
  hubFailure,
  hubFailureCopy,
  hubDateLine,
  hubGreeting,
  hubIsEmpty,
  hubPushAlert,
  hubPushState,
  hubVersionLabel,
  readClockLabel,
  serverClockOffset,
  staleQueueAlert,
  tileAriaLabel,
  tileAttentionCount,
  tileIcon,
  tileIconStyle,
  tileIconUrl,
  tileLinkAttrs,
} from "~/presentation/hub";

// O que só o navegador sabe (a origem da janela, o fuso, se a Central está instalada)
// entra depois de montar: antes disso a árvore é a do servidor.
const mounted = ref(false);
onMounted(() => {
  mounted.value = true;
});

// Como cada bloco abre depende de a Central estar instalada (janela própria por app)
// ou ser uma aba comum. A leitura é reativa: instalar com a tela aberta já muda o link.
const { installed } = useOperatorAppLink();
const linkContext = computed(() => ({
  installed: mounted.value && installed.value,
  currentOrigin: mounted.value ? window.location.origin : "",
}));

// O bloco mostra o ícone REAL do app (o PNG do PWA na origem do próprio app), e cai no
// Lucide do Django quando a URL não resolve OU quando a imagem falha (app fora do ar,
// deploy sem a família), na cor do app como o PNG. A falha é local por bloco: um app sem
// ícone não apaga os outros.
const brokenTileIcons = reactive(new Set<string>());
function tileImageSrc(tile: HubTileProjection): string | null {
  return brokenTileIcons.has(tile.ref) ? null : tileIconUrl(tile);
}
// A imagem que falha ANTES da hidratação (renderizada no servidor) não dispara o `@error`
// que o Vue ainda não ligou, e ficava o ícone quebrado do navegador. Na montagem, a que já
// terminou sem pixels também cai no Lucide. (Antes do `await` abaixo: depois dele o
// `onMounted` não tem instância e o Vue o descarta.)
onMounted(() => {
  for (const img of document.querySelectorAll<HTMLImageElement>("img[data-app-icon]")) {
    if (img.complete && img.naturalWidth === 0 && img.dataset.appIcon) brokenTileIcons.add(img.dataset.appIcon);
  }
});

const apiPath = useApiPath();
// A casa ao lado do nome do sistema: "Shopman · Nelson Boulangerie" (auditoria H06). O
// nome inteiro (`Shop.name`) vem da projection; o curto (`Shop.short_name`, que o kit lê
// para o nome da janela) é do PWA e só entra enquanto a projection não chegou.
const { prefix: house } = useOperatorWindowTitle();

// Versão publicada deste build (`NUXT_PUBLIC_APP_VERSION`/`SOURCE_VERSION`; "local" na
// máquina de quem desenvolve). É o que o operador lê para o suporte ao relatar algo.
const appVersion = String(useRuntimeConfig().public.appVersion || "local");

// Avisos neste dispositivo (dono, 04/11/2026: o rodapé saiu). O estado só aparece quando
// pede um gesto, como aviso da tela; o que chega e os dispositivos ficam a um toque no ⋮
// ("Avisos neste dispositivo"). A permissão só existe no navegador: lida depois de montar,
// e com a lista de dispositivos já lida (sem ela, "desligados" piscaria para quem já ligou).
// (Antes do `await` abaixo: depois dele o `onMounted` não tem instância.)
const push = useWebPush();
const pushRead = ref(false);
onMounted(async () => {
  if (push.supported.value && push.permission.value === "granted") await push.refresh();
  pushRead.value = true;
});
const pushState = computed(() =>
  hubPushState({
    read: pushRead.value,
    supported: push.supported.value,
    active: push.active.value,
    permission: push.permission.value,
    unavailableReason: push.unavailableReason.value,
  }),
);
const pushSettingsOpen = ref(false);

// Suporte: o chamado nasce aqui, com o contexto que a Central conhece.
const supportOpen = ref(false);
function reloadPage(): void {
  window.location.reload();
}

const { hub, tiles, queue, operatorName, shopName, error, pending, refresh } = await useOperatorHub();
const brandLine = computed(() => hubBrandLine(shopName.value || house));

// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps). A Central é a porta
// de entrada de todo dispositivo novo, e por isso oferece todos os tipos de posto. A
// antessala é a mesma chave que o cabeçalho lê para mostrar "Posto Expedição".
const { data: stationSession } = useFetch<OperatorSession>("/api/v1/backstage/operator/session/", {
  key: "operator-session",
  server: true,
});
const stationSetup = useStationSetupOffer({
  canIdentify: computed(() => Boolean(stationSession.value?.operator)),
  locked: computed(() => Boolean(stationSession.value?.locked)),
  stationRef: computed(() => stationSession.value?.station ?? ""),
});

// O relógio da linha do dia conta pela hora do servidor.
const clockOffset = ref(0);
watch(
  () => queue.value?.server_now,
  (serverNow) => {
    clockOffset.value = serverNow ? serverClockOffset(serverNow, Date.now()) : 0;
  },
  { immediate: true },
);
const deviceNow = useNow({ interval: 60_000 });
const nowMs = computed(() => deviceNow.value.getTime() + clockOffset.value);
// "Sexta-feira, 9 de outubro": só depois de montar (o fuso é o do dispositivo, o da loja;
// no servidor seria o da máquina, e a hidratação divergiria).
const dayLine = computed(() => (mounted.value ? hubDateLine(nowMs.value).split(" · ")[1] || "" : ""));

// A hora da última leitura que chegou: o selo diz a cadência enquanto tudo anda e, se a
// releitura falha, de quando é o que está na tela.
const lastReadAt = ref(Number.NaN);
watch(
  [hub, mounted],
  () => {
    if (mounted.value && hub.value && !error.value) lastReadAt.value = Date.now();
  },
  { immediate: true },
);
const readClock = computed(() => readClockLabel(lastReadAt.value));

// Bloquear: a Central não é superfície com capacidade própria, então o Bloquear daqui
// trava o DISPOSITIVO (toda superfície desta sessão pede PIN ou crachá), e a Central
// mostra a trava do kit até alguém se identificar.
const deviceLocked = computed(() => Boolean(stationSession.value?.operator && stationSession.value?.locked));
const { run: lockDevice } = usePendingAction(async () => {
  await $fetch("/api/v1/backstage/operator/lock/", {
    method: "POST",
    credentials: "same-origin",
    body: { scope: "device" },
  });
  await refreshNuxtData("operator-session");
});

// Resiliência de rede (kit): reconciliação ao reconectar/reganhar foco.
const { isOnline, onReconnect } = useConnectivity();
onReconnect(() => refresh());

// Re-gate de sessão (kit): sessão expirada → volta pro login.
const { expired: sessionExpired } = useOperatorSession();

// ⚠️ Cinco causas distintas viravam UM booleano que subia o formulário de senha.
// API fora do ar, deploy em andamento e estação travada pediam senha, num balcão
// onde a credencial é PIN ou crachá, e onde senha não conserta nenhuma das três.
// A classificação é pura (`presentation/hub.ts`) para poder ser testada sem montar
// componente; os utilitários de erro são os do kit.
const failure = computed<HubFailure>(() =>
  hubFailure(error.value, {
    isUnauthenticated: isUnauthenticatedError,
    isStationLocked: isStationLockedError,
    isTransient: isTransientError,
    status: (e) => httpError(e).status,
  }),
);
const failureCopy = computed(() => hubFailureCopy(failure.value));
const needsLogin = computed(() => failure.value === "login" || sessionExpired.value);
// A releitura que falha com a fila já na tela NÃO derruba a tela: vira o aviso do
// cabeçalho, com a hora do que está na tela e o "Tentar de novo".
const staleRead = computed(() => failure.value === "unavailable" && Boolean(hub.value));
const hasBlockingFailure = computed(
  () => (failure.value !== "none" && !staleRead.value) || sessionExpired.value,
);
const isEmpty = computed(() => hubIsEmpty(tiles.value));

const alerts = computed<OperatorScreenAlert[]>(() => {
  const out: OperatorScreenAlert[] = [];
  if (staleRead.value) {
    out.push({
      id: "stale-read",
      color: "warning",
      ...staleQueueAlert(readClock.value),
      action: { label: "Tentar de novo", onSelect: () => void refresh() },
    });
  }
  const pushAlert = hubPushAlert(pushState.value);
  if (pushAlert) {
    const action =
      pushState.value === "off"
        ? { label: push.loading.value ? "Ligando…" : "Ligar avisos", onSelect: () => void push.activate() }
        : pushState.value === "blocked"
          ? { label: "Recarregar", onSelect: reloadPage }
          : undefined;
    out.push(action ? { ...pushAlert, action } : pushAlert);
  }
  return out;
});

// A leitura no ponto do selo da linha do chão (celular): periódica enquanto anda, atrasada
// quando a releitura falha com a fila na tela, sem conexão quando o dispositivo caiu.
const compactTone = computed(() => (!isOnline.value ? "off" : staleRead.value ? "late" : "calm"));

// O ⋯ único da tela: o que age sobre a tela inteira (fase 2, seção 11). Na linha do chão
// do celular é o mesmo ⋮, com a leitura (cadência e hora) no topo. Por último, a versão
// publicada deste build (o que o operador lê para o suporte), como rótulo: não é gesto.
const versionItem = { label: hubVersionLabel(appVersion), icon: "i-lucide-tag", type: "label" as const };
const headerActions = computed<OperatorHeaderAction[]>(() => [
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    disabled: pending.value,
    onSelect: () => void refresh(),
  },
  {
    label: "Suporte",
    icon: "i-lucide-life-buoy",
    onSelect: () => {
      supportOpen.value = true;
    },
  },
  {
    label: "Avisos neste dispositivo",
    icon: "i-lucide-bell",
    onSelect: () => {
      pushSettingsOpen.value = true;
    },
  },
  versionItem,
]);

</script>

<template>
  <OperatorAppRoot>
    <div class="flex min-h-dvh bg-default text-default" data-hub-app>
      <NuxtRouteAnnouncer />
      <OfflineBanner />

      <!-- Gate de login (sessão ausente/expirada) -->
      <OperatorLogin
        v-if="needsLogin"
        mode="page"
        :login-url="apiPath('/api/v1/backstage/operator/login/')"
        :title="sessionExpired ? 'Sua sessão expirou' : brandLine"
        :description="
          sessionExpired
            ? 'Entre de novo para continuar.'
            : 'Acesse com sua conta de operador.'
        "
      />

      <!-- Falha que NÃO se resolve com senha: estação travada, sem permissão, ou a
           home fora do ar sem nada na tela. Cada uma tem a sua saída, e "Tentar de
           novo" só aparece onde tentar de novo faz sentido. -->
      <main v-else-if="hasBlockingFailure" class="grid min-h-dvh flex-1 place-items-center p-4" data-hub-failure>
        <div class="w-full max-w-md">
          <OperatorScreenState
            v-if="failureCopy.retry"
            state="error"
            :title="failureCopy.title"
            :description="failureCopy.hint"
            @retry="refresh()"
          />
          <NuxtEmpty
            v-else
            :icon="failure === 'station' ? 'i-lucide-lock' : 'i-lucide-shield-x'"
            :title="failureCopy.title"
            :description="failureCopy.hint"
          />
        </div>
      </main>

      <!-- Dispositivo travado pelo Bloquear daqui: a trava do kit, sem a Central por baixo. -->
      <OperatorLock v-else-if="deviceLocked" perm="" />

      <!-- Launcher, no shell da suíte. -->
      <OperatorSuiteShell
        v-else
        storage-key="hub"
        home
        :sections="HUB_SECTIONS"
        current="home"
        :label="`Seções ${HUB_NAMED_OF}`"
        :operator-name="operatorName || undefined"
        @lock="lockDevice"
      >
        <!-- `data-compact-page`: no celular a linha do chão é o cabeçalho inteiro (o kit
             esconde a barra de 56px abaixo de `md`; os avisos da tela continuam). -->
        <div class="flex min-h-0 flex-1 flex-col" data-compact-page>
          <OperatorCompactBar
            :title="hubGreeting(operatorName)"
            :tone="compactTone"
            :time="readClock"
            :conn-label="HUB_REFRESH_LABEL"
            search-button-label="Buscar pedido, cliente, produto, insumo ou tela"
            :options="headerActions"
            seal-app-as-title
          />
          <OperatorPageHeader
            :title="hubGreeting(operatorName)"
            search-placeholder="Buscar pedido, cliente, produto, insumo ou tela"
            :actions="headerActions"
            :actions-label="`Mais ações ${HUB_NAMED_OF}`"
            :alerts="alerts"
          >
            <!-- Variante "início": o selo é identidade, sem caminho de volta (já estamos
                 na Central). No celular a gaveta o mostra; na mesa, a barra lateral. -->
            <template #lead>
              <OperatorAppSeal home class="max-sm:hidden" data-hub-seal />
            </template>
            <template #status>
              <OperatorLiveStatus
                :tone="staleRead ? 'late' : 'calm'"
                :time="staleRead ? readClock : ''"
                :label="HUB_REFRESH_LABEL"
                :short-label="HUB_REFRESH_SHORT_LABEL"
                :detail="brandLine"
              />
              <span class="text-xs text-muted max-sm:hidden" data-hub-brand>
                <template v-if="dayLine">{{ dayLine }} · </template>{{ brandLine }}
              </span>
            </template>
          </OperatorPageHeader>

          <main class="min-h-0 flex-1 overflow-y-auto" data-hub-content>
            <div class="mx-auto flex w-full max-w-[1120px] flex-col gap-6 px-4 pt-4 pb-6 sm:px-6">
              <OperatorScreenState
                v-if="isEmpty"
                state="empty"
                icon="i-lucide-layout-grid"
                title="Sua conta ainda não tem acesso a nenhum app."
                description="Peça a um responsável o acesso aos apps do seu turno."
                data-hub-empty
              />

              <template v-else>
                <!-- No celular, a saudação é o título da página (dono, 04/11/2026): o selo da
                     linha do chão diz só "Central". Na mesa ela já é o título do cabeçalho. -->
                <h1 class="-mb-2 text-xl font-semibold text-highlighted md:hidden" data-hub-phone-greeting>
                  {{ hubGreeting(operatorName) }}
                </h1>
                <!-- Os apps: grade de ícones, duas colunas no celular e mais na mesa, ícone
                     grande na cor do app e o nome embaixo (dono, 04/11/2026: "Simplifique",
                     "ícones em grade, como o Odoo faz"). No máximo um indicador: o número no
                     canto superior direito do ícone (o chip de contagem da suíte, o do sino),
                     que conta o que está parado esperando um gesto de quem opera
                     (`attention_count`, critério na projection). Em dia, nada. O detalhe
                     mora dentro do app. A ordem é a do registro: o ícone não troca de lugar. -->
                <section aria-labelledby="hub-apps-title">
                  <h2 id="hub-apps-title" class="sr-only">Apps</h2>
                  <ul
                    class="mx-auto grid w-full max-w-4xl grid-cols-2 gap-x-3 gap-y-4 pt-2 sm:grid-cols-3 md:grid-cols-4 md:gap-y-6 md:pt-6 lg:grid-cols-6"
                    data-hub-apps
                  >
                    <li v-for="tile in tiles" :key="tile.ref" data-hub-app-item>
                      <a
                        :href="tile.url"
                        :target="tileLinkAttrs(tile, linkContext).target"
                        :rel="tileLinkAttrs(tile, linkContext).rel"
                        :aria-label="tileAriaLabel(tile)"
                        class="group flex flex-col items-center gap-2.5 rounded-xl px-2 py-3 text-center transition-colors hover:bg-elevated focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary active:bg-elevated"
                        data-hub-app-link
                        :data-attention="tileAttentionCount(tile) || undefined"
                      >
                        <NuxtChip
                          v-bind="countChipProps(tileAttentionCount(tile) || 1)"
                          :show="tileAttentionCount(tile) > 0"
                          position="top-right"
                        >
                          <span
                            class="grid size-20 place-items-center overflow-hidden rounded-2xl text-primary shadow-sm"
                            :class="tileImageSrc(tile) || tileIconStyle(tile) ? '' : 'bg-primary/10'"
                            :style="tileImageSrc(tile) ? undefined : tileIconStyle(tile) ?? undefined"
                          >
                            <img
                              v-if="tileImageSrc(tile)"
                              :src="tileImageSrc(tile)!"
                              :data-app-icon="tile.ref"
                              class="size-20 rounded-2xl"
                              alt=""
                              loading="lazy"
                              decoding="async"
                              @error="brokenTileIcons.add(tile.ref)"
                            >
                            <NuxtIcon v-else :name="tileIcon(tile.icon)" class="size-9" />
                          </span>
                        </NuxtChip>
                        <span class="text-sm leading-tight font-semibold text-highlighted" data-tile-title>{{ tile.label }}</span>
                      </a>
                    </li>
                  </ul>
                </section>
              </template>

              <!-- Tem mais abaixo (kit): no celular a lista de apps passa da dobra. -->
              <MoreBelow />
            </div>
          </main>
        </div>
      </OperatorSuiteShell>

      <OperatorStationSetup
        v-if="stationSetup.offer.value && !hasBlockingFailure"
        @done="stationSetup.done()"
        @dismiss="stationSetup.dismiss()"
        @unavailable="stationSetup.dismiss({ remember: false })"
      />
      <!-- O que chega e os dispositivos (o cartão do kit), a um toque no ⋮. -->
      <NuxtModal v-model:open="pushSettingsOpen" title="Avisos neste dispositivo" :ui="{ title: 'sr-only' }">
        <template #body>
          <OperatorPushSettings class="mt-0! border-0! bg-transparent! p-0!" />
        </template>
      </NuxtModal>
      <SupportPanel v-model:open="supportOpen" :context="{ app: 'hub', route: '/' }" />
      <OperatorSonner />
      <OperatorPwaRuntime />
    </div>
  </OperatorAppRoot>
</template>
