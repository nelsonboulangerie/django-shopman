<script setup lang="ts">
// Production surface shell (prod.). Thin shell com duas classes de
// tela (verificadas endpoint a endpoint):
//   · telas de OPERADOR (planejamento/preparação/produção/expedição) → rail canônico
//     (kit) + conteúdo, atrás do gate de operador;
//   · painel (Fornadas) → KIOSK de operador em tela cheia (a previsão exige
//     backstage.operate_production) — FORA do rail, mas DENTRO do gate;
// O menuboard paralelo foi aposentado: a TV canônica pertence ao Django, por ref e
// credencial. D4 definirá refs/cutover; este app não adivinha um destino.
const OPERATOR_PERM = "backstage.operate_production";
const { canIdentify, locked, mustChange, operator, lock } =
  useOperatorLock(OPERATOR_PERM);
const { allowed: reportsAllowed } = useReportsAccess();
const { canView: recipesAllowed } = useRecipeBookAccess();

const route = useRoute();
const isKiosk = computed(() => route.path.startsWith("/board"));

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useHead({ title: "Produção" });

async function goToBoard() {
  await navigateTo("/board");
}

async function goToReports() {
  await navigateTo("/reports");
}

async function goToRecipes() {
  await navigateTo("/recipes");
}
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo e global de conexão (kit) — só aparece offline (paridade c/ POS/KDS/Gestor). -->
    <OfflineBanner />
    <!-- Painel de operador em modo kiosk: tela cheia, sem rail, ainda atrás do gate. -->
    <NuxtPage v-if="isKiosk" />
    <!-- Telas de operador: rail canônico (kit) + conteúdo. -->
    <div v-else class="flex min-h-screen">
      <div
        v-if="canIdentify"
        class="sticky top-0 flex h-screen shrink-0 print:hidden"
      >
        <OperatorRail
          app-icon="croissant"
          app-label="Produção"
          :central-url="hubUrl"
          :operator-name="operator?.name"
          @lock="lock"
        >
          <!-- O que não é etapa do fluxo sai das abas e mora aqui: o Letreiro
               (kiosk de TV, tela cheia), as Receitas (o inventário da casa, só
               com o acesso de leitura — a sonda pergunta ao backend) e os
               Relatórios (persona gestor, só com a perm fina). -->
          <template #nav>
            <RailItem
              icon="tower-control"
              label="Letreiro"
              :active="route.path.startsWith('/board')"
              @activate="goToBoard"
            />
            <RailItem
              v-if="recipesAllowed"
              icon="book-open"
              label="Receitas"
              :active="route.path.startsWith('/recipes')"
              @activate="goToRecipes"
            />
            <RailItem
              v-if="reportsAllowed"
              icon="table-2"
              label="Relatórios"
              :active="route.path.startsWith('/reports')"
              @activate="goToReports"
            />
          </template>
        </OperatorRail>
      </div>
      <div class="flex min-w-0 flex-1 flex-col">
        <NuxtPage />
      </div>
    </div>
    <OperatorLogin v-if="!canIdentify" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <OperatorSonner />
  </div>
</template>
