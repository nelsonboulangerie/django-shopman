<script setup lang="ts">
// Cenários com IA: a IA lê os agregados (só a camada de leitura) e PROPÕE; quem decide
// é o gestor. Cada rodada é um relatório versionado: o que ela viu, o que devolveu,
// quanto demorou. Falha fica registrada, nunca inventada.
//
// Cânon do kit (PR-B6 do WP-BI-CANON-LAUDO): o Foco é um `NuxtSelect` com rótulo
// (lista curta e fixa, do servidor); os quadros são `OperatorReadingCard`; o cenário
// dentro da rodada é cartão `soft` (cartão dentro de cartão); vazio e carregando são
// `NuxtEmpty`.
import type { BIScenarioReportView } from "~/types/bi";
import { scenarioReportHeadline, scenarioStatusLabel } from "~/presentation/bi";

const { page, pending, error, refresh, generate, generating } = useBiScenarios();
const shareItems = useBiShareMenuItems();
const focus = ref("sales");
const openId = ref<number | null>(null);

watch(page, (value) => {
  if (value && openId.value === null && value.reports.length) openId.value = value.reports[0]!.id;
});

// Frescor da leitura. A página não traz `generated_at` próprio: o carimbo é a hora em
// que a última leitura chegou. `useState` leva o carimbo do servidor ao cliente, para
// a hidratação não discordar do texto.
const readAt = useState("bi-scenarios-read-at", () => new Date().toISOString());
watch(pending, (now, before) => {
  if (before && !now && !error.value) readAt.value = new Date().toISOString();
});
const readMetadata = computed(() => ({ generated_at: readAt.value }));

const focusItems = computed(() => (page.value?.focuses ?? []).map((item) => ({ label: item.label, value: item.key })));

// As rodadas são um NuxtAccordion de abertura única: a mais nova abre sozinha, e tocar
// de novo na aberta fecha (o `collapsible` do componente). O valor do item é o id da
// rodada em texto, que é o que o Accordion guarda.
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

const errorActions = computed(() => [
  {
    label: "Tentar de novo",
    icon: "i-lucide-refresh-cw",
    color: "error" as const,
    variant: "outline" as const,
    onClick: () => void refresh(),
  },
]);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Que cenários a IA propõe?">
      <template #actions>
        <OperatorReadingPageMenu :items="shareItems" />
      </template>
    </OperatorPageHeader>

    <main class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pt-3 pb-4">
      <NuxtEmpty
        v-if="pending && !page"
        loading
        icon="i-lucide-sparkles"
        title="Carregando os cenários"
        data-bi-loading
      />
      <NuxtAlert
        v-else-if="error && !page"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        title="Não deu para carregar os cenários."
        :actions="errorActions"
        orientation="horizontal"
        role="alert"
        data-bi-error
      />
      <template v-if="page">
        <OperatorReadingCard
          title="Pedir uma rodada"
          description="A IA lê só os agregados do B.I. (nunca pedido, cliente ou caixa) e propõe; quem decide é você. Cada rodada fica registrada com o que ela viu."
        >
          <div class="flex flex-wrap items-end gap-3">
            <template v-if="page.configured">
              <NuxtFormField label="Foco" class="min-w-40">
                <NuxtSelect v-model="focus" :items="focusItems" class="w-full" data-bi-scenario-focus />
              </NuxtFormField>
              <NuxtButton
                icon="i-lucide-sparkles"
                :label="generating ? 'Gerando… (leva alguns segundos)' : 'Gerar cenários'"
                :loading="generating"
                :disabled="generating"
                data-bi-generate
                @click="run"
              />
            </template>
            <NuxtAlert
              v-else
              color="info"
              variant="subtle"
              icon="i-lucide-info"
              title="Geração desligada neste ambiente"
              description="Falta a credencial da IA (AI_ASSIST_API_KEY). Os relatórios já gerados seguem abaixo."
              data-bi-generate-off
            />
            <ReadFreshness inline :metadata="readMetadata" :failed="Boolean(error)" class="self-center" />
          </div>
        </OperatorReadingCard>

        <OperatorReadingCard v-if="rounds.length" title="Rodadas registradas" data-bi-scenario-rounds>
          <NuxtAccordion :model-value="openValue" :items="rounds" @update:model-value="pickRound">
            <template #default="{ item }">
              <span class="min-w-0 text-left">
                <span class="block text-sm font-medium text-highlighted">{{ scenarioReportHeadline(item.report) }}</span>
                <span class="block text-xs text-muted">
                  {{ scenarioStatusLabel(item.report) }}
                  <template v-if="item.report.requested_by"> · pedido por {{ item.report.requested_by }}</template>
                </span>
              </span>
            </template>
            <template #trailing="{ open }">
              <span class="ms-auto inline-flex shrink-0 items-center gap-1.5 text-sm">
                {{ open ? "Fechar" : "Abrir" }}
                <Icon :name="open ? 'lucide:chevron-up' : 'lucide:chevron-down'" class="size-4" aria-hidden="true" />
              </span>
            </template>
            <template #body="{ item }">
              <div class="flex flex-col gap-3" :data-bi-scenario-round="item.report.id">
                <NuxtAlert
                  v-if="item.report.status === 'failed'"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-circle-alert"
                  title="A IA não respondeu no formato esperado"
                  :description="item.report.error"
                />
                <NuxtCard
                  v-for="(scenario, index) in item.report.scenarios"
                  :key="index"
                  variant="soft"
                  :description="scenario.proposal"
                >
                  <template #title><h3>{{ scenario.title }}</h3></template>
                  <div v-if="scenario.basis.length || scenario.unknowns.length" class="grid gap-3">
                    <section v-if="scenario.basis.length">
                      <h4 class="text-xs font-medium text-muted">O que sustenta</h4>
                      <ul class="mt-1 list-disc pl-5 text-sm">
                        <li v-for="(line, i) in scenario.basis" :key="i">{{ line }}</li>
                      </ul>
                    </section>
                    <section v-if="scenario.unknowns.length">
                      <h4 class="text-xs font-medium text-muted">O que os dados não dizem</h4>
                      <ul class="mt-1 list-disc pl-5 text-sm">
                        <li v-for="(line, i) in scenario.unknowns" :key="i">{{ line }}</li>
                      </ul>
                    </section>
                  </div>
                </NuxtCard>
              </div>
            </template>
          </NuxtAccordion>
        </OperatorReadingCard>
        <NuxtEmpty
          v-else
          icon="i-lucide-sparkles"
          title="Nenhum cenário gerado ainda"
          :description="
            page.configured
              ? 'Escolha o foco e toque em Gerar cenários: a rodada aparece aqui.'
              : 'Com a geração ligada, cada rodada aparece aqui.'
          "
          data-bi-scenario-empty
        />
      </template>
    </main>
  </div>
</template>
