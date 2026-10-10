<script setup lang="ts">
// Casca do app: gate de operador + raiz Nuxt UI + outlet. A página compõe o
// shell canônico do catálogo sem manter uma segunda navegação local.
const OPERATOR_PERM = "backstage.view_operator_kitchen_sink";
// Harness hermético só existe no dev server da matriz visual (ver nuxt.config.ts);
// a env não liga o atalho quando NODE_ENV=production.
const harness = useRuntimeConfig().public.kitchenSinkHarness === true;
const gate = harness
  ? {
      canIdentify: ref(true),
      sessionState: ref("authenticated"),
      sessionUnavailable: ref(false),
      refresh: async () => undefined,
      locked: ref(false),
      mustChange: ref(false),
    }
  : useOperatorLock(OPERATOR_PERM);
const { canIdentify, sessionState, sessionUnavailable, refresh, locked, mustChange } = gate;
// Uma única fonte decide o que aparece em cada estado. Sem ela, "checking" podia
// empilhar o esqueleto com a tela de senha, e canIdentify sozinho liberava a
// página de quem estava apenas "identified" (sem permissão).
const surface = computed(() =>
  operatorSurfaceGate({
    sessionState: sessionState.value,
    canIdentify: canIdentify.value,
    sessionUnavailable: sessionUnavailable.value,
    locked: locked.value,
    mustChange: mustChange.value,
    harness,
  }),
);

useOperatorWindowTitle();
</script>

<template>
  <OperatorAppRoot>
    <NuxtRouteAnnouncer />
    <OfflineBanner />
    <NuxtPage v-slot="{ Component }"><component :is="Component" v-if="surface.showPage" /></NuxtPage>
    <main v-if="surface.showForbidden"><NuxtEmpty icon="i-lucide-shield-x" title="Seu acesso não inclui o Catálogo do operador" description="Peça a um responsável a permissão de acesso. Entrar novamente não concede essa permissão." /></main>
    <main v-else-if="surface.showChecking" role="status" aria-busy="true"><NuxtSkeleton class="h-48" /><p>Conferindo acesso ao Catálogo do operador.</p></main>
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy
         subiria a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="surface.showUnavailable" scope="o Catálogo do operador" @retry="refresh()" />
    <OperatorLogin v-if="surface.showLogin" />
    <OperatorLock v-else-if="surface.showLock" :perm="OPERATOR_PERM" />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </OperatorAppRoot>
</template>
