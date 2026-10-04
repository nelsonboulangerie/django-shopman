<script setup lang="ts">
// Shell do Marketing. Casca fina: painel, regras e histórico são páginas
// próprias (pages/), e o shell segura o outlet + a chrome + o gate de operador.
//
// O destrave só pede a capability de entrar. A autorização de cada Action é
// revalidada no backend; abrir o app nunca concede publicação por herança.
const OPERATOR_PERM = "shop.view_marketing";
const {
  canIdentify,
  sessionState,
  sessionUnavailable,
  operator,
  lock,
  refresh: refreshSession,
  locked,
  stationRef,
} = useOperatorLock(OPERATOR_PERM);
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const publicConfig = useRuntimeConfig().public;
const hubUrl = publicConfig.operatorHubUrl as string;
// A cor do app (a mesma do selo no rail) vira `--app-color` no `<html>`: as miniaturas
// da fila de decisões e o carimbo do selo usam o tom dela, como na prévia v4. No
// `<html>`, e não no shell, porque o selo é diálogo teleportado para fora dele.
const appColor = (
  publicConfig.operatorPwa as { identity?: { color?: string } } | undefined
)?.identity?.color;
if (appColor) useHead({ htmlAttrs: { style: `--app-color: ${appColor}` } });
const { attrsFor: appLinkAttrsFor } = useOperatorAppLink();
const hubLink = computed(() => appLinkAttrsFor(hubUrl));

useOperatorWindowTitle();
const route = useRoute();

watch(sessionState, async (next, previous) => {
  if (next !== "authenticated" || previous === "authenticated") return;
  await nextTick();
  const heading = document.querySelector<HTMLElement>(
    "[data-marketing-app-root] main h1",
  );
  heading?.setAttribute("tabindex", "-1");
  heading?.focus();
});
</script>

<template>
  <!-- NuxtPage fica presente para o router, mas a página recebida pelo slot só é
       instanciada depois do gate. Isso evita tanto fetch anônimo quanto o falso
       warning do Nuxt causado por remover condicionalmente o próprio outlet. -->
  <NuxtPage v-slot="{ Component }">
    <!-- `data-suite="v3"`: o Marketing veste a camada visual da suíte (V4-MKT, modelo:
         o Gestor). Os primitivos do kit leem esse atributo para vestir o visual das
         prévias. -->
    <div
      data-marketing-app-root
      data-suite="v3"
      class="flex min-h-dvh bg-background text-foreground"
    >
      <NuxtRouteAnnouncer />
      <!-- Aviso calmo de conexão (kit) — global, só aparece offline. -->
      <OfflineBanner />
      <!-- O app protegido só existe depois de sessão + capability confirmadas. O
         login deixou de ser uma cortina sobre fetches e timers já montados. -->
      <template v-if="sessionState === 'authenticated'">
        <!-- Rail da suíte (kit): o selo do app (Central), as seções do Marketing,
             Bloquear e o menu do operador. Do tablet para cima; no celular as seções
             vão para a barra do polegar, no fim da coluna de conteúdo. -->
        <MarketingNav
          place="rail"
          :hub-url="hubUrl"
          :operator-name="operator?.name"
          @lock="lock"
        />
        <div class="flex min-w-0 flex-1 flex-col">
          <component :is="Component" />
          <!-- Barra do polegar (celular): no fim da COLUNA, não da janela, para
               nunca cobrir o que estiver à esquerda. Ver MarketingNav.vue. A revisão do
               anúncio é tela cheia (v4: o polegar é de Recusar e Continuar), e a página
               declara isso em `definePageMeta({ fullscreen: true })`. -->
          <MarketingNav v-if="!route.meta.fullscreen" place="bar" :operator-name="operator?.name" @lock="lock" />
        </div>
        <!-- A caixa pessoal (SSE, poll, "visto"): uma só, em qualquer largura. -->
        <MarketingInboxLive />
      </template>

      <main
        v-else-if="sessionUnavailable"
        class="grid min-h-screen flex-1 place-items-center p-4"
      >
        <div class="max-w-sm rounded-md border bg-card p-6 text-center">
          <Icon
            name="lucide:wifi-off"
            class="mx-auto size-7 text-muted-foreground"
          />
          <h1 class="mt-3 text-lg font-semibold">
            Não foi possível conferir seu acesso
          </h1>
          <p class="mt-1 text-sm text-muted-foreground">
            O painel continua fechado e nenhum dado de Marketing foi carregado.
          </p>
          <UiButton
            type="button"
            variant="outline"
            class="mt-4"
            @click="refreshSession()"
          >
            Tentar de novo
          </UiButton>
        </div>
      </main>

      <main
        v-else-if="sessionState === 'checking'"
        class="grid min-h-screen flex-1 place-items-center p-4"
        aria-busy="true"
      >
        <p class="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon
            name="line-md:loading-loop"
            class="size-5 motion-reduce:animate-none"
          />
          Conferindo seu acesso…
        </p>
      </main>

      <main
        v-else-if="sessionState === 'forbidden'"
        class="grid min-h-screen flex-1 place-items-center p-4"
      >
        <div class="max-w-sm rounded-md border bg-card p-6 text-center">
          <Icon
            name="lucide:shield-x"
            class="mx-auto size-7 text-muted-foreground"
          />
          <h1 class="mt-3 text-lg font-semibold">
            Seu acesso não inclui Marketing
          </h1>
          <p class="mt-1 text-sm text-muted-foreground">
            Entrar de novo não resolve. Peça a um responsável o acesso ao
            Marketing.
          </p>
          <!-- Mesma regra do ícone da Central no rail: instalado, ele abre na
               janela DELA (ver operator-kit/app/presentation/appLaunch.ts). -->
          <a
            :href="hubUrl"
            :target="hubLink.target"
            :rel="hubLink.rel"
            class="mt-4 inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-semibold hover:bg-muted"
          >
            Voltar à Central
          </a>
        </div>
      </main>

      <OperatorLogin
        v-else-if="sessionState === 'expired' || !canIdentify"
        role="main"
        :expired="sessionState === 'expired'"
        :reload-on-success="false"
      />
      <OperatorLock v-else :perm="OPERATOR_PERM" />
      <OperatorStationSetup
        v-if="stationSetup.offer.value"
        @done="stationSetup.done()"
        @dismiss="stationSetup.dismiss()"
        @unavailable="stationSetup.dismiss({ remember: false })"
      />
      <OperatorSonner />
      <OperatorPwaRuntime />
    </div>
  </NuxtPage>
</template>
