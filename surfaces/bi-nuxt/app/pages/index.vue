<script setup lang="ts">
// Produção: a âncora do B.I. A pergunta nº 1 do dono (prévia `bi-sobra4.html`,
// LEITURA: pergunta, resposta, comparação, aprofundar): "Sobrou ou faltou ontem?",
// produto a produto, contra o mesmo dia da semana.
//
// Um tempo por tela (laudo F08): esta lê UM dia, e o dia mora no cabeçalho, no
// `OperatorPeriodPicker` do kit em modo de um dia (‹ › andam para o dia aberto
// anterior/seguinte que o servidor informa). Os lotes no período (a janela de
// análise) são a segunda aba (`?view=lots`, `ProductionLots`), e o cabeçalho dela
// troca o dia pelo período; as abas abrem a linha de recortes (`ProductionViewNav`).
//
// O dia continua na URL (`?day=`, `useBiOverShort`): o "Copiar link desta leitura"
// do ⋯ leva a mesma leitura. O endereço não aparece mais escrito na tela (F14).
import type { DropdownMenuItem, TableColumn } from "#ui/types";
import type { BIOverShortRow, BIProductionReport, BIReading } from "~/types/bi";
import { formatInt, formatQty } from "~/presentation/bi";
import {
  VERDICTS,
  barScale,
  carryLabel,
  collectionsOf,
  compareCaption,
  compareOptions,
  filterRows,
  hiddenRowsSummary,
  historyHeading,
  historyText,
  outcomeText,
  overShortAnswer,
  overShortCsv,
  overShortTitle,
  overUnit,
  planLabel,
  shortUnit,
  showHiddenLabel,
  soldoutText,
  typicalLine,
  verdictColor,
  verdictMeta,
  versusTypicalText,
} from "~/presentation/overShort";
import { productionView } from "~/presentation/production";
import {
  periodAnchor,
  periodOfDay,
  todayIso,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";

const {
  report: day,
  freshness: dayFreshness,
  pending: dayPending,
  error: dayError,
  refresh: dayRefresh,
  setDay,
  compare,
  setCompare,
} = useBiOverShort();

const route = useRoute();
const router = useRouter();
const today = todayIso();
const view = computed(() => productionView(route.query.view));
const { selection: lotsWindow, bounds, presets } = useBiWindow();
// O frescor da aba aberta: o dia (over-short) ou os lotes (a leitura de produção, que
// o `ProductionLots` busca; aqui só se lê o que ele já trouxe, pela mesma chave).
const { data: lotsReading } = useNuxtData<BIReading<BIProductionReport>>("bi-production");
const freshness = computed(() =>
  view.value === "lots" ? { generated_at: lotsReading.value?.generated_at ?? null } : dayFreshness.value,
);
const yesterday = computed(() => {
  const [y, m, d] = today.split("-").map(Number);
  return new Date(Date.UTC(y!, (m ?? 1) - 1, (d ?? 1) - 1)).toISOString().slice(0, 10);
});

// O dia da leitura no período do kit (modo de um dia). Sem `?day=`, o servidor lê o
// último dia aberto, e é esse dia que o controle mostra.
const readingDay = computed<PeriodSelection>({
  get: () => periodOfDay("day", day.value?.day ?? yesterday.value, today),
  // "Voltar para hoje" do controle pede o dia em curso, que ainda não tem resposta:
  // aí a leitura volta ao padrão do servidor (o último dia aberto), sem `?day=`.
  set: (selection) => {
    const anchor = periodAnchor(selection, today);
    if (anchor <= yesterday.value) {
      setDay(anchor);
      return;
    }
    const rest = { ...route.query };
    delete rest.day;
    void router.replace({ query: rest });
  },
});

// No celular a barra de 56px não comporta a pergunta com o dia: o dia já está no
// controle ao lado, então o título fica só com a pergunta (nunca cortado). `ssrWidth`:
// o servidor e a primeira pintura concordam (sem erro de hidratação).
const isPhone = useMediaQuery("(max-width: 767.98px)", { ssrWidth: 1280 });
const title = computed(() => {
  if (view.value === "lots") return isPhone.value ? "Lotes no período" : "Como foram os lotes no período?";
  if (isPhone.value) return "Sobrou ou faltou?";
  return day.value ? overShortTitle(day.value.day, today) : "Sobrou ou faltou ontem?";
});

const query = ref("");
const verdict = ref("all");
const collection = ref("all");
const showAll = ref(false);
const expanded = ref<Record<string, boolean>>({});
watch(
  () => day.value?.day,
  () => {
    expanded.value = {};
    showAll.value = false;
  },
);

/** Linhas em foco antes do "Ver os outros N" (densidade pela atenção, SPEC4 §4). */
const FOCUS_ROWS = 8;
const rows = computed(() => day.value?.rows ?? []);
const filters = computed(() => ({
  verdict: verdict.value === "all" ? "" : verdict.value,
  collection: collection.value === "all" ? "" : collection.value,
  query: query.value,
}));
const filtered = computed(() => filterRows(rows.value, filters.value));
const narrowed = computed(() => Boolean(filters.value.verdict || filters.value.collection || query.value.trim()));
const visible = computed(() => (showAll.value || narrowed.value ? filtered.value : filtered.value.slice(0, FOCUS_ROWS)));
const hidden = computed(() => (showAll.value || narrowed.value ? [] : filtered.value.slice(FOCUS_ROWS)));
const scale = computed(() => barScale(rows.value));
const counts = computed(() => ({
  short: day.value?.summary.short ?? 0,
  over: day.value?.summary.over ?? 0,
  right: day.value?.summary.right ?? 0,
}));

// Recorte por veredito: NuxtTabs em pílula do tablet para cima (escolha de UM entre
// quatro, com o "Todos" na fileira); no celular as quatro pílulas não cabem e cortavam
// ("Na me…", laudo F18), então o mesmo recorte vira um NuxtSelect (lista curta e fixa).
const verdictItems = computed(() => [
  { value: "all", label: "Todos", badge: rows.value.length },
  ...VERDICTS.map((key) => ({ value: key, label: verdictMeta(key).label, badge: counts.value[key] })),
]);
const verdictOptions = computed(() =>
  verdictItems.value.map((item) => ({ value: item.value, label: `${item.label} (${item.badge})` })),
);
const CHIP_DOT = { short: "bg-error", over: "bg-warning", right: "bg-success" } as const;
const VERDICT_TEXT = { error: "text-error", warning: "text-warning", success: "text-success" } as const;

// Coleção: a lista cresce com o catálogo, então é NuxtSelectMenu com busca; a busca
// só recebe o foco ao abrir onde há teclado físico.
const touch = useMediaQuery("(pointer: coarse)");
const collectionItems = computed(() => [
  { value: "all", label: "Todas as coleções" },
  ...collectionsOf(rows.value).map((item) => ({ value: item.ref, label: item.name })),
]);

const compareItems = computed(() =>
  day.value ? compareOptions(day.value.day).map((option) => ({ value: option.key, label: `${option.label} (${option.reach})` })) : [],
);

const config = useRuntimeConfig().public as { productionUrl?: string; ordersUrl?: string };
const productionUrl = (config.productionUrl || "").replace(/\/?$/, "/");
const ordersUrl = (config.ordersUrl || "").replace(/\/?$/, "/");
const planUrl = computed(() => (day.value?.plan_day && productionUrl ? `${productionUrl}plan?date=${day.value.plan_day}` : ""));
const closeUrl = computed(() => (day.value && productionUrl ? `${productionUrl}close?date=${day.value.day}` : ""));
const { attrsFor } = useOperatorAppLink();
const planLink = computed(() => attrsFor(planUrl.value));

// "Levar ao plano do próximo sábado" (pino 3): a falta e a sobra viram o porquê ao
// lado da sugestão do Planejamento. Não muda número nenhum do plano.
const { run: carryToPlan, pending: carrying } = usePendingAction(async () => {
  if (!day.value) return;
  try {
    const result = await $fetch<{ plan_day: string; carried: number }>("/api/v1/backstage/bi/over-short/carry/", {
      method: "POST",
      body: { day: day.value.day, compare: compare.value },
    });
    if (!result.carried) {
      useSonner.info("Nada a levar: tudo ficou na medida neste dia.");
      return;
    }
    useSonner.success(
      `${result.carried === 1 ? "1 produto levado" : `${result.carried} produtos levados`} ao plano de ${planLabel(result.plan_day).replace(/^Abrir o plano de /, "")}: o porquê aparece ao lado da sugestão.`,
      planUrl.value ? { action: { label: "Abrir o plano", onClick: () => window.open(planUrl.value, planLink.value.target || "_self") } } : undefined,
    );
  } catch (error) {
    useSonner.error(httpErrorMessage(error, "Não deu para levar ao plano. Tente de novo."));
  }
});
const explainOpen = ref(false);
// "Como é calculado" é um item do ⋯ da página (o menu do kit recebe os itens por prop).
const shareItems = useBiShareMenuItems();
const pageMenuItems = computed<DropdownMenuItem[]>(() => [
  ...shareItems.value,
  ...(view.value === "lots" ? [] : [{
    label: explainOpen.value ? "Esconder como é calculado" : "Como é calculado",
    icon: "i-lucide-circle-help",
    onSelect: () => {
      explainOpen.value = !explainOpen.value;
    },
  }]),
]);

// Teclas do desktop: [ e ] andam um dia aberto; / leva à busca.
const search = ref<{ focus: () => void } | null>(null);
function typing(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  return Boolean(target?.closest("input, textarea, select, [contenteditable='true']"));
}
onKeyStroke("[", (event) => {
  if (typing(event) || view.value !== "day" || !day.value?.previous_day) return;
  setDay(day.value.previous_day);
});
onKeyStroke("]", (event) => {
  if (typing(event) || view.value !== "day" || !day.value?.next_day) return;
  setDay(day.value.next_day);
});
onKeyStroke("/", (event) => {
  if (typing(event)) return;
  event.preventDefault();
  search.value?.focus();
});

// A tabela (laudo F04): NuxtTable com cabeçalho de verdade e a linha que abre o
// detalhe ("Ver lotes e vendas") embaixo dela. Do celular ao desktop largo as colunas
// secundárias recolhem para dentro da célula do produto (`meta.class`): nenhuma
// informação fica só no desktop, e a página não rola de lado.
const HIDE_BELOW_SM = { th: "max-sm:hidden", td: "max-sm:hidden" };
const HIDE_BELOW_MD = { th: "max-md:hidden", td: "max-md:hidden" };
const HIDE_BELOW_LG = { th: "max-lg:hidden", td: "max-lg:hidden" };
const columns = computed<TableColumn<BIOverShortRow>[]>(() => [
  { id: "product", header: "Produto" },
  { id: "verdict", header: "Veredito", meta: { class: HIDE_BELOW_MD } },
  { id: "made_sold", header: "Fez × vendeu", meta: { class: HIDE_BELOW_SM } },
  { id: "soldout", header: "Acabou às", meta: { class: HIDE_BELOW_LG } },
  {
    id: "history",
    header: day.value ? historyHeading(day.value.day, day.value.compare_days) : "Nos dias iguais",
    meta: { class: HIDE_BELOW_LG },
  },
  { id: "typical", header: "Contra o típico", meta: { class: HIDE_BELOW_LG } },
  { id: "open", header: "", meta: { class: { th: "text-end", td: "text-end" } } },
]);
const csv = computed(() => overShortCsv(filtered.value));
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader :title="title">
      <template v-if="view === 'day'" #search>
        <OperatorSuiteSearch ref="search" v-model="query" screen-label="filtrando a tabela" placeholder="Buscar produto ou SKU" aria-label="Buscar produto ou SKU" />
      </template>
      <template #actions>
        <OperatorReadingPageMenu :items="pageMenuItems" />
      </template>
      <!-- Um tempo por aba, no mesmo lugar das outras telas: o primeiro da linha de
           recortes. A aba "Sobrou ou faltou" lê um dia; "Lotes no período", a janela. -->
      <template #filters>
        <OperatorPeriodPicker
          v-if="view === 'lots'"
          v-model="lotsWindow"
          :presets="presets"
          custom
          compact
          :today="bounds.today"
          :max="bounds.max"
          :epoch="bounds.epoch"
          align="start"
          label="Período de análise"
          data-bi-window
        />
        <OperatorPeriodPicker
          v-else-if="day"
          v-model="readingDay"
          compact
          :today="today"
          :max="yesterday"
          :prev-day="day.previous_day || ''"
          :next-day="day.next_day || ''"
          align="start"
          label="Dia da leitura"
          data-bi-reading-day
        />
        <ProductionViewNav />
        <template v-if="view === 'day' && day">
          <NuxtFormField label="Comparar com" orientation="horizontal" :hint="isPhone ? undefined : compareCaption(day.day, day.compare_days)" data-bi-compare>
            <NuxtSelect :model-value="compare" :items="compareItems" @update:model-value="setCompare(String($event))" />
          </NuxtFormField>
          <div class="max-sm:hidden">
            <NuxtTabs
              v-model="verdict"
              :items="verdictItems"
              :content="false"
              variant="pill"
              aria-label="Recorte por veredito"
              data-bi-verdict-tabs
            >
              <template #leading="{ item }">
                <span v-if="item.value !== 'all'" class="size-2 rounded-full" :class="CHIP_DOT[item.value as keyof typeof CHIP_DOT]" aria-hidden="true" />
              </template>
            </NuxtTabs>
          </div>
          <NuxtFormField label="Veredito" orientation="horizontal" class="sm:hidden" data-bi-verdict-select>
            <NuxtSelect v-model="verdict" :items="verdictOptions" />
          </NuxtFormField>
          <NuxtFormField v-if="collectionItems.length > 1" label="Coleção" orientation="horizontal" data-bi-collection>
            <NuxtSelectMenu v-model="collection" :items="collectionItems" value-key="value" :search-input="{ autofocus: !touch, placeholder: 'Buscar coleção' }" />
          </NuxtFormField>
        </template>
        <ClientOnly>
          <ReadFreshness inline class="ms-auto" :metadata="freshness" :failed="view === 'day' && Boolean(dayError)" />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <template v-if="view === 'day'">
        <BiPageState :error="dayError" what="a leitura do dia" @retry="dayRefresh()" />

        <NuxtCard v-if="day && explainOpen" title="Como é calculado" class="text-sm leading-6" data-bi-explain>
          <p><b>Fez</b>: o realizado dos lotes fechados do dia. <b>Vendeu</b>: as vendas do dia, de todos os canais.</p>
          <p><b>Acabou às</b>: a hora da venda em que o vendido alcançou o feito. <b>Vendas perdidas</b>: o ritmo até acabar, estendido até o fechamento{{ day.closes_at ? ` (${day.closes_at})` : "" }}, com teto de 2× o vendido. É a mesma conta que a sugestão do Planejamento usa.</p>
          <p><b>Faltou</b>: acabou antes da última hora. <b>Na medida</b>: acabou na última hora, sobrou até 2, ou vendeu mais do que fez (havia estoque de antes). <b>Sobrou</b>: sobrou mais que isso. A comparação é a média dos últimos {{ day.compare_days.length || 4 }} dias iguais com a loja aberta.</p>
          <p><b>Custo</b>: a ficha técnica ativa vezes o custo do fornecedor preferencial de cada insumo. Insumo sem custo deixa o produto sem custo (nada é estimado).</p>
        </NuxtCard>

        <!-- A resposta: uma frase e três números, cada um com o típico ao lado. -->
        <div v-if="day" class="grid gap-3 sm:grid-cols-3 xl:grid-cols-4">
          <OperatorMetric title="A resposta" :value="overShortAnswer(day)" size="statement" class="sm:col-span-3 xl:col-span-1" />
          <OperatorMetric title="Faltou" :value="formatInt(day.summary.short)" tone="error" :unit="shortUnit(day)" :hint="typicalLine(day, 'short')" />
          <OperatorMetric title="Sobrou" :value="formatInt(day.summary.over)" tone="warning" :unit="overUnit(day)" :hint="typicalLine(day, 'over')" />
          <OperatorMetric title="Na medida" :value="formatInt(day.summary.right)" tone="success" :unit="day.summary.right === 1 ? 'produto' : 'produtos'" :hint="typicalLine(day, 'right')" />
        </div>
        <!-- O gesto principal mora logo depois da resposta, em toda largura de tela
             (BI-11): no celular, na largura toda, ao alcance do polegar; na barra de
             cima ele espremia o título até cortá-lo. -->
        <NuxtButton
          v-if="day?.plan_day"
          size="xl"
          class="w-full justify-center md:w-auto md:self-start"
          icon="i-lucide-arrow-right-left"
          :label="carryLabel(day.plan_day)"
          :loading="carrying"
          data-bi-carry
          @click="carryToPlan()"
        />

        <OperatorReadingCard
          v-if="!dayError"
          title="Produto a produto"
          description="Fez × vendeu de cada produto do dia; abra a linha para ver os lotes e as vendas por hora"
          :csv="day ? csv : undefined"
          data-over-short-table
        >
          <NuxtTable
            v-model:expanded="expanded"
            :data="visible"
            :columns="columns"
            :loading="dayPending"
            :get-row-id="(row: BIOverShortRow) => row.sku"
            caption="Sobrou ou faltou, produto a produto"
          >
            <template #product-cell="{ row }">
              <div class="flex min-w-0 flex-col gap-1 whitespace-normal" data-over-short-row :data-verdict="row.original.verdict">
                <p class="text-sm font-medium text-highlighted">
                  {{ row.original.name }} <span class="font-mono text-xs font-normal text-muted">{{ row.original.sku }}</span>
                </p>
                <NuxtBadge class="self-start md:hidden" :color="verdictColor(row.original.verdict)" :label="verdictMeta(row.original.verdict).label" />
                <div class="flex flex-col gap-1 sm:hidden">
                  <OverShortBar :row="row.original" :scale="scale" />
                  <p class="text-xs tnum text-muted">
                    fez <b class="text-default">{{ formatQty(row.original.made) }}</b> · vendeu <b class="text-default">{{ formatQty(row.original.sold) }}</b> ·
                    {{ outcomeText(row.original) }}
                  </p>
                </div>
                <p class="text-xs tnum text-muted lg:hidden">
                  {{ row.original.soldout_at ? `acabou às ${row.original.soldout_at}` : "não acabou" }} · {{ historyText(row.original) }} · {{ versusTypicalText(row.original) }}
                </p>
              </div>
            </template>
            <template #verdict-cell="{ row }">
              <NuxtBadge :color="verdictColor(row.original.verdict)" :label="verdictMeta(row.original.verdict).label" data-over-short-verdict />
            </template>
            <template #made_sold-header>
              <span class="inline-flex items-center gap-3">
                Fez × vendeu
                <span class="inline-flex items-center gap-1 text-xs font-normal"><span class="h-3 w-0.5 bg-inverted" aria-hidden="true" />típico</span>
              </span>
            </template>
            <template #made_sold-cell="{ row }">
              <div class="flex min-w-48 flex-col gap-1">
                <OverShortBar :row="row.original" :scale="scale" />
                <p class="text-xs tnum text-muted">
                  fez <b class="text-default">{{ formatQty(row.original.made) }}</b> · vendeu <b class="text-default">{{ formatQty(row.original.sold) }}</b> ·
                  <span class="font-medium" :class="VERDICT_TEXT[verdictColor(row.original.verdict)]">{{ outcomeText(row.original) }}</span>
                </p>
              </div>
            </template>
            <template #soldout-cell="{ row }">
              <span class="tnum" :class="row.original.verdict === 'short' ? 'font-medium text-error' : ''">{{ soldoutText(row.original) }}</span>
            </template>
            <template #history-cell="{ row }">
              <span class="tnum text-muted">{{ historyText(row.original) }}</span>
            </template>
            <template #typical-cell="{ row }">
              <span class="whitespace-normal text-xs text-muted">{{ versusTypicalText(row.original) }}</span>
            </template>
            <template #open-header>
              <span class="sr-only">Lotes e vendas</span>
            </template>
            <template #open-cell="{ row }">
              <NuxtButton
                color="neutral"
                variant="ghost"
                :active="row.getIsExpanded()"
                active-color="primary"
                :trailing-icon="row.getIsExpanded() ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                :aria-expanded="row.getIsExpanded()"
                :aria-label="`Ver lotes e vendas de ${row.original.name}`"
                data-over-short-toggle
                @click="row.toggleExpanded()"
              >
                <span class="max-md:sr-only">Ver lotes e vendas</span>
              </NuxtButton>
            </template>
            <template #expanded="{ row }">
              <OverShortDetail
                v-if="day"
                :row="row.original"
                :day="day.day"
                :compare="day.compare"
                :close-url="closeUrl"
                :orders-url="ordersUrl"
              />
            </template>
            <template #loading>
              <NuxtEmpty loading variant="naked" title="Carregando a leitura do dia" />
            </template>
            <template #empty>
              <NuxtEmpty
                v-if="rows.length"
                variant="naked"
                icon="i-lucide-filter-x"
                title="Nenhum produto neste recorte"
                description="Troque o veredito, a coleção ou a busca para ver os outros produtos."
              />
              <NuxtEmpty
                v-else
                variant="naked"
                icon="i-lucide-chef-hat"
                title="Nenhum lote fechado neste dia"
                description="A leitura começa quando a Produção fecha o primeiro lote."
              />
            </template>
          </NuxtTable>
          <template v-if="hidden.length" #footer>
            <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between" data-over-short-more>
              <p class="text-xs text-muted">{{ hiddenRowsSummary(hidden) }}</p>
              <NuxtButton
                color="neutral"
                variant="outline"
                icon="i-lucide-chevron-down"
                :label="showHiddenLabel(hidden.length)"
                class="self-start sm:self-auto"
                @click="showAll = true"
              />
            </div>
          </template>
        </OperatorReadingCard>
      </template>
      <ProductionLots v-else />
      <MoreBelow />
    </main>
  </div>
</template>
