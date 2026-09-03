<script setup lang="ts">
// Nova receita (/recipes/new) — três portas na mesma tela: Anotação (colar texto),
// Foto (câmera/arquivo, redimensionada no navegador) e Manual (editor vazio). As
// duas primeiras leem por POST recipes/capture/ e mostram o rascunho lido —
// nome, língua, rendimento, ingredientes casados com candidatos, papel — para o
// padeiro conferir antes de "Continuar no editor", que cria a entry + versão em
// rascunho (POST recipes/) e navega para /recipes/<ref>/edit. Sem leitura
// automática no ambiente (503), a tela diz isso e aponta a porta manual.
import type { CaptureItemProjection, IngredientOptionProjection, VersionPayload } from "~/types/recipeBook";
import { CAPTURE_UNAVAILABLE_MESSAGE } from "~/composables/useRecipeCapture";
import {
  KIND_OPTIONS,
  ROLE_OPTIONS,
  YIELD_UNIT_OPTIONS,
  emptyFormula,
  formulaFromDraft,
} from "~/presentation/recipeBook";

useHead({ title: "Nova receita · Produção" });

type Door = "note" | "photo" | "manual";
const route = useRoute();
const door = ref<Door>(route.query.door === "manual" ? "manual" : route.query.door === "photo" ? "photo" : "note");
const doors: { value: Door; label: string; icon: string }[] = [
  { value: "note", label: "Anotação", icon: "lucide:notebook-pen" },
  { value: "photo", label: "Foto", icon: "lucide:camera" },
  { value: "manual", label: "Manual", icon: "lucide:pencil" },
];

const { canEdit, captureAvailable, pending: accessPending } = useRecipeBookAccess();
const { creating, createEntry } = useRecipeBook(ref(""), ref(""), ref(false));
const capture = useRecipeCapture();

// ── Anotação ────────────────────────────────────────────────────────────────
const noteText = ref("");
const languageHint = ref("");

async function readNote() {
  const draft = await capture.captureText(noteText.value.trim(), languageHint.value.trim());
  if (draft) seedDraft(draft.items, "note");
}

// ── Foto ────────────────────────────────────────────────────────────────────
const photoFile = ref<File | null>(null);
const photoPreview = ref("");

function onPhotoChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  if (photoPreview.value) URL.revokeObjectURL(photoPreview.value);
  photoFile.value = file;
  photoPreview.value = file ? URL.createObjectURL(file) : "";
}

async function readPhoto() {
  if (!photoFile.value) return;
  const draft = await capture.captureImage(photoFile.value, languageHint.value.trim());
  if (draft) seedDraft(draft.items, "photo");
}

onBeforeUnmount(() => {
  if (photoPreview.value) URL.revokeObjectURL(photoPreview.value);
});

// ── Rascunho lido (conferência antes do editor) ─────────────────────────────
// Cópia local editável: o padeiro troca o insumo entre os candidatos e o papel;
// o nome/rendimento também são dele. O `draft` do composable fica intacto: é a
// receita COMO FOI LIDA, e vira `origin` na versão.
const draftName = ref("");
const draftKind = ref("other");
const draftYieldQuantity = ref("");
const draftYieldUnit = ref("kg");
const draftItems = ref<CaptureItemProjection[]>([]);
const draftSource = ref<"note" | "photo">("note");

function seedDraft(items: CaptureItemProjection[], source: "note" | "photo") {
  const draft = capture.draft.value;
  draftName.value = draft?.name ?? "";
  draftKind.value = draft?.kind && KIND_OPTIONS.some((option) => option.value === draft.kind) ? draft.kind : "other";
  draftYieldQuantity.value = draft?.yield_quantity ?? "";
  draftYieldUnit.value = draft?.yield_unit || "kg";
  draftItems.value = items.map((item) => ({ ...item, candidates: [...(item.candidates ?? [])] }));
  draftSource.value = source;
}

function candidateFor(item: CaptureItemProjection): IngredientOptionProjection | null {
  return item.candidates.find((candidate) => candidate.sku === item.sku) ?? null;
}

function chooseCandidate(index: number, sku: string) {
  const item = draftItems.value[index];
  if (!item) return;
  const candidate = item.candidates.find((option) => option.sku === sku);
  draftItems.value = draftItems.value.map((row, i) =>
    i === index ? { ...row, sku, role: candidate?.role && row.role === "other" ? candidate.role : row.role } : row,
  );
}

function setRole(index: number, role: string) {
  draftItems.value = draftItems.value.map((row, i) => (i === index ? { ...row, role } : row));
}

const unmatchedCount = computed(() => draftItems.value.filter((item) => !item.sku).length);
const draftError = ref("");

async function continueToEditor() {
  const draft = capture.draft.value;
  if (!draft) return;
  const name = draftName.value.trim();
  if (!name) {
    draftError.value = "Dê um nome à receita.";
    return;
  }
  draftError.value = "";
  const formula = formulaFromDraft({ ...draft, items: draftItems.value });
  const version: VersionPayload = {
    formula,
    yield_quantity: draftYieldQuantity.value.trim() || "1",
    yield_unit: draftYieldUnit.value,
    steps: draft.steps ?? [],
    notes: "",
    label: draftSource.value === "photo" ? "Lida de foto" : "Lida de anotação",
    origin: {
      kind: draftSource.value,
      language: draft.language,
      text: draftSource.value === "note" ? noteText.value : "",
      yield_quantity: draft.yield_quantity,
      yield_unit: draft.yield_unit,
      items: draft.items.map((item) => ({
        name: item.name,
        original_text: item.original_text,
        quantity: item.quantity,
        unit: item.unit,
      })),
      steps: draft.steps ?? [],
    },
    source: {
      kind: draftSource.value,
      language: draft.language,
      ...(draftSource.value === "note" ? { text: noteText.value } : {}),
      ...(draftSource.value === "photo" && photoFile.value ? { image_name: photoFile.value.name } : {}),
    },
  };
  const result = await createEntry({ name, kind: draftKind.value, output_sku: "", notes: draft.notes ?? "", version });
  if (result.ok && result.entry) await navigateTo(`/recipes/${result.entry.ref}/edit`);
  else if (result.message) draftError.value = result.message;
}

// ── Manual ──────────────────────────────────────────────────────────────────
const manualName = ref("");
const manualKind = ref("bread");
const manualYieldQuantity = ref("1");
const manualYieldUnit = ref("kg");
const manualError = ref("");

async function startManual() {
  const name = manualName.value.trim();
  if (!name) {
    manualError.value = "Dê um nome à receita.";
    return;
  }
  manualError.value = "";
  const result = await createEntry({
    name,
    kind: manualKind.value,
    output_sku: "",
    notes: "",
    version: {
      formula: emptyFormula(manualKind.value === "bread" || manualKind.value === "viennoiserie" ? "flour" : "total"),
      yield_quantity: manualYieldQuantity.value.trim() || "1",
      yield_unit: manualYieldUnit.value,
      steps: [],
      source: { kind: "manual" },
    },
  });
  if (result.ok && result.entry) await navigateTo(`/recipes/${result.entry.ref}/edit`);
  else if (result.message) manualError.value = result.message;
}

const showUnavailable = computed(
  () => capture.unavailable.value || (!accessPending.value && !captureAvailable.value),
);
const hasDraft = computed(() => capture.state.value === "done" && !!capture.draft.value);
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <RecipeHeader title="Nova receita" back="/recipes" hide-refresh />

    <section v-if="!accessPending && !canEdit" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-lg border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Só leitura</p>
        <p class="text-sm text-muted-foreground">
          Criar receitas pede a permissão de gestão da produção. Peça a liberação a quem administra a loja.
        </p>
        <NuxtLink to="/recipes" class="mt-1 text-sm text-primary underline-offset-2 hover:underline"
          >Voltar ao inventário</NuxtLink
        >
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mx-auto grid max-w-4xl gap-4">
        <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="tablist" aria-label="Como entrar a receita">
          <button
            v-for="option in doors"
            :key="option.value"
            type="button"
            role="tab"
            class="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition"
            :class="
              door === option.value
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-selected="door === option.value"
            @click="door = option.value"
          >
            <Icon :name="option.icon" class="size-4" />
            {{ option.label }}
          </button>
        </div>

        <!-- ── Anotação / Foto: entrada ──────────────────────────────────── -->
        <template v-if="door !== 'manual'">
          <div
            v-if="showUnavailable"
            class="flex flex-wrap items-center gap-3 rounded-lg border border-dashed p-4 text-sm text-muted-foreground"
          >
            <Icon name="lucide:sparkles" class="size-5 shrink-0" />
            <span class="flex-1">{{ CAPTURE_UNAVAILABLE_MESSAGE }}</span>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
              @click="door = 'manual'"
            >
              <Icon name="lucide:pencil" class="size-4" /> Preencher à mão
            </button>
          </div>

          <template v-else-if="!hasDraft">
            <div v-if="door === 'note'" class="grid gap-2 rounded-lg border bg-card p-4">
              <label class="grid gap-1 text-sm font-medium">
                Cole ou digite a receita, em qualquer língua
                <UiTextarea
                  v-model="noteText"
                  :rows="10"
                  placeholder="Ex.: Pain de campagne — 1 kg farine T65, 700 g eau, 20 g sel, 200 g levain…"
                />
              </label>
              <div class="flex flex-wrap items-end gap-3">
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Língua (opcional)
                  <input
                    v-model="languageHint"
                    type="text"
                    placeholder="pt, fr, en, ja…"
                    class="h-9 w-32 rounded-md border bg-background px-2 text-sm text-foreground"
                  />
                </label>
                <button
                  type="button"
                  class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
                  :disabled="!noteText.trim() || capture.reading.value"
                  @click="readNote"
                >
                  <Icon :name="capture.reading.value ? 'lucide:loader-circle' : 'lucide:sparkles'" class="size-4" :class="capture.reading.value ? 'animate-spin' : ''" />
                  {{ capture.reading.value ? "Lendo…" : "Ler anotação" }}
                </button>
              </div>
            </div>

            <div v-else class="grid gap-3 rounded-lg border bg-card p-4">
              <label class="grid gap-1 text-sm font-medium">
                Foto da ficha ou do caderno
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  class="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border file:bg-background file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-foreground"
                  @change="onPhotoChange"
                />
              </label>
              <img
                v-if="photoPreview"
                :src="photoPreview"
                alt="Prévia da foto escolhida"
                class="max-h-72 w-auto rounded-md border object-contain"
              />
              <p class="text-xs text-muted-foreground">
                A foto é reduzida neste aparelho antes de subir (até 1600 px no maior lado).
              </p>
              <div class="flex flex-wrap items-end gap-3">
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Língua (opcional)
                  <input
                    v-model="languageHint"
                    type="text"
                    placeholder="pt, fr, en, ja…"
                    class="h-9 w-32 rounded-md border bg-background px-2 text-sm text-foreground"
                  />
                </label>
                <button
                  type="button"
                  class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
                  :disabled="!photoFile || capture.reading.value"
                  @click="readPhoto"
                >
                  <Icon :name="capture.reading.value ? 'lucide:loader-circle' : 'lucide:sparkles'" class="size-4" :class="capture.reading.value ? 'animate-spin' : ''" />
                  {{ capture.reading.value ? "Lendo…" : "Ler foto" }}
                </button>
              </div>
            </div>

            <div
              v-if="capture.state.value === 'error'"
              class="flex flex-wrap items-center gap-3 rounded-md border border-destructive/30 px-3 py-2 text-sm"
            >
              <Icon name="lucide:cloud-off" class="size-4 shrink-0 text-destructive/70" />
              <span class="flex-1">{{ capture.error.value }}</span>
              <button type="button" class="text-sm text-primary underline-offset-2 hover:underline" @click="door = 'manual'">
                Preencher à mão
              </button>
            </div>
          </template>

          <!-- ── Rascunho lido: conferência ────────────────────────────── -->
          <div v-else class="grid gap-4">
            <div class="grid gap-3 rounded-lg border bg-card p-4">
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="text-base font-bold">O que foi lido</h2>
                <UiBadge v-if="capture.draft.value?.language" variant="outline" class="px-1.5 py-0 text-xs">
                  Língua: {{ capture.draft.value.language }}
                </UiBadge>
                <button
                  type="button"
                  class="ml-auto text-sm text-muted-foreground underline-offset-2 hover:underline"
                  @click="capture.reset()"
                >
                  Ler outra
                </button>
              </div>
              <div class="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Nome
                  <input
                    v-model="draftName"
                    type="text"
                    class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
                  />
                </label>
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Tipo
                  <select v-model="draftKind" class="h-9 rounded-md border bg-background px-2 text-sm text-foreground">
                    <option v-for="option in KIND_OPTIONS" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Rendimento
                  <span class="flex items-center gap-1">
                    <input
                      v-model="draftYieldQuantity"
                      type="text"
                      inputmode="decimal"
                      class="h-9 w-20 rounded-md border bg-background px-2 text-sm text-foreground"
                    />
                    <select v-model="draftYieldUnit" class="h-9 rounded-md border bg-background px-2 text-sm text-foreground">
                      <option v-for="unit in YIELD_UNIT_OPTIONS" :key="unit" :value="unit">{{ unit }}</option>
                    </select>
                  </span>
                </label>
              </div>
            </div>

            <div class="overflow-hidden rounded-lg border">
              <table class="w-full text-sm">
                <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th class="px-3 py-2 font-semibold">Ingrediente lido</th>
                    <th class="px-3 py-2 text-right font-semibold">Qtd</th>
                    <th class="px-3 py-2 font-semibold">Insumo</th>
                    <th class="px-3 py-2 font-semibold">Papel</th>
                  </tr>
                </thead>
                <tbody class="divide-y">
                  <tr v-if="!draftItems.length">
                    <td colspan="4" class="px-3 py-4 text-center text-muted-foreground">
                      Nenhum ingrediente foi lido. Continue no editor e preencha à mão.
                    </td>
                  </tr>
                  <tr v-for="(item, index) in draftItems" :key="`${item.name}-${index}`">
                    <td class="px-3 py-2">
                      <p class="font-medium">{{ item.name }}</p>
                      <p v-if="item.original_text && item.original_text !== item.name" class="text-xs text-muted-foreground">
                        {{ item.original_text }}
                      </p>
                    </td>
                    <td class="px-3 py-2 text-right tabular-nums">{{ item.quantity }} {{ item.unit }}</td>
                    <td class="px-3 py-2">
                      <select
                        :value="item.sku"
                        class="h-9 w-full min-w-40 rounded-md border bg-background px-2 text-sm text-foreground"
                        :class="item.sku ? '' : 'border-amber-500/50'"
                        :aria-label="`Insumo para ${item.name}`"
                        @change="chooseCandidate(index, ($event.target as HTMLSelectElement).value)"
                      >
                        <option value="">Sem insumo (casar no editor)</option>
                        <option v-for="candidate in item.candidates" :key="candidate.sku" :value="candidate.sku">
                          {{ candidate.name }} · {{ candidate.sku }}
                        </option>
                      </select>
                      <p v-if="candidateFor(item) && item.match_confidence" class="mt-0.5 text-xs text-muted-foreground">
                        Confiança {{ item.match_confidence }}
                      </p>
                    </td>
                    <td class="px-3 py-2">
                      <select
                        :value="item.role"
                        class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
                        :aria-label="`Papel de ${item.name}`"
                        @change="setRole(index, ($event.target as HTMLSelectElement).value)"
                      >
                        <option v-for="role in ROLE_OPTIONS" :key="role.value" :value="role.value">{{ role.label }}</option>
                      </select>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="capture.draft.value?.steps?.length" class="rounded-lg border bg-card p-4">
              <p class="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">Passos lidos</p>
              <ol class="list-decimal space-y-0.5 pl-5 text-sm">
                <li v-for="(step, index) in capture.draft.value.steps" :key="index">{{ step }}</li>
              </ol>
            </div>

            <div class="flex flex-wrap items-center gap-3">
              <p class="text-sm text-muted-foreground">
                <template v-if="unmatchedCount">{{ unmatchedCount }} sem insumo. Dá para casar no editor.</template>
                <template v-else>Todos os ingredientes têm insumo.</template>
              </p>
              <p v-if="draftError" class="text-sm text-destructive">{{ draftError }}</p>
              <button
                type="button"
                class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
                :disabled="creating"
                @click="continueToEditor"
              >
                <Icon name="lucide:arrow-right" class="size-4" />
                {{ creating ? "Criando…" : "Continuar no editor" }}
              </button>
            </div>
          </div>
        </template>

        <!-- ── Manual: direto ao editor vazio ────────────────────────────── -->
        <div v-else class="grid gap-3 rounded-lg border bg-card p-4">
          <p class="text-sm text-muted-foreground">
            Dê um nome e um tipo; a fórmula você monta no editor, com a prévia da lente ao lado.
          </p>
          <div class="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Nome
              <input
                v-model="manualName"
                type="text"
                placeholder="Ex.: Pão de campanha"
                class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
                @keydown.enter="startManual"
              />
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Tipo
              <select v-model="manualKind" class="h-9 rounded-md border bg-background px-2 text-sm text-foreground">
                <option v-for="option in KIND_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Rendimento
              <span class="flex items-center gap-1">
                <input
                  v-model="manualYieldQuantity"
                  type="text"
                  inputmode="decimal"
                  class="h-9 w-20 rounded-md border bg-background px-2 text-sm text-foreground"
                />
                <select v-model="manualYieldUnit" class="h-9 rounded-md border bg-background px-2 text-sm text-foreground">
                  <option v-for="unit in YIELD_UNIT_OPTIONS" :key="unit" :value="unit">{{ unit }}</option>
                </select>
              </span>
            </label>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <p v-if="manualError" class="text-sm text-destructive">{{ manualError }}</p>
            <button
              type="button"
              class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
              :disabled="creating"
              @click="startManual"
            >
              <Icon name="lucide:arrow-right" class="size-4" />
              {{ creating ? "Criando…" : "Abrir o editor" }}
            </button>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
