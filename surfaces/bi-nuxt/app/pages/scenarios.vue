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
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Que cenários a IA propõe?">
      <template #status>
        <BiLiveStatus :pending="pending" :error="error" />
      </template>
      <template #actions>
        <BiPageMenu />
      </template>
      <template #phone-actions>
        <BiShareButton />
        <BiPhoneBell />
      </template>
    </OperatorPageHeader>

    <main class="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
      <BiPageState :pending="pending && !page" :error="error" what="os cenários" @retry="refresh()" />
      <template v-if="page">
        <BiSection
          title="Pedir uma rodada"
          caption="A IA lê só os agregados do B.I. (nunca pedido, cliente ou caixa) e propõe; quem decide é você. Cada rodada fica registrada com o que ela viu."
        >
          <div v-if="page.configured" class="flex flex-wrap items-center gap-2">
            <label class="op-label text-muted-foreground" for="scenario-focus">Foco</label>
            <UiNativeSelect id="scenario-focus" v-model="focus">
              <option v-for="item in page.focuses" :key="item.key" :value="item.key">{{ item.label }}</option>
            </UiNativeSelect>
            <button
              type="button"
              class="inline-flex min-h-control items-center gap-2 rounded-md bg-primary px-4 op-label font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
              :disabled="generating"
              @click="run"
            >
              <Icon name="lucide:sparkles" class="size-4" aria-hidden="true" />
              {{ generating ? "Gerando… (leva alguns segundos)" : "Gerar cenários" }}
            </button>
          </div>
          <p v-else class="op-body text-muted-foreground">
            Geração desligada neste ambiente: falta a credencial da IA (AI_ASSIST_API_KEY). Os relatórios já gerados seguem abaixo.
          </p>
        </BiSection>

        <section v-if="page.reports.length" class="overflow-hidden rounded-lg border border-border bg-card" aria-label="Rodadas registradas">
          <article
            v-for="report in page.reports"
            :key="report.id"
            class="border-b border-border last:border-0"
          >
            <button
              type="button"
              class="flex min-h-control w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-accent"
              :class="openId === report.id ? 'bg-primary/5' : ''"
              :aria-expanded="openId === report.id"
              @click="toggle(report)"
            >
              <span class="min-w-0">
                <span class="block op-body font-medium text-foreground">{{ scenarioReportHeadline(report) }}</span>
                <span class="block op-micro text-muted-foreground">
                  {{ scenarioStatusLabel(report) }}
                  <template v-if="report.requested_by"> · pedido por {{ report.requested_by }}</template>
                </span>
              </span>
              <span class="inline-flex shrink-0 items-center gap-1.5 op-label">
                {{ openId === report.id ? "Fechar" : "Abrir" }}
                <Icon :name="openId === report.id ? 'lucide:chevron-up' : 'lucide:chevron-down'" class="size-4" aria-hidden="true" />
              </span>
            </button>
            <div v-if="openId === report.id" class="flex flex-col gap-3 bg-primary/5 px-4 pb-3">
              <p v-if="report.status === 'failed'" class="op-body text-muted-foreground">{{ report.error }}</p>
              <div
                v-for="(scenario, index) in report.scenarios"
                :key="index"
                class="rounded-lg border border-border bg-card px-4 py-3"
              >
                <h3 class="op-title text-foreground">{{ scenario.title }}</h3>
                <p class="mt-1 op-body text-foreground">{{ scenario.proposal }}</p>
                <p v-if="scenario.basis.length" class="mt-2 op-eyebrow text-muted-foreground">O que sustenta</p>
                <ul v-if="scenario.basis.length" class="list-disc pl-5 op-label text-muted-foreground">
                  <li v-for="(line, i) in scenario.basis" :key="i">{{ line }}</li>
                </ul>
                <p v-if="scenario.unknowns.length" class="mt-2 op-eyebrow text-muted-foreground">O que os dados não dizem</p>
                <ul v-if="scenario.unknowns.length" class="list-disc pl-5 op-label text-muted-foreground">
                  <li v-for="(line, i) in scenario.unknowns" :key="i">{{ line }}</li>
                </ul>
              </div>
            </div>
          </article>
        </section>
        <p v-else class="op-body text-muted-foreground">Nenhum cenário gerado ainda.</p>
      </template>
      <BiSwipeHint />
    </main>
  </div>
</template>
