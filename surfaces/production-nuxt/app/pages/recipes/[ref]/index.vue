<script setup lang="ts">
import { alertActions } from "../../../../../operator-kit/app/utils/alertActions";
// A receita (/recipes/[ref]) — a lente da versão selecionada (âncora e base,
// tabela g/%, métricas com faixa de referência, mistura final e BOM), a
// linha do tempo das versões e as ações: editar (abre ou prepara o rascunho),
// publicar (diálogo com o que muda contra a atual), comparar, duplicar e arquivar.
// Ler é do gate do app; mexer pede `can_edit`.
// A estrela (favorita) é preferência do operador: basta ler. A nota da versão
// (0 a 5 por critério do Admin) também; as referências (livros, vídeos, artigos)
// são da receita e pedem `can_edit` para mudar.
import type { RecipeVersionProjection } from "~/types/recipeBook";
import { isStale } from "~/presentation/production";
import {
  comparePath,
  favoriteActionHint,
  needsReview,
  provenanceIcon,
  reviewSignature,
  statusBadgeColor,
  toneClass,
  unmatchedItems,
  versionRefLabel,
} from "~/presentation/recipeBook";

const route = useRoute();
const router = useRouter();
const entryRef = String(route.params.ref ?? "");

const {
  entry,
  canEdit,
  versions,
  currentVersion,
  versionByNumber,
  notFound,
  forbidden,
  pending,
  error,
  refresh,
  busy,
  patchEntry,
  duplicate,
  publish,
  saveReferences,
  rateVersion,
  confirmVersion,
  toggleFavorite,
  favoriteBusy,
} = useRecipeEntry(entryRef);

// Conferência (WP-RECEITAS-DA-CASA F1): só a versão em uso se confere.
async function confirmSelected() {
  if (!selected.value) return;
  const result = await confirmVersion(selected.value.number);
  if (result.ok) useSonner.success(`Versão ${selected.value.number} conferida.`);
}

useHead({ title: computed(() => entry.value?.name || "Receita") });

// ── Versão selecionada (query `v`; padrão = a atual, senão a mais nova) ─────
const selectedNumber = ref<number | null>(Number(route.query.v) || null);
watch(
  () => route.query.v,
  (value) => {
    selectedNumber.value = Number(value) || null;
  },
);
const selected = computed<RecipeVersionProjection | null>(
  () => versionByNumber(selectedNumber.value) ?? currentVersion.value ?? versions.value[0] ?? null,
);
function selectVersion(version: RecipeVersionProjection) {
  selectedNumber.value = version.number;
  router.replace({ query: { ...route.query, v: String(version.number) } });
}

const subtitle = computed(() => {
  if (!entry.value) return "";
  const details = [entry.value.kind_label];
  details.push(entry.value.output_sku ? entry.value.output_name || entry.value.output_sku : "Sem SKU");
  if (selected.value) details.push(`Versão ${selected.value.number}`);
  return details.join(" · ");
});
const stale = computed(() => isStale({ error: !!error.value, hasData: !!entry.value }));
const isCurrent = computed(() => !!selected.value && selected.value.number === entry.value?.current_version_number);
const editAction = computed(() =>
  canEdit.value && entry.value?.is_active
    ? {
        label: "Editar",
        icon: "i-lucide-pencil-line",
        to: `/recipes/${entryRef}/edit`,
      }
    : undefined,
);
const executionSummary = computed(() => {
  const execution = entry.value?.execution;
  if (!execution?.exists) return "";
  return [
    execution.max_started_minutes ? `${execution.max_started_minutes} min até atraso` : "tempo padrão da loja",
    execution.capacity_per_day ? `${execution.capacity_per_day} por dia` : "capacidade sem teto próprio",
    execution.shelf_life_days == null
      ? "validade não declarada"
      : `${execution.shelf_life_days} ${execution.shelf_life_days === 1 ? "dia" : "dias"} de validade`,
  ].join(" · ");
});

function editRecipe() {
  navigateTo(`/recipes/${entryRef}/edit`);
}

function compareWith() {
  if (selected.value) navigateTo(comparePath(entryRef, selected.value.number));
}

// ── Publicar: o diálogo mostra o que muda contra a versão atual ─────────────
const publishOpen = ref(false);
const compareA = ref("");
const compareB = ref("");
const publishCompare = useRecipeCompare(compareA, compareB);
const changedRows = computed(() => publishCompare.rows.value.filter((row) => row.delta_display));
const changedMetrics = computed(() => publishCompare.metrics.value.filter((metric) => metric.delta_display));
const unmatched = computed(() => (selected.value ? unmatchedItems(selected.value.lens.ingredients) : []));
const publishBlocked = computed(() => !entry.value?.output_sku || unmatched.value.length > 0);

function openPublish() {
  if (!selected.value) return;
  if (currentVersion.value && currentVersion.value.number !== selected.value.number) {
    compareA.value = versionRefLabel(entryRef, currentVersion.value.number);
    compareB.value = versionRefLabel(entryRef, selected.value.number);
  } else {
    compareA.value = "";
    compareB.value = "";
  }
  publishOpen.value = true;
}

async function confirmPublish() {
  if (!selected.value || publishBlocked.value) return;
  const result = await publish(selected.value.number);
  if (result.ok) {
    publishOpen.value = false;
    useSonner.success(`Versão ${selected.value.number} publicada.`);
  }
}

// ── Cadastro turbo: copiar a receita inteira ───────────────────────────────
const duplicateOpen = ref(false);
const duplicateKey = ref("");

function newMutationKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function openDuplicate() {
  duplicateKey.value = newMutationKey();
  duplicateOpen.value = true;
}

async function saveDuplicate(payload: Parameters<typeof duplicate>[0]) {
  const result = await duplicate(payload, duplicateKey.value);
  if (!result.ok && !result.uncertain) duplicateKey.value = newMutationKey();
  if (result.ok && result.entry) {
    duplicateOpen.value = false;
    useSonner.success("Cópia criada como rascunho.");
    await navigateTo(`/recipes/${result.entry.ref}/edit?v=1`);
  }
}

// ── Arquivar / desarquivar (destrutivo pede confirmação) ────────────────────
const archiveOpen = ref(false);
async function confirmArchive() {
  if (!entry.value) return;
  const result = await patchEntry({
    is_active: !entry.value.is_active,
    expectedRevision: entry.value.revision,
  });
  if (result.ok) {
    archiveOpen.value = false;
    useSonner.success(entry.value.is_active ? "Receita desarquivada." : "Receita arquivada.");
  }
}
const archiveDescription = computed(() =>
  entry.value && !entry.value.is_active
    ? "Ela volta à lista de receitas e pode receber versões de novo."
    : 'Ela sai da lista principal (fica em "Arquivadas") e não recebe novas versões. A versão em uso na produção não muda.',
);
const publishDescription = computed(() => {
  return currentVersion.value && currentVersion.value.number !== selected.value?.number
    ? `A versão ${currentVersion.value.number} será substituída. Os ingredientes, o rendimento e o modo de preparo desta versão passam a valer na produção.`
    : "Os ingredientes, o rendimento e o modo de preparo desta versão passam a valer na produção.";
});
// Os dois motivos que seguram a publicação, cada um com a ação que o resolve.
function skuFromPublish() {
  publishOpen.value = false;
  editRecipe();
}
function editorFromPublish() {
  publishOpen.value = false;
  editRecipe();
}

const secondaryActions = computed(() => [
  {
    label: "Duplicar receita",
    icon: "i-lucide-copy-plus",
    disabled: !versions.value.length,
    onSelect: openDuplicate,
  },
  {
    label: entry.value?.is_active ? "Arquivar receita" : "Desarquivar receita",
    icon: entry.value?.is_active ? "i-lucide-archive" : "i-lucide-archive-restore",
    onSelect: () => {
      archiveOpen.value = true;
    },
  },
]);

// O selo do estado da versão: rascunho avisa, publicada é ok, o resto é neutro.
const PUBLISH_NUM = { class: { th: "text-right", td: "text-right tabular-nums" } };
const PUBLISH_DIFF_COLUMNS = [
  { id: "name", header: "O que muda", enableHiding: false },
  { id: "a", header: "Atual", meta: PUBLISH_NUM },
  { accessorKey: "b_display", header: "Nova", meta: PUBLISH_NUM },
  { id: "delta", header: "Diferença", meta: PUBLISH_NUM },
];
const publishDiff = computed(() => [
  ...changedRows.value.map((row) => ({
    key: `row-${row.sku || row.name}`,
    name: row.name || row.sku,
    metric: false,
    a_display: row.a_display,
    b_display: row.b_display,
    delta_display: row.delta_display,
    tone: row.tone,
  })),
  ...changedMetrics.value.map((metric) => ({
    key: `metric-${metric.label}`,
    name: metric.label,
    metric: true,
    a_display: metric.a_display,
    b_display: metric.b_display,
    delta_display: metric.delta_display,
    tone: metric.tone,
  })),
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <RecipeHeader
      :title="entry?.name || 'Receita'"
      :subtitle="subtitle"
      back="/recipes"
      :pending="pending"
      :primary="editAction"
      @refresh="refresh()"
    >
      <!-- Anterior e próxima dentro da lista de onde a pessoa veio (com o recorte dela).
           Aberta por link, sem trilha: o par não aparece. -->
      <template #status>
        <OperatorRecordNav
          trail="production-recipes"
          :current="entryRef"
          :to="(id) => `/recipes/${id}`"
          previous-label="Receita anterior"
          next-label="Próxima receita"
        />
      </template>
    </RecipeHeader>

    <section v-if="forbidden" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Área da produção</p>
        <p class="text-sm text-muted-foreground">Esta receita pede uma permissão que este operador não tem.</p>
        <NuxtLink to="/" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Voltar para a produção</NuxtLink>
      </div>
    </section>

    <section v-else-if="notFound" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:book-x" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Receita não encontrada</p>
        <p class="text-sm text-muted-foreground">Não existe receita com a ref <span class="font-mono">{{ entryRef }}</span>.</p>
        <NuxtLink to="/recipes" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Voltar às receitas</NuxtLink>
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !entry" class="text-sm text-muted-foreground">Carregando…</p>

      <div
        v-else-if="error && !entry"
        class="grid place-items-center gap-2 rounded-md border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível carregar a receita.</p>
        <NuxtButton
          class="mt-1"
          color="neutral"
          variant="outline"
          icon="i-lucide-refresh-cw"
          label="Tentar de novo"
          @click="refresh()"
        />
      </div>

      <template v-else-if="entry">
        <NuxtAlert
          v-if="stale"
          class="mb-3"
          color="warning"
          variant="subtle"
          icon="i-lucide-wifi-off"
          title="Sem atualizar. Mostrando a última leitura."
          :actions="alertActions('warning', [{ label: 'Tentar de novo', onClick: () => refresh() }])"
          role="status"
          aria-live="polite"
        />

        <!-- ── Cabeçalho da ficha técnica ───────────────────────────────── -->
        <NuxtCard class="mb-4" :ui="{ body: 'flex flex-wrap items-center gap-x-4 gap-y-2 p-3 text-sm sm:p-3' }">
          <span class="font-semibold">Ficha técnica</span>
          <NuxtBadge color="neutral" :label="entry.kind_label" />
          <NuxtBadge v-if="!entry.is_active" color="neutral" label="Arquivada" />
          <NuxtBadge v-if="currentVersion && entry.execution?.exists" color="success" label="Em uso na produção" />

          <div class="flex min-w-0 items-center gap-1.5">
            <Icon name="lucide:tag" class="size-4 shrink-0 text-muted-foreground" />
            <span v-if="entry.output_sku" class="truncate">
              {{ entry.output_name || entry.output_sku }}
              <span class="ml-1 font-mono text-xs text-muted-foreground">{{ entry.output_sku }}</span>
            </span>
            <span v-else class="text-warning">Sem produto associado</span>
          </div>

          <div class="ml-auto flex flex-wrap items-center gap-1.5">
            <NuxtButton
              color="neutral"
              variant="outline"
              :active="entry.is_favorite"
              active-color="primary"
              active-variant="outline"
              label="Favorita"
              :aria-pressed="entry.is_favorite"
              :title="favoriteActionHint(entry.is_favorite)"
              :disabled="favoriteBusy"
              @click="toggleFavorite(!entry.is_favorite)"
            >
              <template #leading>
                <Icon name="lucide:star" class="size-4" :class="entry.is_favorite ? 'fill-current' : ''" />
              </template>
            </NuxtButton>
            <OperatorMoreMenu v-if="canEdit" :items="secondaryActions" label="Mais ações" />
          </div>
        </NuxtCard>

        <p v-if="entry.notes" class="mb-4 max-w-3xl whitespace-pre-line text-sm text-muted-foreground">{{ entry.notes }}</p>

        <NuxtCard v-if="entry.execution?.exists" class="mb-4">
          <h2 class="text-sm font-semibold">Configuração da produção</h2>
          <p class="mt-1 text-sm text-muted-foreground">{{ executionSummary }}</p>
        </NuxtCard>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
          <!-- ── A lente da versão selecionada ───────────────────────────── -->
          <div class="min-w-0">
            <div
              v-if="!selected"
              class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground"
            >
              <Icon name="lucide:scale" class="size-8" />
              <p class="text-base font-medium">Esta receita ainda não tem versão.</p>
            </div>
            <template v-else>
              <div class="mb-3 flex flex-wrap items-center gap-2">
                <h2 class="text-lg font-semibold">Versão {{ selected.number }}</h2>
                <NuxtBadge :color="statusBadgeColor(selected.status)" :label="selected.status_label" />
                <NuxtBadge v-if="isCurrent" color="neutral" label="Atual" />
                <span v-if="selected.label" class="text-sm text-muted-foreground">{{ selected.label }}</span>
                <span v-if="selected.yield_display" class="text-sm tabular-nums text-muted-foreground">
                  Rende {{ selected.yield_display }}
                </span>

                <div v-if="canEdit && entry.is_active" class="ml-auto flex flex-wrap items-center gap-1.5">
                  <NuxtButton
                    v-if="selected.status === 'draft'"
                    icon="i-lucide-check"
                    label="Publicar"
                    @click="openPublish"
                  />
                  <NuxtButton
                    color="neutral"
                    variant="outline"
                    icon="i-lucide-git-compare"
                    label="Comparar com…"
                    @click="compareWith"
                  />
                </div>
                <NuxtButton
                  v-else
                  class="ml-auto"
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-git-compare"
                  label="Comparar com…"
                  @click="compareWith"
                />
              </div>

              <div class="mb-3 flex flex-wrap items-center gap-2 text-sm" data-version-review>
                <NuxtIcon :name="provenanceIcon(selected.provenance_kind)" class="size-4 shrink-0 text-muted-foreground" />
                <span class="text-muted-foreground">
                  <b class="text-foreground">{{ selected.provenance_label }}.</b> {{ selected.provenance_detail }}
                </span>
                <NuxtBadge
                  v-if="needsReview(selected.review_status)"
                  :color="selected.review_status === 'changed' ? 'warning' : 'neutral'"
                  :label="selected.review_label"
                />
                <span v-else-if="selected.review_by_name" class="text-muted-foreground">
                  {{ reviewSignature(selected.review_by_name, selected.review_at_display) }}
                </span>
              </div>

              <h3 class="mb-2 text-sm font-semibold">Ingredientes</h3>
              <FormulaLens :lens="selected.lens" />

              <NuxtCard class="mt-4">
                <h3 class="mb-2 text-sm font-semibold">Modo de preparo</h3>
                <ol v-if="selected.steps.length" class="list-decimal space-y-1 pl-5 text-sm">
                  <li v-for="(step, index) in selected.steps" :key="index">
                    <span class="font-medium">{{ step.name }}</span>
                    <span v-if="step.target_display" class="text-muted-foreground"> · {{ step.target_display }}</span>
                    <span v-if="step.temperature_display" class="text-muted-foreground"> · {{ step.temperature_display }}</span>
                    <p v-if="step.instructions" class="whitespace-pre-line text-muted-foreground">{{ step.instructions }}</p>
                    <p v-if="step.note" class="whitespace-pre-line text-xs text-muted-foreground">{{ step.note }}</p>
                  </li>
                </ol>
                <p v-else class="text-sm text-muted-foreground">Modo de preparo ainda não informado.</p>
              </NuxtCard>
              <p v-if="selected.notes" class="mt-3 whitespace-pre-line text-sm text-muted-foreground">{{ selected.notes }}</p>
              <NuxtAlert
                v-if="canEdit && isCurrent && entry.is_active && needsReview(selected.review_status)"
                class="mt-4"
                color="warning"
                variant="subtle"
                icon="i-lucide-clipboard-check"
                title="Conferência pendente"
                description="Confira ingredientes, rendimento e modo de preparo. Ao confirmar, você registra que esta versão representa a receita da casa."
                :actions="alertActions('warning', [{ label: 'Marcar como conferida', icon: 'i-lucide-check', onClick: confirmSelected }])"
              />
            </template>
          </div>

          <!-- ── Linha do tempo das versões ──────────────────────────────── -->
          <aside class="min-w-0">
            <p class="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Versões</p>
            <ol v-if="versions.length" class="grid gap-1.5">
              <li v-for="version in versions" :key="version.id">
                <!-- A versão é uma linha inteira que se escolhe (três linhas de metadados). -->
                <NuxtButton
                  color="neutral"
                  variant="outline"
                  block
                  :active="selected?.number === version.number"
                  active-color="primary"
                  active-variant="outline"
                  :ui="{ base: 'grid h-auto justify-start gap-0.5 whitespace-normal p-2.5 text-left' }"
                  :aria-pressed="selected?.number === version.number"
                  @click="selectVersion(version)"
                >
                  <span class="flex items-center gap-2">
                    <b class="tabular-nums">Versão {{ version.number }}</b>
                    <NuxtBadge :color="statusBadgeColor(version.status)" :label="version.status_label" />
                    <NuxtBadge v-if="version.number === entry.current_version_number" color="neutral" label="Atual" />
                  </span>
                  <span v-if="version.label" class="truncate font-normal text-muted-foreground">{{ version.label }}</span>
                  <span class="text-xs font-normal text-muted-foreground">
                    {{ version.source_label }}
                    <template v-if="version.published_at_display"> · publicada {{ version.published_at_display }}</template>
                    <template v-else-if="version.created_at_display"> · criada {{ version.created_at_display }}</template>
                    <template v-if="version.created_by"> · {{ version.created_by }}</template>
                  </span>
                </NuxtButton>
              </li>
            </ol>
            <p v-else class="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">Nenhuma versão ainda.</p>

            <div class="mt-4 grid gap-3">
              <RecipeVersionRating
                :version="selected"
                :criteria="entry.rating_criteria"
                :ratings="entry.ratings"
                :busy="busy"
                :rate="rateVersion"
              />
              <RecipeExternalReferences
                :references="entry.external_references"
                :can-edit="canEdit"
                :busy="busy"
                :save="saveReferences"
              />
            </div>
          </aside>
        </div>
      </template>
    </section>

    <!-- ── Publicar: confirmação com o que muda ──────────────────────────── -->
    <NuxtModal
      v-model:open="publishOpen"
      :title="`Publicar a versão ${selected?.number ?? ''}`"
      :description="publishDescription"
      :ui="{ content: 'sm:max-w-lg' }"
    >
      <template #body>
        <div class="grid gap-3">
          <NuxtAlert
            v-if="!entry?.output_sku"
            color="warning"
            variant="subtle"
            icon="i-lucide-tag"
            title="Associe um SKU antes de publicar."
            :actions="alertActions('warning', [{ label: 'Associar SKU', onClick: skuFromPublish }])"
          />
          <NuxtAlert
            v-if="unmatched.length"
            color="warning"
            variant="subtle"
            icon="i-lucide-unlink"
            :title="unmatched.length === 1 ? '1 ingrediente ainda sem insumo' : `${unmatched.length} ingredientes ainda sem insumo`"
            :description="`${unmatched.map((item) => item.name).join(', ')}. Associe cada um a um insumo no editor.`"
            :actions="alertActions('warning', [{ label: 'Abrir o editor', onClick: editorFromPublish }])"
          />

          <template v-if="publishCompare.ready.value">
            <p v-if="publishCompare.pending.value" class="text-sm text-muted-foreground">Comparando…</p>
            <p v-else-if="publishCompare.error.value" class="text-sm text-muted-foreground">Não foi possível comparar com a versão atual.</p>
            <p v-else-if="!changedRows.length && !changedMetrics.length" class="text-sm text-muted-foreground">
              Nenhuma diferença de ingrediente ou métrica contra a versão atual.
            </p>
            <!-- O que muda contra a versão atual: ingredientes e, por último, métricas. -->
            <div v-else class="max-h-64 overflow-auto">
              <OperatorTable
                :data="publishDiff"
                :columns="PUBLISH_DIFF_COLUMNS"
                :row-key="(row) => row.key"
                caption="Diferenças contra a versão atual"
              >
                <template #name-cell="{ row }">
                  <span :class="row.original.metric ? 'font-medium' : ''">{{ row.original.name }}</span>
                </template>
                <template #a-cell="{ row }">
                  <span class="text-muted-foreground">{{ row.original.a_display }}</span>
                </template>
                <template #delta-cell="{ row }">
                  <span :class="toneClass(row.original.tone)">{{ row.original.delta_display }}</span>
                </template>
              </OperatorTable>
            </div>
          </template>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="publishOpen = false" />
          <NuxtButton label="Publicar" :disabled="publishBlocked || busy" @click="confirmPublish" />
        </div>
      </template>
    </NuxtModal>

    <!-- ── Arquivar / desarquivar ───────────────────────────────────────── -->
    <NuxtModal
      v-model:open="archiveOpen"
      :title="entry && !entry.is_active ? 'Desarquivar a receita' : 'Arquivar a receita'"
      :description="archiveDescription"
      :ui="{ content: 'sm:max-w-sm' }"
    >
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="archiveOpen = false" />
          <NuxtButton
            :color="entry && !entry.is_active ? 'primary' : 'error'"
            :label="entry && !entry.is_active ? 'Desarquivar' : 'Arquivar'"
            :disabled="busy"
            @click="confirmArchive"
          />
        </div>
      </template>
    </NuxtModal>

    <RecipeDuplicatePanel
      v-model:open="duplicateOpen"
      :source="entry"
      :from-version="selected?.number"
      :busy="busy"
      @save="saveDuplicate"
    />

  </main>
</template>
