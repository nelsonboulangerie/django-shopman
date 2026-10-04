<script setup lang="ts">
// Central: a home do Shopman e o launcher pós-login. Veste a camada visual da suíte
// (`data-suite="v3"`, prévia v4 `hub4.html`, "a fila das filas"): o rail de 76px com
// "Início" como única seção, a saudação de uma linha, a fila e os blocos dos apps, e o
// rodapé calmo com os avisos deste dispositivo e a versão. Lê a projection do hub e mostra,
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
  APPS_HINT_COPY,
  HUB_NAMED_OF,
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
// "10:03 · Sábado, 3 de outubro": só no cliente (o fuso é o do dispositivo, o da loja; no
// servidor seria o da máquina).
const dateLine = computed(() => (import.meta.client ? hubDateLine(nowMs.value) : ""));

// Do tablet para cima o sino mora no pé do rail; no celular (sem rail), no cabeçalho.
const isPhone = useMediaQuery("(max-width: 767.98px)");
// O selo da Central na barra de 56px do celular (v3 `depois-hub-celular`): o mesmo ícone
// do PWA que o rail mostra do tablet para cima.
const hubIdentity = (useRuntimeConfig().public as { operatorPwa?: { identity?: { iconSrc?: string; color?: string; icon?: string } } })
  .operatorPwa?.identity;
const hubSealBroken = ref(false);
const { isCollapsed: railHidden, set: setRail } = useRailState();

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
// A imagem que falha ANTES da hidratação (renderizada no servidor) não dispara o `@error`
// que o Vue ainda não ligou, e ficava o ícone quebrado do navegador. Na montagem, a que já
// terminou sem pixels também cai no Lucide.
onMounted(() => {
  for (const img of document.querySelectorAll<HTMLImageElement>("img[data-app-icon]")) {
    if (img.complete && img.naturalWidth === 0 && img.dataset.appIcon) brokenTileIcons.add(img.dataset.appIcon);
  }
});

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
  <!-- `data-suite="v3"`: a Central veste a camada visual da suíte (UX-KIT-V1). Os
       primitivos do kit (e a oferta de posto) leem esse atributo. -->
  <main class="min-h-dvh bg-background text-foreground" data-suite="v3">
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
         home fora do ar. Cada uma tem a sua saída, e "tentar de novo" só aparece
         onde tentar de novo faz sentido. -->
    <div v-else-if="hasBlockingFailure" class="grid min-h-dvh place-items-center p-4">
      <div class="grid w-full max-w-md gap-5 rounded-[14px] border border-border bg-card p-6 text-center shadow-sm sm:p-8">
        <div class="mx-auto grid size-12 place-items-center rounded-xl bg-secondary">
          <Icon
            :name="failure === 'station' ? 'lucide:lock' : failure === 'forbidden' ? 'lucide:shield-alert' : 'lucide:cloud-off'"
            class="size-6 text-foreground"
          />
        </div>
        <div class="grid gap-1.5">
          <h1 class="op-heading">{{ failureCopy.title }}</h1>
          <p class="op-body text-muted-foreground">{{ failureCopy.hint }}</p>
        </div>
        <button
          v-if="failureCopy.retry"
          type="button"
          class="inline-flex h-12 items-center justify-center rounded-lg bg-primary px-4 op-title text-primary-foreground"
          @click="refresh()"
        >
          Tentar de novo
        </button>
      </div>
    </div>

    <!-- Launcher -->
    <div v-else class="flex min-h-dvh">
      <!-- Rail da suíte (kit), do tablet para cima: o selo da Central (sem caminho de
           volta: já estamos nela), "Início" como única seção, Avisos e o menu do operador
           (tema, giro, ocultar a barra) no pé. A Central não trava operador: cada app
           trava o seu. -->
      <OperatorSuiteRail
        :sections="HUB_SECTIONS"
        current="home"
        :label="`Seções ${HUB_NAMED_OF}`"
        :operator-name="operatorName || undefined"
        :lockable="false"
      >
        <template v-if="!isPhone" #foot>
          <NotificationBell placement="rail" />
        </template>
      </OperatorSuiteRail>

      <div class="flex min-w-0 flex-1 flex-col">
        <!-- Cabeçalho de uma linha (76px): a saudação e a linha fina com o ao vivo, a
             hora e a assinatura "Shopman · Nelson". -->
        <!-- Celular: a barra de 56px com o selo, a saudação, o ao vivo e o sino; embaixo, o
             campo "Buscar em toda a suíte" (com a câmera), que abre a busca em tela cheia.
             Tablet e desktop: a saudação e, ao lado, a barra grande da busca (v4 `hub.jpg`). -->
        <header class="flex shrink-0 flex-wrap items-center gap-x-3 border-b border-border bg-card px-4 pt-2 md:h-[76px] md:flex-nowrap md:gap-6 md:px-8 md:py-0">
          <button
            v-if="railHidden"
            type="button"
            class="hidden size-control shrink-0 place-items-center rounded-md border border-border bg-card text-muted-foreground transition hover:bg-accent hover:text-foreground md:grid"
            aria-label="Mostrar a barra"
            title="Mostrar a barra"
            data-hub-show-rail
            @click="setRail('compact')"
          >
            <Icon name="lucide:panel-left-open" class="size-5" />
          </button>
          <span
            class="grid size-9 shrink-0 place-items-center overflow-hidden rounded-lg md:hidden"
            :style="{ background: hubIdentity?.color || 'var(--foreground)' }"
            aria-hidden="true"
            data-hub-phone-seal
          >
            <img
              v-if="hubIdentity?.iconSrc && !hubSealBroken"
              :src="hubIdentity.iconSrc"
              class="size-9"
              alt=""
              decoding="async"
              @error="hubSealBroken = true"
            >
            <Icon v-else name="lucide:layout-grid" class="size-5 text-white" />
          </span>
          <div class="min-w-0 flex-1 py-1 md:py-0">
            <h1 class="truncate op-heading">{{ hubGreeting(operatorName) }}</h1>
            <p class="mt-1.5 flex min-w-0 items-start gap-1.5 op-micro md:items-center text-muted-foreground tnum" data-hub-brand>
              <span class="live-dot mt-1 md:mt-0" aria-hidden="true" />
              <span class="min-w-0 md:truncate">
                <template v-if="dateLine">{{ dateLine }} · </template>{{ brandLine }}
              </span>
            </p>
          </div>
          <div v-if="isPhone" class="shrink-0">
            <NotificationBell />
          </div>
          <div class="order-last w-full pt-1 pb-3 md:order-none md:w-auto md:py-0" data-hub-search>
            <OperatorSuiteSearch variant="hero" placeholder="Buscar pedido, cliente, produto, insumo ou tela" />
          </div>
          <div class="hidden flex-1 xl:block" aria-hidden="true" />
        </header>

        <div class="flex-1">
          <div class="mx-auto flex w-full max-w-[1120px] flex-col gap-6 px-4 pt-5 pb-8 md:px-8 md:pt-6">
            <div v-if="isEmpty" class="grid place-items-center gap-3 rounded-[14px] border border-dashed border-border bg-card p-10 text-center">
              <Icon name="lucide:inbox" class="size-8 text-muted-foreground" />
              <div class="grid gap-1">
                <p class="op-title">Nenhum app liberado</p>
                <p class="op-body text-muted-foreground">
                  Sua conta ainda não tem acesso a nenhuma superfície. Fale com o gerente.
                </p>
              </div>
            </div>

            <template v-else>
              <!-- Precisa de você: a fila das filas (UX-H1). O item exato primeiro, ordenado
                   por urgência entre apps; cada linha com um gesto que abre o lugar exato no
                   app certo. O fato em si é declarado lá, na forma única do trabalho. -->
              <section aria-labelledby="hub-queue-title" data-hub-queue>
                <div class="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <h2 id="hub-queue-title" class="op-eyebrow">
                    Precisa de você
                    <span v-if="queueTotal" class="ml-1.5 op-label tracking-normal text-muted-foreground normal-case tnum">{{ queueTotal }}</span>
                  </h2>
                  <p class="ml-auto hidden op-micro text-muted-foreground md:block">{{ QUEUE_HINT_COPY }}</p>
                </div>

                <p
                  v-if="!queueItems.length"
                  data-hub-queue-empty
                  class="rounded-xl border border-border bg-card px-4 py-5 op-body text-muted-foreground"
                >
                  {{ QUEUE_EMPTY_COPY }}
                </p>

                <ol v-else class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
                  <li
                    v-for="item in queueItems"
                    :key="item.key"
                    data-hub-queue-item
                  >
                    <!-- Celular (v3 `depois-hub-celular`): a linha fina, inteira é o toque, com o
                         app › o lugar, o tempo, o ponto quando pede atenção e o chevron. -->
                    <a
                      :href="item.url"
                      :target="itemLinkAttrs(item).target"
                      :rel="itemLinkAttrs(item).rel"
                      :aria-label="queueActionAriaLabel(item)"
                      class="flex min-h-14 items-center gap-3 px-3 py-2 md:hidden"
                      data-hub-queue-phone-row
                    >
                      <span
                        class="grid size-8 shrink-0 place-items-center overflow-hidden rounded-lg text-primary"
                        :class="itemIconSrc(item) ? '' : 'bg-primary/10'"
                      >
                        <img v-if="itemIconSrc(item)" :src="itemIconSrc(item)!" class="size-8 rounded-lg" alt="" loading="lazy" decoding="async" @error="brokenTileIcons.add(item.app)">
                        <Icon v-else :name="itemIcon(item)" class="size-4" />
                      </span>
                      <span class="min-w-0 flex-1">
                        <span class="block op-label font-semibold">{{ item.title }}</span>
                        <span class="block op-micro text-muted-foreground">{{ item.app_label }} · {{ queueTimeLabel(item, nowMs) }}</span>
                      </span>
                      <span v-if="item.attention" class="size-[7px] shrink-0 rounded-full bg-warning" aria-hidden="true" />
                      <Icon name="lucide:chevron-right" class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                    </a>
                    <div class="hidden min-h-14 items-center gap-3.5 py-1 pr-3 pl-4 md:flex">
                    <!-- App: ícone e nome. No celular, divide a linha com o tempo. -->
                    <div class="flex min-w-0 items-center justify-between gap-3 md:contents">
                      <span class="flex min-w-0 items-center gap-2.5 md:contents">
                        <span
                          class="grid size-7 shrink-0 place-items-center overflow-hidden rounded-lg text-primary"
                          :class="itemIconSrc(item) ? '' : 'bg-primary/10'"
                        >
                          <img
                            v-if="itemIconSrc(item)"
                            :src="itemIconSrc(item)!"
                            :data-app-icon="item.app"
                            class="size-7 rounded-lg"
                            alt=""
                            loading="lazy"
                            decoding="async"
                            @error="brokenTileIcons.add(item.app)"
                          >
                          <Icon v-else :name="itemIcon(item)" class="size-4" />
                        </span>
                        <span class="op-label font-normal text-muted-foreground md:line-clamp-2 md:w-[76px] md:shrink-0 md:leading-tight">{{ item.app_label }}</span>
                      </span>
                      <span
                        class="shrink-0 op-label tnum md:hidden"
                        :class="item.attention ? 'font-semibold text-warning' : 'font-normal text-muted-foreground'"
                      >{{ queueTimeLabel(item, nowMs) }}</span>
                    </div>

                    <div class="min-w-0 md:flex-1">
                      <p class="op-body font-semibold lg:truncate">{{ item.title }}</p>
                      <p class="op-micro text-muted-foreground lg:truncate">{{ queueDetailLine(item, nowMs) }}</p>
                    </div>

                    <span
                      data-hub-queue-time
                      class="hidden w-[108px] shrink-0 text-right op-label tnum md:block"
                      :class="item.attention ? 'font-semibold text-warning' : 'font-normal text-muted-foreground'"
                    >{{ queueTimeLabel(item, nowMs) }}</span>

                    <a
                      :href="item.url"
                      :target="itemLinkAttrs(item).target"
                      :rel="itemLinkAttrs(item).rel"
                      :aria-label="queueActionAriaLabel(item)"
                      data-hub-queue-action
                      class="inline-flex h-12 items-center justify-center gap-1.5 rounded-md border border-border bg-card px-4 op-label font-semibold transition hover:border-primary/40 hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring md:w-[164px] md:shrink-0 md:px-3"
                    >
                      <!-- Largura fixa no tablet e no desktop (a coluna não serrilha): o gesto
                           longo ("Resolver no contexto") quebra em duas linhas dentro do botão. -->
                      <span class="line-clamp-2 text-center leading-tight" data-hub-queue-action-label>{{ item.action_label }}</span>
                      <Icon name="lucide:arrow-right" class="size-4" aria-hidden="true" />
                    </a>
                    </div>
                  </li>
                </ol>

                <p v-if="queueMore" class="mt-2 op-micro text-muted-foreground" data-hub-queue-more>{{ queueMore }}</p>
              </section>

              <!-- Os apps: blocos calmos (aparência aprovada na v3), o bloco inteiro é o link,
                   com a linha de estado que concorda com a fila acima. -->
              <section aria-labelledby="hub-apps-title">
                <div class="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <h2 id="hub-apps-title" class="op-eyebrow">
                    Apps <span class="ml-1.5 op-label tracking-normal text-muted-foreground normal-case tnum">{{ tiles.length }}</span>
                  </h2>
                  <p class="ml-auto hidden items-center gap-1.5 op-micro text-muted-foreground md:inline-flex">
                    <Icon name="lucide:info" class="size-3.5" aria-hidden="true" />{{ APPS_HINT_COPY }}
                  </p>
                </div>
                <!-- Celular (v3 `depois-hub-celular`): os apps como linhas grandes numa lista,
                     ícone, nome, a linha de estado e o chevron; a linha inteira é o toque. -->
                <ul class="grid auto-rows-fr grid-cols-1 overflow-hidden rounded-xl border border-border bg-card divide-y divide-border md:grid-cols-2 md:gap-3 md:divide-y-0 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent lg:grid-cols-4" data-hub-apps>
                  <li v-for="tile in tiles" :key="tile.ref" class="h-full">
                    <a
                      :href="tile.url"
                      :target="tileLinkAttrs(tile, linkContext).target"
                      :rel="tileLinkAttrs(tile, linkContext).rel"
                      class="relative grid h-full min-h-[62px] grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 px-3 py-2 text-left transition hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring md:flex md:flex-col md:items-stretch md:rounded-[14px] md:border md:border-border md:bg-card md:px-4 md:py-3.5 md:hover:border-primary/40"
                    >
                      <Icon
                        v-if="tile.kind === 'external'"
                        name="lucide:external-link"
                        class="col-start-3 row-span-2 row-start-1 size-4 text-muted-foreground md:absolute md:top-5 md:right-5"
                        aria-hidden="true"
                      />
                      <Icon
                        v-else
                        name="lucide:chevron-right"
                        class="col-start-3 row-span-2 row-start-1 size-5 text-muted-foreground md:hidden"
                        aria-hidden="true"
                      />
                      <!-- Altura ÚNICA: a grade tem linhas de mesma altura (`auto-rows-fr`) e cada
                           bloco ocupa a linha inteira. Nome e frase param em duas linhas; a linha
                           de estado desce para o pé do bloco, nunca se corta (quebra a linha), e
                           ocupa o lugar mesmo vazia, para nenhum bloco encolher. -->
                      <span class="contents md:flex md:items-center md:gap-3" :class="tile.kind === 'external' ? 'md:pr-6' : ''">
                        <!-- O PNG tem cantos arredondados e transparentes: o fundo tingido é só do
                             Lucide de fallback, senão vira moldura nos cantos do ícone. -->
                        <span
                          class="row-span-2 grid size-10 shrink-0 place-items-center overflow-hidden rounded-[10px] text-primary"
                          :class="tileImageSrc(tile) ? '' : 'bg-primary/10'"
                        >
                          <img
                            v-if="tileImageSrc(tile)"
                            :src="tileImageSrc(tile)!"
                            :data-app-icon="tile.ref"
                            class="size-10 rounded-[10px]"
                            alt=""
                            loading="lazy"
                            decoding="async"
                            @error="brokenTileIcons.add(tile.ref)"
                          >
                          <Icon v-else :name="tileIcon(tile.icon)" class="size-5" />
                        </span>
                        <span class="grid min-w-0 self-end md:self-auto">
                          <span data-tile-title class="line-clamp-2 op-title leading-tight">{{ tile.label }}</span>
                          <span data-tile-description class="hidden line-clamp-2 op-label font-normal text-muted-foreground md:block">{{ tile.description }}</span>
                        </span>
                      </span>
                      <span data-tile-status class="col-start-2 flex min-w-0 items-start gap-2 self-start op-label font-normal md:mt-auto md:min-h-[26px] md:pt-2">
                        <template v-if="tileStatus(tile).hasStatus">
                          <!-- O ponto diz o tom (âmbar pede alguém, verde está bem, neutro no
                               resto); a frase sempre escrita ao lado, a cor nunca fala sozinha. -->
                          <span
                            class="mt-[5.5px] size-[7px] shrink-0 rounded-full"
                            :class="{
                              'bg-warning': tileStatus(tile).tone === 'attention',
                              'bg-success': tileStatus(tile).tone === 'positive',
                              'bg-muted-foreground/50': tileStatus(tile).tone === 'neutral',
                            }"
                            :data-tile-tone="tileStatus(tile).tone"
                            aria-hidden="true"
                          />
                          <span class="min-w-0">
                            <template v-for="(part, index) in tileStatus(tile).parts" :key="part.role">
                              <span v-if="index" class="text-muted-foreground"> · </span>
                              <span
                                :class="{
                                  'font-semibold text-warning': part.role === 'attention',
                                  'text-muted-foreground': part.role === 'neutral' && tileStatus(tile).tone === 'attention',
                                }"
                              >{{ part.text }}</span>
                            </template>
                          </span>
                        </template>
                      </span>
                    </a>
                  </li>
                </ul>
              </section>
            </template>
            <!-- "Mais N apps abaixo" no celular: o aviso de rolagem da casa (kit). -->
            <MoreBelow />
          </div>
        </div>

        <!-- Rodapé calmo: avisos neste dispositivo (o gesto que cabe ao estado; o que chega
             e os dispositivos a um toque) e a versão publicada deste build, que é o que o
             operador lê para o suporte ao relatar algo. -->
        <footer class="border-t border-border">
          <div class="mx-auto w-full max-w-[1120px] px-4 py-3 md:px-8 md:py-2">
            <OperatorPushSettings variant="line">
              <template #end>
                <span class="ml-auto inline-flex min-h-control items-center tnum" data-hub-version>
                  Versão {{ HUB_NAMED_OF }}:&nbsp;<span class="font-mono text-foreground">{{ appVersion }}</span>
                </span>
              </template>
            </OperatorPushSettings>
          </div>
        </footer>
      </div>
    </div>

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
