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

// As rodadas são um NuxtAccordion de abertura única: a mais nova abre sozinha, e
// tocar de novo na aberta fecha (o `collapsible` do componente). O valor do item é o
// id da rodada em texto, que é o que o Accordion guarda.
const rounds = computed(() =>
  (page.value?.reports ?? []).map((report: BIScenarioReportView) => ({ value: String(report.id), report })),
);
const openValue = computed(() => (openId.value === null ? undefined : String(openId.value)));
function pickRound(value: string | string[] | undefined) {
  const picked = Array.isArray(value) ? value[0] : value;
  openId.value = picked ? Number(picked) : null;
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
            <NuxtButton
              icon="i-lucide-sparkles"
              :label="generating ? 'Gerando… (leva alguns segundos)' : 'Gerar cenários'"
              :loading="generating"
              :disabled="generating"
              data-bi-generate
              @click="run"
            />
          </div>
          <p v-else class="op-body text-muted-foreground">
            Geração desligada neste ambiente: falta a credencial da IA (AI_ASSIST_API_KEY). Os relatórios já gerados seguem abaixo.
          </p>
        </BiSection>

        <NuxtCard v-if="rounds.length" as="section" aria-label="Rodadas registradas" data-bi-scenario-rounds>
          <NuxtAccordion :model-value="openValue" :items="rounds" @update:model-value="pickRound">
            <template #default="{ item }">
              <span class="min-w-0 text-left">
                <span class="block op-body font-medium text-foreground">{{ scenarioReportHeadline(item.report) }}</span>
                <span class="block op-micro font-normal text-muted-foreground">
                  {{ scenarioStatusLabel(item.report) }}
                  <template v-if="item.report.requested_by"> · pedido por {{ item.report.requested_by }}</template>
                </span>
              </span>
            </template>
            <template #trailing="{ open }">
              <span class="ms-auto inline-flex shrink-0 items-center gap-1.5 op-label">
                {{ open ? "Fechar" : "Abrir" }}
                <Icon :name="open ? 'lucide:chevron-up' : 'lucide:chevron-down'" class="size-4" aria-hidden="true" />
              </span>
            </template>
            <template #body="{ item }">
              <div class="flex flex-col gap-3" :data-bi-scenario-round="item.report.id">
                <p v-if="item.report.status === 'failed'" class="op-body text-muted-foreground">{{ item.report.error }}</p>
                <NuxtCard v-for="(scenario, index) in item.report.scenarios" :key="index" variant="subtle">
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
                </NuxtCard>
              </div>
            </template>
          </NuxtAccordion>
        </NuxtCard>
        <p v-else class="op-body text-muted-foreground">Nenhum cenário gerado ainda.</p>
      </template>
      <BiSwipeHint />
    </main>
  </div>
</template>
