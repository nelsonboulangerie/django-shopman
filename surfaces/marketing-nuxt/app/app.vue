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
} = useOperatorLock(OPERATOR_PERM);

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useHead({ title: "Marketing" });
</script>

<template>
  <!-- NuxtPage fica presente para o router, mas a página recebida pelo slot só é
       instanciada depois do gate. Isso evita tanto fetch anônimo quanto o falso
       warning do Nuxt causado por remover condicionalmente o próprio outlet. -->
  <NuxtPage v-slot="{ Component }">
    <div class="flex min-h-screen bg-background text-foreground">
      <NuxtRouteAnnouncer />
      <!-- Aviso calmo de conexão (kit) — global, só aparece offline. -->
      <OfflineBanner />
      <!-- O app protegido só existe depois de sessão + capability confirmadas. O
         login deixou de ser uma cortina sobre fetches e timers já montados. -->
      <template v-if="sessionState === 'authenticated'">
        <div class="sticky top-0 flex h-screen shrink-0 print:hidden">
          <OperatorRail
            app-icon="megaphone"
            app-label="Marketing"
            :central-url="hubUrl"
            :operator-name="operator?.name"
            @lock="lock"
          />
        </div>
        <div class="flex min-w-0 flex-1 flex-col">
          <CampaignTopBar />
          <component :is="Component" />
        </div>
      </template>

      <main
        v-else-if="sessionUnavailable"
        class="grid min-h-screen flex-1 place-items-center p-4"
      >
        <div class="max-w-sm rounded-xl border bg-card p-6 text-center">
          <Icon
            name="lucide:wifi-off"
            class="mx-auto size-7 text-muted-foreground"
          />
          <h1 class="mt-3 text-lg font-bold">
            Não foi possível conferir seu acesso
          </h1>
          <p class="mt-1 text-sm text-muted-foreground">
            O painel continua fechado e nenhum dado de Marketing foi carregado.
          </p>
          <button
            type="button"
            class="mt-4 min-h-11 rounded-md border border-border px-4 text-sm font-semibold hover:bg-muted"
            @click="refreshSession()"
          >
            Tentar novamente
          </button>
        </div>
      </main>

      <main
        v-else-if="sessionState === 'checking'"
        class="grid min-h-screen flex-1 place-items-center p-4"
        aria-busy="true"
      >
        <p class="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon name="line-md:loading-loop" class="size-5" />
          Conferindo seu acesso…
        </p>
      </main>

      <main
        v-else-if="sessionState === 'forbidden'"
        class="grid min-h-screen flex-1 place-items-center p-4"
      >
        <div class="max-w-sm rounded-xl border bg-card p-6 text-center">
          <Icon
            name="lucide:shield-x"
            class="mx-auto size-7 text-muted-foreground"
          />
          <h1 class="mt-3 text-lg font-bold">
            Seu acesso não inclui Marketing
          </h1>
          <p class="mt-1 text-sm text-muted-foreground">
            Entrar novamente não amplia permissões. Peça a um responsável o
            acesso
            <span class="font-mono">shop.view_marketing</span>.
          </p>
          <a
            :href="hubUrl"
            class="mt-4 inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-semibold hover:bg-muted"
          >
            Voltar à Central
          </a>
        </div>
      </main>

      <OperatorLogin
        v-else-if="sessionState === 'expired' || !canIdentify"
        :expired="sessionState === 'expired'"
      />
      <OperatorLock v-else :perm="OPERATOR_PERM" />
      <UiSonner />
    </div>
  </NuxtPage>
</template>
