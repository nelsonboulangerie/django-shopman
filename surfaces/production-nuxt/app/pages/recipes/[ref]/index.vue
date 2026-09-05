<script setup lang="ts">
// A receita (/recipes/[ref]) — a lente da versão selecionada (âncora e base,
// tabela g/%, métricas com faixa de referência, partes, mistura final, BOM), a
// linha do tempo das versões e as ações: nova versão (copia a selecionada em
// rascunho), editar rascunho, publicar (diálogo com o que muda contra a atual),
// comparar, associar SKU, arquivar. Ler é do gate do app; mexer pede `can_edit`.
import type { RecipeVersionProjection } from "~/types/recipeBook";
import { isStale } from "~/presentation/production";
import {
  KIND_OPTIONS,
  comparePath,
  formulaFromServed,
  statusBadgeVariant,
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
  createVersion,
  publish,
} = useRecipeEntry(entryRef);

useHead({ title: computed(() => `${entry.value?.name || "Receita"} · Produção`) });

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
  const parts = [entry.value.kind_label];
  parts.push(entry.value.output_sku ? entry.value.output_name || entry.value.output_sku : "Sem SKU");
  if (selected.value) parts.push(`Versão ${selected.value.number}`);
  return parts.join(" · ");
});
const stale = computed(() => isStale({ error: !!error.value, hasData: !!entry.value }));
const isCurrent = computed(() => !!selected.value && selected.value.number === entry.value?.current_version_number);

// ── Nova versão: copia a selecionada em rascunho e abre o editor ────────────
async function newVersion() {
  const base = selected.value;
  if (!base) return;
  const result = await createVersion({
    from_version: base.number,
    formula: formulaFromServed(base.formula),
    yield_quantity: base.yield_quantity,
    yield_unit: base.yield_unit,
    steps: [...base.steps],
    notes: base.notes,
    label: "",
  });
  if (result.ok && result.version) await navigateTo(`/recipes/${entryRef}/edit?v=${result.version.number}`);
}

function editDraft() {
  if (selected.value?.status === "draft") navigateTo(`/recipes/${entryRef}/edit?v=${selected.value.number}`);
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
const unmatched = computed(() => (selected.value ? unmatchedItems(selected.value.lens.items) : []));
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

// ── Associar SKU: edição inline; a validação do SKU é do backend ────────────
const skuEditing = ref(false);
const skuInput = ref("");
const skuError = ref("");
function startSku() {
  skuInput.value = entry.value?.output_sku ?? "";
  skuError.value = "";
  skuEditing.value = true;
}
async function saveSku() {
  const result = await patchEntry({ output_sku: skuInput.value.trim().toUpperCase() });
  if (result.ok) {
    skuEditing.value = false;
    skuError.value = "";
  } else if (result.field === "output_sku" || result.message) {
    skuError.value = result.message ?? "SKU inválido.";
  }
}

// ── Dados da receita (nome, tipo, notas) ────────────────────────────────────
const detailsOpen = ref(false);
const detailsName = ref("");
const detailsKind = ref("other");
const detailsNotes = ref("");
const detailsError = ref("");
function openDetails() {
  detailsName.value = entry.value?.name ?? "";
  detailsKind.value = entry.value?.kind ?? "other";
  detailsNotes.value = entry.value?.notes ?? "";
  detailsError.value = "";
  detailsOpen.value = true;
}
async function saveDetails() {
  const name = detailsName.value.trim();
  if (!name) {
    detailsError.value = "Dê um nome à receita.";
    return;
  }
  const result = await patchEntry({ name, kind: detailsKind.value, notes: detailsNotes.value });
  if (result.ok) detailsOpen.value = false;
  else detailsError.value = result.message ?? "";
}

// ── Arquivar / restaurar (destrutivo pede confirmação) ──────────────────────
const archiveOpen = ref(false);
async function confirmArchive() {
  if (!entry.value) return;
  const result = await patchEntry({ is_archived: !entry.value.is_archived });
  if (result.ok) {
    archiveOpen.value = false;
    useSonner.success(entry.value.is_archived ? "Receita restaurada." : "Receita arquivada.");
  }
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <RecipeHeader :title="entry?.name || 'Receita'" :subtitle="subtitle" back="/recipes" :pending="pending" @refresh="refresh()" />

    <section v-if="forbidden" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-lg border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Área da produção</p>
        <p class="text-sm text-muted-foreground">Esta receita pede uma permissão que este operador não tem.</p>
        <NuxtLink to="/" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Voltar para a produção</NuxtLink>
      </div>
    </section>

    <section v-else-if="notFound" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-lg border border-dashed p-10">
        <Icon name="lucide:book-x" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Receita não encontrada</p>
        <p class="text-sm text-muted-foreground">Não existe receita com a ref <span class="font-mono">{{ entryRef }}</span>.</p>
        <NuxtLink to="/recipes" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Voltar ao inventário</NuxtLink>
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !entry" class="text-sm text-muted-foreground">Carregando…</p>

      <div
        v-else-if="error && !entry"
        class="grid place-items-center gap-2 rounded-lg border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível carregar a receita.</p>
        <button
          type="button"
          class="mt-1 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" /> Tentar de novo
        </button>
      </div>

      <template v-else-if="entry">
        <div
          v-if="stale"
          role="status"
          aria-live="polite"
          class="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-amber-700 dark:text-amber-300"
        >
          <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
          <span>Sem atualizar. Mostrando a última leitura.</span>
        </div>

        <!-- ── Cabeçalho da receita: tipo, SKU, ficha, arquivada ─────────── -->
        <div class="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-card p-3 text-sm">
          <UiBadge variant="outline" class="px-1.5 py-0 text-xs">{{ entry.kind_label }}</UiBadge>
          <UiBadge v-if="entry.is_archived" variant="outline" class="px-1.5 py-0 text-xs">Arquivada</UiBadge>

          <div class="flex min-w-0 items-center gap-1.5">
            <Icon name="lucide:tag" class="size-4 shrink-0 text-muted-foreground" />
            <template v-if="!skuEditing">
              <span v-if="entry.output_sku" class="truncate">
                {{ entry.output_name || entry.output_sku }}
                <span class="ml-1 font-mono text-xs text-muted-foreground">{{ entry.output_sku }}</span>
              </span>
              <span v-else class="text-amber-700 dark:text-amber-300">Sem SKU</span>
              <button
                v-if="canEdit && !entry.is_archived"
                type="button"
                class="ml-1 text-xs text-primary underline-offset-2 hover:underline"
                @click="startSku"
              >
                {{ entry.output_sku ? "Trocar" : "Associar SKU" }}
              </button>
            </template>
            <form v-else class="flex flex-wrap items-center gap-1.5" @submit.prevent="saveSku">
              <input
                v-model="skuInput"
                type="text"
                autofocus
                placeholder="SKU do produto"
                class="h-9 w-40 rounded-md border bg-background px-2 font-mono text-sm uppercase text-foreground"
                :aria-invalid="skuError ? 'true' : undefined"
                aria-label="SKU do produto"
              />
              <button
                type="submit"
                class="h-9 rounded-md border border-transparent bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
                :disabled="busy"
              >
                Salvar
              </button>
              <button
                type="button"
                class="h-9 rounded-md border px-3 text-sm font-medium transition hover:bg-accent"
                @click="skuEditing = false"
              >
                Cancelar
              </button>
              <span v-if="skuError" class="basis-full text-xs text-destructive">{{ skuError }}</span>
            </form>
          </div>

          <span v-if="entry.ficha_ref" class="text-muted-foreground">
            Ficha técnica <span class="font-mono text-xs">{{ entry.ficha_ref }}</span>
          </span>

          <div class="ml-auto flex flex-wrap items-center gap-1.5">
            <button
              v-if="canEdit"
              type="button"
              class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
              @click="openDetails"
            >
              <Icon name="lucide:pencil" class="size-4" /> Dados
            </button>
            <button
              v-if="canEdit"
              type="button"
              class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
              @click="archiveOpen = true"
            >
              <Icon :name="entry.is_archived ? 'lucide:archive-restore' : 'lucide:archive'" class="size-4" />
              {{ entry.is_archived ? "Restaurar" : "Arquivar" }}
            </button>
          </div>
        </div>

        <p v-if="entry.notes" class="mb-4 max-w-3xl whitespace-pre-line text-sm text-muted-foreground">{{ entry.notes }}</p>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
          <!-- ── A lente da versão selecionada ───────────────────────────── -->
          <div class="min-w-0">
            <div
              v-if="!selected"
              class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
            >
              <Icon name="lucide:scale" class="size-8" />
              <p class="text-base font-medium">Esta receita ainda não tem versão.</p>
            </div>
            <template v-else>
              <div class="mb-3 flex flex-wrap items-center gap-2">
                <h2 class="text-base font-bold">Versão {{ selected.number }}</h2>
                <UiBadge :variant="statusBadgeVariant(selected.status)" class="px-1.5 py-0 text-xs">{{ selected.status_label }}</UiBadge>
                <UiBadge v-if="isCurrent" variant="outline" class="px-1.5 py-0 text-xs">Atual</UiBadge>
                <span v-if="selected.label" class="text-sm text-muted-foreground">{{ selected.label }}</span>
                <span v-if="selected.yield_display" class="text-sm tabular-nums text-muted-foreground">
                  Rende {{ selected.yield_display }}
                </span>

                <div v-if="canEdit && !entry.is_archived" class="ml-auto flex flex-wrap items-center gap-1.5">
                  <button
                    v-if="selected.status === 'draft'"
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
                    @click="editDraft"
                  >
                    <Icon name="lucide:pencil-line" class="size-4" /> Editar rascunho
                  </button>
                  <button
                    v-if="selected.status === 'draft'"
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
                    @click="openPublish"
                  >
                    <Icon name="lucide:check" class="size-4" /> Publicar
                  </button>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
                    :disabled="busy"
                    @click="newVersion"
                  >
                    <Icon name="lucide:copy-plus" class="size-4" /> Nova versão
                  </button>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
                    @click="compareWith"
                  >
                    <Icon name="lucide:git-compare" class="size-4" /> Comparar com…
                  </button>
                </div>
                <button
                  v-else
                  type="button"
                  class="ml-auto inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
                  @click="compareWith"
                >
                  <Icon name="lucide:git-compare" class="size-4" /> Comparar com…
                </button>
              </div>

              <FormulaLens :lens="selected.lens" />

              <div v-if="selected.steps.length" class="mt-4 rounded-lg border bg-card p-4">
                <p class="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">Passos</p>
                <ol class="list-decimal space-y-1 pl-5 text-sm">
                  <li v-for="(step, index) in selected.steps" :key="index">{{ step }}</li>
                </ol>
              </div>
              <p v-if="selected.notes" class="mt-3 whitespace-pre-line text-sm text-muted-foreground">{{ selected.notes }}</p>
            </template>
          </div>

          <!-- ── Linha do tempo das versões ──────────────────────────────── -->
          <aside class="min-w-0">
            <p class="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Versões</p>
            <ol v-if="versions.length" class="grid gap-1.5">
              <li v-for="version in versions" :key="version.id">
                <button
                  type="button"
                  class="grid w-full gap-0.5 rounded-lg border p-2.5 text-left text-sm transition"
                  :class="
                    selected?.number === version.number
                      ? 'border-primary/50 bg-primary/5'
                      : 'bg-card hover:bg-accent/40'
                  "
                  :aria-pressed="selected?.number === version.number"
                  @click="selectVersion(version)"
                >
                  <span class="flex items-center gap-2">
                    <b class="tabular-nums">Versão {{ version.number }}</b>
                    <UiBadge :variant="statusBadgeVariant(version.status)" class="px-1.5 py-0 text-xs">{{ version.status_label }}</UiBadge>
                    <UiBadge v-if="version.number === entry.current_version_number" variant="outline" class="px-1.5 py-0 text-xs">Atual</UiBadge>
                  </span>
                  <span v-if="version.label" class="truncate text-muted-foreground">{{ version.label }}</span>
                  <span class="text-xs text-muted-foreground">
                    {{ version.source_label }}
                    <template v-if="version.published_at_display"> · publicada {{ version.published_at_display }}</template>
                    <template v-else-if="version.created_at_display"> · criada {{ version.created_at_display }}</template>
                    <template v-if="version.created_by"> · {{ version.created_by }}</template>
                  </span>
                </button>
              </li>
            </ol>
            <p v-else class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">Nenhuma versão ainda.</p>
          </aside>
        </div>
      </template>
    </section>

    <!-- ── Publicar: confirmação com o que muda ──────────────────────────── -->
    <UiDialog :open="publishOpen" @update:open="(v) => (publishOpen = v)">
      <UiDialogContent class="sm:max-w-lg">
        <UiDialogHeader>
          <UiDialogTitle>Publicar a versão {{ selected?.number }}</UiDialogTitle>
          <UiDialogDescription>
            <template v-if="currentVersion && currentVersion.number !== selected?.number">
              A versão {{ currentVersion.number }} passa a substituída e a ficha de execução
              <span class="font-mono">{{ entry?.ficha_ref || entryRef }}</span> é reescrita com esta fórmula.
            </template>
            <template v-else>
              Esta é a primeira versão publicada: a ficha de execução
              <span class="font-mono">{{ entry?.ficha_ref || entryRef }}</span> nasce dela.
            </template>
          </UiDialogDescription>
        </UiDialogHeader>

        <div v-if="publishBlocked" class="grid gap-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <p v-if="!entry?.output_sku" class="text-amber-700 dark:text-amber-300">Associe um SKU antes de publicar.</p>
          <p v-if="unmatched.length" class="text-amber-700 dark:text-amber-300">
            {{ unmatched.length === 1 ? "1 ingrediente ainda sem insumo" : `${unmatched.length} ingredientes ainda sem insumo` }}:
            {{ unmatched.map((item) => item.name).join(", ") }}. Case todos no editor.
          </p>
        </div>

        <template v-if="publishCompare.ready.value">
          <p v-if="publishCompare.pending.value" class="text-sm text-muted-foreground">Comparando…</p>
          <p v-else-if="publishCompare.error.value" class="text-sm text-muted-foreground">Não foi possível comparar com a versão atual.</p>
          <p v-else-if="!changedRows.length && !changedMetrics.length" class="text-sm text-muted-foreground">
            Nenhuma diferença de ingrediente ou métrica contra a versão atual.
          </p>
          <div v-else class="max-h-64 overflow-auto rounded-md border text-sm">
            <table class="w-full">
              <tbody class="divide-y">
                <tr v-for="row in changedRows" :key="`row-${row.sku || row.name}`">
                  <td class="px-3 py-1.5">{{ row.name || row.sku }}</td>
                  <td class="px-3 py-1.5 text-right tabular-nums text-muted-foreground">{{ row.a_display }}</td>
                  <td class="px-3 py-1.5 text-right tabular-nums">{{ row.b_display }}</td>
                  <td class="px-3 py-1.5 text-right tabular-nums" :class="toneClass(row.tone)">{{ row.delta_display }}</td>
                </tr>
                <tr v-for="metric in changedMetrics" :key="`metric-${metric.label}`" class="bg-muted/30">
                  <td class="px-3 py-1.5 font-medium">{{ metric.label }}</td>
                  <td class="px-3 py-1.5 text-right tabular-nums text-muted-foreground">{{ metric.a_display }}</td>
                  <td class="px-3 py-1.5 text-right tabular-nums">{{ metric.b_display }}</td>
                  <td class="px-3 py-1.5 text-right tabular-nums" :class="toneClass(metric.tone)">{{ metric.delta_display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="publishOpen = false">
            Cancelar
          </button>
          <button
            type="button"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            :disabled="publishBlocked || busy"
            @click="confirmPublish"
          >
            Publicar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- ── Dados da receita ──────────────────────────────────────────────── -->
    <UiDialog :open="detailsOpen" @update:open="(v) => (detailsOpen = v)">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Dados da receita</UiDialogTitle>
          <UiDialogDescription>Nome, tipo (define as referências) e notas gerais.</UiDialogDescription>
        </UiDialogHeader>
        <div class="grid gap-3">
          <label class="grid gap-1 text-xs font-medium text-muted-foreground">
            Nome
            <input v-model="detailsName" type="text" class="h-9 rounded-md border bg-background px-2 text-sm text-foreground" />
          </label>
          <label class="grid gap-1 text-xs font-medium text-muted-foreground">
            Tipo
            <select v-model="detailsKind" class="h-9 rounded-md border bg-background px-2 text-sm text-foreground">
              <option v-for="option in KIND_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="grid gap-1 text-xs font-medium text-muted-foreground">
            Notas
            <UiTextarea v-model="detailsNotes" :rows="3" />
          </label>
          <p v-if="detailsError" class="text-sm text-destructive">{{ detailsError }}</p>
        </div>
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="detailsOpen = false">
            Cancelar
          </button>
          <button
            type="button"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            :disabled="busy"
            @click="saveDetails"
          >
            Salvar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- ── Arquivar / restaurar ──────────────────────────────────────────── -->
    <UiDialog :open="archiveOpen" @update:open="(v) => (archiveOpen = v)">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>{{ entry?.is_archived ? "Restaurar a receita" : "Arquivar a receita" }}</UiDialogTitle>
          <UiDialogDescription>
            <template v-if="entry?.is_archived">Ela volta ao inventário e pode receber versões de novo.</template>
            <template v-else>
              Ela sai do inventário (fica em "Arquivadas") e não recebe novas versões. A ficha de execução publicada
              não muda.
            </template>
          </UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="archiveOpen = false">
            Cancelar
          </button>
          <button
            type="button"
            class="rounded-md border border-transparent px-3 py-2 text-sm font-semibold transition disabled:opacity-50"
            :class="
              entry?.is_archived
                ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                : 'bg-warning text-warning-foreground hover:bg-warning/90'
            "
            :disabled="busy"
            @click="confirmArchive"
          >
            {{ entry?.is_archived ? "Restaurar" : "Arquivar" }}
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
