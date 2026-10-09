<script setup lang="ts">
// Central: a home do Shopman e o launcher pós-login, no shell da suíte (fase 2, variante
// "início"). A casca é a mesma dos apps migrados (`OperatorSuiteShell`): barra lateral em
// três estados na mesa, gaveta pelo ☰ e barra do topo no celular, com "Início" como única
// seção. A página é o `OperatorPageHeader` (saudação, selo de cadência, busca da suíte,
// avisos da tela e o ⋯ único) e o conteúdo: "Precisa de você" (a fila das filas: o item
// exato de cada app, com o gesto que abre o lugar exato) e os blocos dos apps com a linha
// de estado de cada um. Tudo já vem filtrado por permissão.
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
import type { HubQueueItemProjection, HubTileProjection } from "~/types/hub";
import type { OperatorSession } from "../../operator-kit/app/types/operator";
import { useNow } from "@vueuse/core";
import {
  APPS_HINT_COPY,
  HUB_NAMED_OF,
  HUB_REFRESH_LABEL,
  HUB_SECTIONS,
  QUEUE_EMPTY_COPY,
  QUEUE_HINT_COPY,
  hubBrandLine,
  hubFailure,
  hubFailureCopy,
  hubDateLine,
  hubGreeting,
  hubIsEmpty,
  queueActionAriaLabel,
  queueCount,
  queueDetailLine,
  queueMoreLabel,
  queuePhoneLine,
  queueTimeLabel,
  readClockLabel,
  serverClockOffset,
  staleQueueAlert,
  tileAriaLabel,
  tileForItem,
  tileIcon,
  tileIconUrl,
  tileLinkAttrs,
  tileStatus,
  PHONE_QUEUE_ROWS,
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
// deploy sem a família). A falha é local por bloco: um app sem ícone não apaga os outros.
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

// Precisa de você. O relógio anda a cada segundo (a contagem "aceita sozinho em 2:40" não
// congela entre uma leitura e outra) e conta pela hora do servidor, não pela do dispositivo.
const queueItems = computed(() => queue.value?.items ?? []);
const queueTotal = computed(() => queueCount(queue.value));
const queueMore = computed(() => queueMoreLabel(queue.value?.more_count ?? 0));
// No celular, "Precisa de você" mostra até 3 linhas; o resto abre num toque. A linha
// inteira é o toque.
const phoneQueueOpen = ref(false);
const phoneQueueItems = computed(() =>
  phoneQueueOpen.value ? queueItems.value : queueItems.value.slice(0, PHONE_QUEUE_ROWS),
);
const phoneQueueHidden = computed(() =>
  phoneQueueOpen.value ? 0 : Math.max(0, queueItems.value.length - PHONE_QUEUE_ROWS),
);
const clockOffset = ref(0);
watch(
  () => queue.value?.server_now,
  (serverNow) => {
    clockOffset.value = serverNow ? serverClockOffset(serverNow, Date.now()) : 0;
  },
  { immediate: true },
);
const deviceNow = useNow({ interval: 1000 });
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
const { onReconnect } = useConnectivity();
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

const alerts = computed<OperatorScreenAlert[]>(() =>
  staleRead.value
    ? [
        {
          id: "stale-read",
          color: "warning",
          ...staleQueueAlert(readClock.value),
          action: { label: "Tentar de novo", onSelect: () => void refresh() },
        },
      ]
    : [],
);

// O ⋯ único da tela: o que age sobre a tela inteira (fase 2, seção 11).
const headerActions = computed<OperatorHeaderAction[]>(() => [
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    disabled: pending.value,
    onSelect: () => void refresh(),
  },
]);

// A linha da fila usa o ícone do app de destino (o mesmo do bloco) e abre do mesmo jeito
// que o bloco abriria: na janela própria do app quando a Central está instalada.
function itemIconSrc(item: HubQueueItemProjection): string | null {
  const tile = tileForItem(tiles.value, item);
  return tile ? tileImageSrc(tile) : null;
}
function itemIcon(item: HubQueueItemProjection): string {
  return tileIcon(tileForItem(tiles.value, item)?.icon || "circle-dot");
}
function itemLinkAttrs(item: HubQueueItemProjection) {
  return tileLinkAttrs({ kind: "launch", url: item.url }, linkContext.value);
}

/** O ponto de estado do bloco: a cor nunca fala sozinha (a frase está ao lado). */
function toneDot(tile: HubTileProjection): string {
  const tone = tileStatus(tile).tone;
  return tone === "attention" ? "bg-warning" : tone === "positive" ? "bg-success" : "bg-(--ui-text-dimmed)";
}
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
        :sections="HUB_SECTIONS"
        current="home"
        :label="`Seções ${HUB_NAMED_OF}`"
        :operator-name="operatorName || undefined"
        @lock="lockDevice"
      >
        <div class="flex min-h-0 flex-1 flex-col">
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
                <!-- Precisa de você: a fila das filas (UX-H1). O item exato primeiro,
                     ordenado por urgência entre apps; cada linha com o gesto que abre o
                     lugar exato no app certo. -->
                <section aria-labelledby="hub-queue-title" data-hub-queue>
                  <div class="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <h2 id="hub-queue-title" class="text-base font-semibold">Precisa de você</h2>
                    <NuxtBadge v-if="queueTotal" color="neutral" :label="String(queueTotal)" />
                    <p class="ms-auto text-xs text-muted max-md:hidden">{{ QUEUE_HINT_COPY }}</p>
                  </div>

                  <OperatorScreenState
                    v-if="!queueItems.length"
                    state="empty"
                    icon="i-lucide-circle-check"
                    :title="QUEUE_EMPTY_COPY"
                    data-hub-queue-empty
                  />

                  <NuxtCard v-else :ui="{ body: 'p-0 sm:p-0' }">
                    <!-- Celular: a linha inteira é o toque, com o ponto de atenção e o
                         chevron; até 3, o resto num toque. O texto quebra, nunca corta. -->
                    <ol class="divide-y divide-default md:hidden" data-hub-queue-phone>
                      <li v-for="item in phoneQueueItems" :key="item.key" data-hub-queue-item>
                        <a
                          :href="item.url"
                          :target="itemLinkAttrs(item).target"
                          :rel="itemLinkAttrs(item).rel"
                          :aria-label="queueActionAriaLabel(item)"
                          class="flex min-h-14 items-center gap-3 px-4 py-2 transition-colors active:bg-elevated"
                          data-hub-queue-action
                        >
                          <span
                            class="grid size-8 shrink-0 place-items-center overflow-hidden rounded-md text-primary"
                            :class="itemIconSrc(item) ? '' : 'bg-primary/10'"
                          >
                            <img
                              v-if="itemIconSrc(item)"
                              :src="itemIconSrc(item)!"
                              :data-app-icon="item.app"
                              class="size-8 rounded-md"
                              alt=""
                              loading="lazy"
                              decoding="async"
                              @error="brokenTileIcons.add(item.app)"
                            >
                            <NuxtIcon v-else :name="itemIcon(item)" class="size-4" />
                          </span>
                          <span class="min-w-0 flex-1">
                            <span class="block text-sm font-semibold">{{ item.title }}</span>
                            <span class="block text-xs text-muted">{{ queuePhoneLine(item, nowMs) }}</span>
                          </span>
                          <span
                            v-if="item.attention"
                            class="size-2 shrink-0 rounded-full bg-warning"
                            aria-hidden="true"
                            data-hub-queue-dot
                          />
                          <NuxtIcon name="i-lucide-chevron-right" class="size-5 shrink-0 text-muted" aria-hidden="true" />
                        </a>
                      </li>
                    </ol>

                    <!-- Tablet e mesa: app, o item, o tempo e o gesto, numa linha que
                         quebra o texto em vez de cortar. -->
                    <ol class="hidden divide-y divide-default md:block">
                      <li
                        v-for="item in queueItems"
                        :key="item.key"
                        data-hub-queue-item
                        class="flex min-h-14 items-center gap-3.5 px-4 py-2"
                      >
                        <span
                          class="grid size-7 shrink-0 place-items-center overflow-hidden rounded-md text-primary"
                          :class="itemIconSrc(item) ? '' : 'bg-primary/10'"
                        >
                          <img
                            v-if="itemIconSrc(item)"
                            :src="itemIconSrc(item)!"
                            :data-app-icon="item.app"
                            class="size-7 rounded-md"
                            alt=""
                            loading="lazy"
                            decoding="async"
                            @error="brokenTileIcons.add(item.app)"
                          >
                          <NuxtIcon v-else :name="itemIcon(item)" class="size-4" />
                        </span>
                        <span class="w-20 shrink-0 text-xs text-muted">{{ item.app_label }}</span>

                        <div class="min-w-0 flex-1">
                          <p class="text-sm font-semibold">{{ item.title }}</p>
                          <p class="text-xs text-muted">{{ queueDetailLine(item, nowMs) }}</p>
                        </div>

                        <span
                          data-hub-queue-time
                          class="w-28 shrink-0 text-right text-sm tabular-nums"
                          :class="item.attention ? 'font-semibold text-warning' : 'text-muted'"
                        >{{ queueTimeLabel(item, nowMs) }}</span>

                        <!-- Largura fixa (a coluna não serrilha): o gesto longo ("Resolver
                             no contexto") quebra em duas linhas dentro do botão. -->
                        <NuxtButton
                          :to="item.url"
                          :target="itemLinkAttrs(item).target"
                          :rel="itemLinkAttrs(item).rel"
                          :aria-label="queueActionAriaLabel(item)"
                          color="neutral"
                          variant="outline"
                          trailing-icon="i-lucide-arrow-right"
                          class="w-40 shrink-0 justify-center"
                          data-hub-queue-action
                        >
                          <span class="text-center leading-tight whitespace-normal" data-hub-queue-action-label>{{ item.action_label }}</span>
                        </NuxtButton>
                      </li>
                    </ol>
                  </NuxtCard>

                  <NuxtButton
                    v-if="phoneQueueHidden"
                    :label="`Ver mais ${phoneQueueHidden}`"
                    color="neutral"
                    variant="ghost"
                    block
                    class="mt-1 md:hidden"
                    data-hub-queue-phone-more
                    @click="phoneQueueOpen = true"
                  />

                  <p v-if="queueMore" class="mt-2 text-xs text-muted" data-hub-queue-more>{{ queueMore }}</p>
                </section>

                <!-- Os apps: o bloco inteiro é o link, com a linha de estado que concorda
                     com a fila acima. -->
                <section aria-labelledby="hub-apps-title">
                  <div class="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <h2 id="hub-apps-title" class="text-base font-semibold">Apps</h2>
                    <NuxtBadge color="neutral" :label="String(tiles.length)" />
                    <p class="ms-auto text-xs text-muted max-md:hidden">{{ APPS_HINT_COPY }}</p>
                  </div>

                  <!-- Celular: os apps como linhas de 62 px, com chevron; nome e estado
                       quebram, nunca cortam. -->
                  <NuxtCard class="md:hidden" :ui="{ body: 'p-0 sm:p-0' }">
                    <ul class="divide-y divide-default" data-hub-apps-phone>
                      <li v-for="tile in tiles" :key="tile.ref">
                        <a
                          :href="tile.url"
                          :target="tileLinkAttrs(tile, linkContext).target"
                          :rel="tileLinkAttrs(tile, linkContext).rel"
                          class="flex min-h-[62px] items-center gap-3 px-4 py-2 transition-colors active:bg-elevated"
                          data-hub-app-row
                        >
                          <span
                            class="grid size-10 shrink-0 place-items-center overflow-hidden rounded-lg text-primary"
                            :class="tileImageSrc(tile) ? '' : 'bg-primary/10'"
                          >
                            <img
                              v-if="tileImageSrc(tile)"
                              :src="tileImageSrc(tile)!"
                              :data-app-icon="tile.ref"
                              class="size-10 rounded-lg"
                              alt=""
                              loading="lazy"
                              decoding="async"
                              @error="brokenTileIcons.add(tile.ref)"
                            >
                            <NuxtIcon v-else :name="tileIcon(tile.icon)" class="size-5" />
                          </span>
                          <span class="min-w-0 flex-1">
                            <span class="block text-base font-semibold leading-tight" data-tile-title>{{ tile.label }}</span>
                            <span v-if="tileStatus(tile).hasStatus" class="flex min-w-0 items-start gap-1.5 text-xs" data-tile-status>
                              <span class="mt-1 size-[7px] shrink-0 rounded-full" :class="toneDot(tile)" aria-hidden="true" />
                              <span class="min-w-0">
                                <template v-for="(part, index) in tileStatus(tile).parts" :key="part.role">
                                  <span v-if="index" class="text-muted"> · </span>
                                  <span :class="part.role === 'attention' ? 'font-semibold text-warning' : 'text-muted'">{{ part.text }}</span>
                                </template>
                              </span>
                            </span>
                          </span>
                          <NuxtIcon
                            :name="tile.kind === 'external' ? 'i-lucide-external-link' : 'i-lucide-chevron-right'"
                            class="size-5 shrink-0 text-muted"
                            aria-hidden="true"
                          />
                        </a>
                      </li>
                    </ul>
                  </NuxtCard>

                  <!-- Tablet e mesa: o destaque navegável canônico (`NuxtPageCard`). A
                       grade tem linhas de mesma altura; o texto quebra, nunca corta. -->
                  <NuxtPageGrid class="hidden auto-rows-fr gap-3 md:grid md:grid-cols-2 lg:grid-cols-4 lg:gap-3">
                    <NuxtPageCard
                      v-for="tile in tiles"
                      :key="tile.ref"
                      :to="tile.url"
                      :target="tileLinkAttrs(tile, linkContext).target"
                      :rel="tileLinkAttrs(tile, linkContext).rel"
                      :aria-label="tileAriaLabel(tile)"
                      :title="tile.label"
                      :description="tile.description"
                      data-hub-app-card
                    >
                      <template #leading>
                        <span
                          class="grid size-10 shrink-0 place-items-center overflow-hidden rounded-lg text-primary"
                          :class="tileImageSrc(tile) ? '' : 'bg-primary/10'"
                        >
                          <img
                            v-if="tileImageSrc(tile)"
                            :src="tileImageSrc(tile)!"
                            :data-app-icon="tile.ref"
                            class="size-10 rounded-lg"
                            alt=""
                            loading="lazy"
                            decoding="async"
                            @error="brokenTileIcons.add(tile.ref)"
                          >
                          <NuxtIcon v-else :name="tileIcon(tile.icon)" class="size-5" />
                        </span>
                      </template>
                      <template #title>
                        <span class="inline-flex items-center gap-1.5" data-tile-title>
                          {{ tile.label }}
                          <NuxtIcon
                            v-if="tile.kind === 'external'"
                            name="i-lucide-external-link"
                            class="size-4 text-muted"
                            aria-hidden="true"
                          />
                        </span>
                      </template>
                      <template v-if="tileStatus(tile).hasStatus" #footer>
                        <span class="flex min-w-0 items-start gap-2 text-sm" data-tile-status>
                          <span
                            class="mt-1.5 size-[7px] shrink-0 rounded-full"
                            :class="toneDot(tile)"
                            :data-tile-tone="tileStatus(tile).tone"
                            aria-hidden="true"
                          />
                          <span class="min-w-0">
                            <template v-for="(part, index) in tileStatus(tile).parts" :key="part.role">
                              <span v-if="index" class="text-muted"> · </span>
                              <span
                                :class="{
                                  'font-semibold text-warning': part.role === 'attention',
                                  'text-muted': part.role === 'neutral' && tileStatus(tile).tone === 'attention',
                                }"
                              >{{ part.text }}</span>
                            </template>
                          </span>
                        </span>
                      </template>
                    </NuxtPageCard>
                  </NuxtPageGrid>
                </section>
              </template>

              <!-- Avisos neste dispositivo (o gesto que cabe ao estado; o que chega e os
                   dispositivos a um toque) e a versão publicada deste build, que é o que
                   o operador lê para o suporte ao relatar algo. -->
              <footer class="border-t border-default pt-3 text-sm text-muted">
                <OperatorPushSettings variant="line">
                  <template #end>
                    <span class="ms-auto inline-flex min-h-8 items-center tabular-nums" data-hub-version>
                      Versão {{ HUB_NAMED_OF }}:&nbsp;<span class="font-mono text-default">{{ appVersion }}</span>
                    </span>
                  </template>
                </OperatorPushSettings>
              </footer>
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
      <OperatorSonner />
      <OperatorPwaRuntime />
    </div>
  </OperatorAppRoot>
</template>
