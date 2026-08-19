<script setup lang="ts">
// Cenários com IA — a IA lê os agregados (só a camada de leitura) e PROPÕE;
// quem decide é o gestor. Cada rodada é um relatório versionado: o que ela
// viu, o que devolveu, quanto demorou. Falha fica registrada, nunca inventada.
import type { BIScenarioReportView } from "~/types/bi";
import { scenarioReportHeadline, scenarioStatusLabel } from "~/presentation/bi";

const { page, pending, error, refresh, generate, generating } = useBiScenarios();
const focus = ref("sales");
const openId = ref<number | null>(null);

watch(page, (value) => {
  if (value && openId.value === null && value.reports.length) openId.value = value.reports[0]!.id;
});

function toggle(report: BIScenarioReportView) {
  openId.value = openId.value === report.id ? null : report.id;
}

async function run() {
  const report = await generate(focus.value);
  if (report) openId.value = report.id;
}
</script>

<template>
  <main class="flex flex-1 flex-col gap-4 p-4">
    <p v-if="pending" class="text-sm text-muted-foreground">Carregando…</p>
    <div v-else-if="error" class="flex items-center gap-3">
      <p class="text-sm text-muted-foreground">Não deu para carregar os cenários.</p>
      <button type="button" class="h-9 rounded-md border border-border px-3 text-sm font-medium" @click="refresh()">
        Tentar de novo
      </button>
    </div>
    <template v-else-if="page">
      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">Cenários propostos pela IA</h2>
        <p class="mb-3 text-xs text-muted-foreground">
          A IA lê só os agregados do B.I. (nunca pedido, cliente ou caixa) e propõe; quem decide é você.
          Cada rodada fica registrada com o que ela viu.
        </p>
        <div v-if="page.configured" class="flex flex-wrap items-center gap-2">
          <label class="text-sm text-muted-foreground" for="scenario-focus">Foco</label>
          <select
            id="scenario-focus"
            v-model="focus"
            class="h-9 rounded-md border border-border bg-background px-2 text-sm"
          >
            <option v-for="item in page.focuses" :key="item.key" :value="item.key">{{ item.label }}</option>
          </select>
          <button
            type="button"
            class="h-9 rounded-md bg-foreground px-3 text-sm font-medium text-background disabled:opacity-50"
            :disabled="generating"
            @click="run"
          >
            {{ generating ? "Gerando… (leva alguns segundos)" : "Gerar cenários" }}
          </button>
        </div>
        <p v-else class="text-sm text-muted-foreground">
          Geração desligada neste ambiente: falta a credencial da IA (AI_ASSIST_API_KEY). Os relatórios já gerados seguem abaixo.
        </p>
      </section>

      <section v-if="page.reports.length" class="flex flex-col gap-3">
        <article
          v-for="report in page.reports"
          :key="report.id"
          class="rounded-md border border-border bg-card p-3"
        >
          <button type="button" class="flex w-full items-start justify-between gap-3 text-left" @click="toggle(report)">
            <span>
              <span class="block text-sm font-medium text-foreground">{{ scenarioReportHeadline(report) }}</span>
              <span class="block text-xs text-muted-foreground">
                {{ scenarioStatusLabel(report) }}
                <template v-if="report.requested_by"> · pedido por {{ report.requested_by }}</template>
              </span>
            </span>
            <span class="text-xs text-muted-foreground">{{ openId === report.id ? "fechar" : "abrir" }}</span>
          </button>
          <div v-if="openId === report.id" class="mt-3 flex flex-col gap-3">
            <p v-if="report.status === 'failed'" class="text-sm text-muted-foreground">{{ report.error }}</p>
            <div
              v-for="(scenario, index) in report.scenarios"
              :key="index"
              class="rounded-md border border-border p-3"
            >
              <h3 class="text-base font-semibold text-foreground">{{ scenario.title }}</h3>
              <p class="mt-1 text-sm text-foreground">{{ scenario.proposal }}</p>
              <p v-if="scenario.basis.length" class="mt-2 text-xs font-medium text-muted-foreground">O que sustenta</p>
              <ul v-if="scenario.basis.length" class="list-disc pl-5 text-xs text-muted-foreground">
                <li v-for="(line, i) in scenario.basis" :key="i">{{ line }}</li>
              </ul>
              <p v-if="scenario.unknowns.length" class="mt-2 text-xs font-medium text-muted-foreground">O que os dados não dizem</p>
              <ul v-if="scenario.unknowns.length" class="list-disc pl-5 text-xs text-muted-foreground">
                <li v-for="(line, i) in scenario.unknowns" :key="i">{{ line }}</li>
              </ul>
            </div>
          </div>
        </article>
      </section>
      <p v-else class="text-sm text-muted-foreground">Nenhum cenário gerado ainda.</p>
    </template>
  </main>
</template>
