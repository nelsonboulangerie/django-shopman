<script setup lang="ts">
// Central: a home do Shopman e o launcher pós-login, no shell da suíte (fase 2, variante
// "início", `home`: o selo do topo da barra lateral é identidade, sem "voltar à Central").
// A casca é a mesma dos apps migrados (`OperatorSuiteShell`): barra lateral em três estados
// na mesa, gaveta pelo ☰ e barra do topo no celular, com "Início" como única seção (por
// isso sem barra inferior: uma vaga só não aparece). A página é o `OperatorPageHeader`
// (saudação, selo de cadência, busca da suíte, avisos da tela e o ⋯ único) e o conteúdo:
// os apps, cada um com a linha de estado e, quando há, a pendência mais urgente dele como
// ação direta (leva ao item exato); os apps com pendência vêm primeiro. Tudo já vem filtrado por permissão.
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
  hubBrandLine,
  hubFailure,
  hubFailureCopy,
  hubDateLine,
  hubGreeting,
  hubIsEmpty,
  nextItemMeta,
  queueActionAriaLabel,
  readClockLabel,
  serverClockOffset,
  staleQueueAlert,
  tileAriaLabel,
  tileIcon,
  tileIconUrl,
  tileLinkAttrs,
  tilesByPendency,
  tileStatus,
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

// Os apps com pendência primeiro, na ordem de sempre entre si (a lista não pula quando
// a urgência muda). O relógio anda a cada segundo (a contagem "aceita sozinho em 2:40"
// não congela entre uma leitura e outra) e conta pela hora do servidor.
const sortedTiles = computed(() => tilesByPendency(tiles.value));
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

// A pendência abre do mesmo jeito que o app abriria: na janela própria do app quando a
// Central está instalada.
function nextItemLinkAttrs(item: HubQueueItemProjection) {
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
        home
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
                <!-- Os apps: o bloco inteiro é o link para o app, com a linha de estado.
                     A pendência mais urgente de cada app (`next_item`) é a ação direta da
                     linha, que leva ao item exato; os apps com pendência vêm primeiro, na
                     ordem de sempre entre si (dono, 09/10/2026: "Precisa de você" saiu, porque
                     empurrava os apps para baixo e repetia o que cada app já diz). -->
                <section aria-labelledby="hub-apps-title">
                  <div class="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <h2 id="hub-apps-title" class="text-base font-semibold">Apps</h2>
                    <OperatorCountChip :count="tiles.length" />
                    <p class="ms-auto text-xs text-muted max-md:hidden">{{ APPS_HINT_COPY }}</p>
                  </div>

                  <!-- Celular: os apps como linhas de 62 px, com chevron; nome e estado
                       quebram, nunca cortam. -->
                  <NuxtCard class="md:hidden" :ui="{ body: 'p-0 sm:p-0' }">
                    <ul class="divide-y divide-default" data-hub-apps-phone>
                      <li v-for="tile in sortedTiles" :key="tile.ref" data-hub-app-item>
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
                        <div v-if="tile.next_item" class="px-4 pb-3 ps-[68px]" data-hub-app-next>
                          <NuxtButton
                            :to="tile.next_item.url"
                            :target="nextItemLinkAttrs(tile.next_item).target"
                            :rel="nextItemLinkAttrs(tile.next_item).rel"
                            :aria-label="queueActionAriaLabel(tile.next_item)"
                            color="neutral"
                            variant="outline"
                            block
                            trailing-icon="i-lucide-arrow-right"
                            class="justify-between text-start"
                            data-hub-app-next-action
                          >
                            <span class="min-w-0 whitespace-normal">
                              <span class="block font-semibold">{{ tile.next_item.title }}</span>
                              <span
                                v-if="nextItemMeta(tile.next_item, nowMs)"
                                class="block text-xs font-normal"
                                :class="tile.next_item.attention ? 'text-warning' : 'text-muted'"
                              >{{ nextItemMeta(tile.next_item, nowMs) }}</span>
                            </span>
                          </NuxtButton>
                        </div>
                      </li>
                    </ul>
                  </NuxtCard>

                  <!-- Tablet e mesa: o destaque navegável canônico (`NuxtPageCard`). A
                       grade tem linhas de mesma altura; o texto quebra, nunca corta. -->
                  <NuxtPageGrid class="hidden auto-rows-fr gap-3 md:grid md:grid-cols-2 lg:grid-cols-4 lg:gap-3">
                    <NuxtPageCard
                      v-for="tile in sortedTiles"
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
                      <template v-if="tileStatus(tile).hasStatus || tile.next_item" #footer>
                        <span v-if="tileStatus(tile).hasStatus" class="flex min-w-0 items-start gap-2 text-sm" data-tile-status>
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
                        <!-- `relative z-[1]`: acima do link do cartão (a camada que cobre o
                             cartão inteiro), para a pendência levar ao item e não ao app. -->
                        <NuxtButton
                          v-if="tile.next_item"
                          :to="tile.next_item.url"
                          :target="nextItemLinkAttrs(tile.next_item).target"
                          :rel="nextItemLinkAttrs(tile.next_item).rel"
                          :aria-label="queueActionAriaLabel(tile.next_item)"
                          color="neutral"
                          variant="outline"
                          block
                          trailing-icon="i-lucide-arrow-right"
                          class="relative z-[1] mt-2 justify-between text-start"
                          data-hub-app-next-action
                        >
                          <span class="min-w-0 whitespace-normal">
                            <span class="block font-semibold">{{ tile.next_item.title }}</span>
                            <span
                              v-if="nextItemMeta(tile.next_item, nowMs)"
                              class="block text-xs font-normal"
                              :class="tile.next_item.attention ? 'text-warning' : 'text-muted'"
                            >{{ nextItemMeta(tile.next_item, nowMs) }}</span>
                          </span>
                        </NuxtButton>
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
