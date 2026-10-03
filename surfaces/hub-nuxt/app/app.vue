<script setup lang="ts">
// Central: a home do Shopman e o launcher pós-login. Lê a projection do hub e mostra,
// no topo, "Precisa de você" (a fila das filas: o item exato de cada app, com o gesto que
// abre o lugar exato) e, embaixo, os blocos dos apps com a linha de estado de cada um.
// Tudo já vem filtrado por permissão.
// Sem CRUD: cada tile abre a superfície dedicada (ou deep-linka pro Unfold, no caso da
// Loja). Herda do kit o OfflineBanner, o re-gate de 401 (useOperatorSession) e
// httpErrorMessage.
import { useNow } from "@vueuse/core";
import type { HubFailure } from "~/presentation/hub";
import type { HubQueueItemProjection, HubTileProjection } from "~/types/hub";
import type { OperatorSession } from "../../operator-kit/app/types/operator";
import {
  HUB_NAMED_OF,
  QUEUE_EMPTY_COPY,
  QUEUE_HINT_COPY,
  hubBrandLine,
  hubFailure,
  hubFailureCopy,
  hubGreeting,
  hubIsEmpty,
  queueActionAriaLabel,
  queueCount,
  queueDetailLine,
  queueMoreLabel,
  queueTimeLabel,
  serverClockOffset,
  tileForItem,
  tileIcon,
  tileIconUrl,
  tileLinkAttrs,
  tileStatus,
} from "~/presentation/hub";

// Como cada tile abre depende de a Central estar instalada (janela própria por app)
// ou ser uma aba comum. A leitura é reativa: instalar com a tela aberta já muda o link.
const { installed } = useOperatorAppLink();
const linkContext = computed(() => ({
  installed: installed.value,
  currentOrigin: import.meta.client ? window.location.origin : "",
}));

const apiPath = useApiPath();
// A casa (`Shop.short_name`) que o kit já lê do Django para o nome da janela. A Central
// a mostra ao lado do nome do sistema: "Shopman · Nelson".
const { prefix: house } = useOperatorWindowTitle();
const brandLine = hubBrandLine(house);

// Versão publicada deste build (`NUXT_PUBLIC_APP_VERSION`/`SOURCE_VERSION`; "local" na
// máquina de quem desenvolve). É o que o operador lê para o suporte ao relatar algo.
const appVersion = String(useRuntimeConfig().public.appVersion || "local");

const { tiles, queue, operatorName, error, refresh } = await useOperatorHub();

// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps). A Central é a porta
// de entrada de todo dispositivo novo, e por isso oferece todos os tipos de posto. A
// antessala é a mesma chave que o rail lê para mostrar "Posto Expedição".
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

// Resiliência de rede (kit): reconciliação ao reconectar/reganhar foco.
const { onReconnect } = useConnectivity();
onReconnect(() => refresh());

// Re-gate de sessão (kit): sessão expirada → volta pro login.
const { expired: sessionExpired } = useOperatorSession();

// ⚠️ Cinco causas distintas viravam UM booleano que subia o formulário de senha.
// API fora do ar, deploy em andamento e estação travada pediam senha — num balcão
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
const hasBlockingFailure = computed(() => failure.value !== "none" || sessionExpired.value);
const isEmpty = computed(() => hubIsEmpty(tiles.value));

// O tile mostra o ícone REAL do app (o PNG do PWA na origem do próprio app), e cai no
// Lucide do Django quando a URL não resolve OU quando a imagem falha (app fora do ar,
// deploy sem a família). A falha é local por tile: um app sem ícone não apaga os outros.
const brokenTileIcons = reactive(new Set<string>());
function tileImageSrc(tile: HubTileProjection): string | null {
  return brokenTileIcons.has(tile.ref) ? null : tileIconUrl(tile);
}

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
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
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
         home fora do ar. Cada uma tem a sua saída — e "tentar de novo" só aparece
         onde tentar de novo faz sentido. -->
    <div v-else-if="hasBlockingFailure" class="grid min-h-dvh place-items-center p-4">
      <div class="grid w-full max-w-sm gap-4 text-center">
        <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
          <Icon
            :name="failure === 'station' ? 'lucide:lock' : failure === 'forbidden' ? 'lucide:shield-alert' : 'lucide:cloud-off'"
            class="size-7 text-muted-foreground"
          />
        </div>
        <div class="grid gap-1.5">
          <h1 class="text-lg font-semibold">{{ failureCopy.title }}</h1>
          <p class="text-sm text-muted-foreground">{{ failureCopy.hint }}</p>
        </div>
        <button
          v-if="failureCopy.retry"
          type="button"
          class="inline-flex h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          @click="refresh()"
        >
          Tentar de novo
        </button>
      </div>
    </div>

    <!-- Launcher -->
    <template v-else>
      <div class="flex min-h-dvh">
        <!-- Rail canônico (kit). Esta é a home: sem o atalho de volta (já estamos nela) e
             sem travar-operador. Só identidade + tema — a mesma espinha das outras. -->
        <div class="sticky top-0 flex h-dvh shrink-0">
          <OperatorRail />
        </div>

        <div class="flex min-w-0 flex-1 flex-col">
          <!-- Cabeçalho: controle do rail + a saudação (identidade da home). -->
          <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-3">
            <RailToggle />
            <div class="min-w-0">
              <h1 class="truncate text-base font-semibold leading-tight">{{ hubGreeting(operatorName) }}</h1>
              <p class="text-xs text-muted-foreground">{{ brandLine }}</p>
            </div>
          </header>

          <div class="mx-auto grid w-full max-w-6xl gap-8 p-4 sm:p-6">
            <div v-if="isEmpty" class="grid place-items-center gap-3 rounded-md border border-dashed p-10 text-center">
              <Icon name="lucide:inbox" class="size-8 text-muted-foreground" />
              <div class="grid gap-1">
                <p class="text-base font-semibold">Nenhum app liberado</p>
                <p class="text-sm text-muted-foreground">
                  Sua conta ainda não tem acesso a nenhuma superfície. Fale com o gerente.
                </p>
              </div>
            </div>

            <template v-else>
              <!-- Precisa de você: a fila das filas (UX-H1). O item exato primeiro, ordenado
                   por urgência entre apps; cada linha com um gesto que abre o lugar exato no
                   app certo. O fato em si é declarado lá, na forma única do trabalho. -->
              <section aria-labelledby="hub-queue-title" data-hub-queue class="grid gap-3">
                <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h2 id="hub-queue-title" class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Precisa de você
                    <span v-if="queueTotal" class="ml-1.5 tabular-nums text-foreground">{{ queueTotal }}</span>
                  </h2>
                  <p class="hidden text-xs text-muted-foreground sm:block">{{ QUEUE_HINT_COPY }}</p>
                </div>

                <p
                  v-if="!queueItems.length"
                  data-hub-queue-empty
                  class="rounded-md border border-border bg-card px-4 py-5 text-sm text-muted-foreground"
                >
                  {{ QUEUE_EMPTY_COPY }}
                </p>

                <ol v-else class="divide-y divide-border overflow-hidden rounded-md border border-border bg-card">
                  <li
                    v-for="item in queueItems"
                    :key="item.key"
                    data-hub-queue-item
                    class="grid gap-x-4 gap-y-2 px-4 py-3 sm:grid-cols-[9rem_minmax(0,1fr)_auto_auto] sm:items-center"
                  >
                    <!-- App: ícone ao lado do nome. No celular, divide a linha com o tempo. -->
                    <div class="flex min-w-0 items-center justify-between gap-3 sm:contents">
                      <span class="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
                        <span
                          class="grid size-7 shrink-0 place-items-center overflow-hidden rounded-md text-primary"
                          :class="itemIconSrc(item) ? '' : 'bg-primary/10'"
                        >
                          <img
                            v-if="itemIconSrc(item)"
                            :src="itemIconSrc(item)!"
                            class="size-7 rounded-md"
                            alt=""
                            loading="lazy"
                            decoding="async"
                            @error="brokenTileIcons.add(item.app)"
                          >
                          <Icon v-else :name="itemIcon(item)" class="size-4" />
                        </span>
                        <span>{{ item.app_label }}</span>
                      </span>
                      <span
                        class="shrink-0 text-sm tabular-nums sm:hidden"
                        :class="item.attention ? 'font-semibold text-warning' : 'text-muted-foreground'"
                      >{{ queueTimeLabel(item, nowMs) }}</span>
                    </div>

                    <div class="min-w-0">
                      <p class="text-sm font-semibold leading-snug">{{ item.title }}</p>
                      <p class="text-xs text-muted-foreground">{{ queueDetailLine(item, nowMs) }}</p>
                    </div>

                    <span
                      data-hub-queue-time
                      class="hidden text-right text-sm tabular-nums sm:block"
                      :class="item.attention ? 'font-semibold text-warning' : 'text-muted-foreground'"
                    >{{ queueTimeLabel(item, nowMs) }}</span>

                    <a
                      :href="item.url"
                      :target="itemLinkAttrs(item).target"
                      :rel="itemLinkAttrs(item).rel"
                      :aria-label="queueActionAriaLabel(item)"
                      data-hub-queue-action
                      class="inline-flex h-12 items-center justify-center gap-2 rounded-md border border-border bg-background px-4 text-sm font-medium transition hover:border-primary/40 hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-w-36"
                    >
                      {{ item.action_label }}
                      <Icon name="lucide:arrow-right" class="size-4" aria-hidden="true" />
                    </a>
                  </li>
                </ol>

                <p v-if="queueMore" class="text-xs text-muted-foreground" data-hub-queue-more>{{ queueMore }}</p>
              </section>

              <!-- Os apps: a aparência calma aprovada, mais compacta, com o ícone ao lado do
                   nome e a linha de estado que concorda com a fila acima. -->
              <section aria-labelledby="hub-apps-title" class="grid gap-3">
                <h2 id="hub-apps-title" class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Apps <span class="ml-1.5 tabular-nums text-foreground">{{ tiles.length }}</span>
                </h2>
                <ul class="grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <li v-for="tile in tiles" :key="tile.ref" class="h-full">
                    <a
                      :href="tile.url"
                      :target="tileLinkAttrs(tile, linkContext).target"
                      :rel="tileLinkAttrs(tile, linkContext).rel"
                      class="flex h-full min-h-28 gap-3 rounded-md border border-border bg-card p-4 text-left transition hover:border-primary/40 hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <!-- O PNG tem cantos arredondados e transparentes: o fundo tingido é só do
                           Lucide de fallback, senão vira moldura nos cantos do ícone. -->
                      <span
                        class="grid size-11 shrink-0 place-items-center overflow-hidden rounded-md text-primary"
                        :class="tileImageSrc(tile) ? '' : 'bg-primary/10'"
                      >
                        <img
                          v-if="tileImageSrc(tile)"
                          :src="tileImageSrc(tile)!"
                          class="size-11 rounded-md"
                          alt=""
                          loading="lazy"
                          decoding="async"
                          @error="brokenTileIcons.add(tile.ref)"
                        >
                        <Icon v-else :name="tileIcon(tile.icon)" class="size-6" />
                      </span>
                      <!-- Altura ÚNICA: a grade tem linhas de mesma altura (`auto-rows-fr`) e cada
                           bloco ocupa a linha inteira. Sem isso a grade ficava serrilhada (cada
                           bloco parava numa altura) e o olho perdia a coluna. Nome e frase param em
                           duas linhas; a linha de estado é aviso e nunca se corta (quebra a linha),
                           e ocupa o lugar mesmo vazia, para nenhum bloco encolher. -->
                      <span class="grid min-w-0 content-start gap-0.5">
                        <span data-tile-title class="line-clamp-2 text-base font-semibold leading-tight">{{ tile.label }}</span>
                        <span data-tile-description class="line-clamp-2 text-sm text-muted-foreground">{{ tile.description }}</span>
                        <span data-tile-status class="mt-2 flex min-h-4 min-w-0 items-start gap-2 text-xs leading-4">
                          <template v-if="tileStatus(tile).hasStatus">
                            <span
                              class="mt-1 size-2 shrink-0 rounded-full"
                              :class="tileStatus(tile).attention ? 'bg-warning' : 'bg-muted-foreground/40'"
                              aria-hidden="true"
                            />
                            <span class="min-w-0">
                              <span v-if="tileStatus(tile).attention" class="font-semibold text-warning">{{ tileStatus(tile).attention }}</span>
                              <span v-if="tileStatus(tile).attention && tileStatus(tile).summary" class="text-muted-foreground"> · </span>
                              <span v-if="tileStatus(tile).summary" class="text-muted-foreground">{{ tileStatus(tile).summary }}</span>
                            </span>
                          </template>
                        </span>
                      </span>
                    </a>
                  </li>
                </ul>
              </section>
            </template>

            <div class="grid gap-4">
              <OperatorPushSettings />

              <!-- Carimbo da versão publicada. Ele morava colado no título dos avisos e se
                   lia como se fosse propriedade do aviso ("local"); é a versão do build que
                   está no ar, e é assim que ele se apresenta agora. -->
              <p class="border-t border-border pt-4 text-xs text-muted-foreground">
                Versão {{ HUB_NAMED_OF }}: <span class="font-medium text-foreground">{{ appVersion }}</span>
              </p>
            </div>
          </div>
        </div>
      </div>
    </template>
    <!-- Avisos do rail (ex.: "este dispositivo não deixa travar o giro"). -->
    <OperatorStationSetup
      v-if="stationSetup.offer.value && !hasBlockingFailure"
      @done="stationSetup.done()"
      @dismiss="stationSetup.dismiss()"
      @unavailable="stationSetup.dismiss({ remember: false })"
    />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </main>
</template>
