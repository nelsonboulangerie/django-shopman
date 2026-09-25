<script setup lang="ts">
// Unificar dois cadastros — lado a lado, com a PRÉVIA antes do gesto.
//
// Três passos numa caixa só: (1) escolher o outro cadastro (vem pré-escolhido
// quando o gestor clicou num candidato; senão, busca), (2) escolher quem FICA —
// a tela sugere, o gestor decide — e (3) ler o que muda e confirmar. A prévia é
// a unificação de verdade, feita e desfeita no servidor (`MergeService.preview`):
// o que ela diz é o que o "Unificar" faz.
import type {
  CustomerDetailProjection,
  CustomerRowProjection,
  MergePreviewProjection,
} from "~/generated/ordersContract";
import { mergePair, suggestedKeeper, type Keeper, type MergeCandidateSide } from "~/presentation/customers";

const props = defineProps<{
  open: boolean;
  current: CustomerDetailProjection;
  // O candidato escolhido na ficha; vazio abre a busca.
  initialOther: MergeCandidateSide & { name: string } | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  merged: [payload: { targetRef: string; sourceRef: string }];
}>();

type Side = MergeCandidateSide & { name: string; document_display?: string; orders_label?: string };

const other = ref<Side | null>(null);
const keeper = ref<Keeper>("current");
const preview = ref<MergePreviewProjection | null>(null);
const previewError = ref("");
const loadingPreview = ref(false);
const busy = ref(false);
const submitError = ref("");

const search = ref("");
const results = ref<CustomerRowProjection[]>([]);
const searching = ref(false);
const searchError = ref("");

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    other.value = props.initialOther ? { ...props.initialOther } : null;
    search.value = "";
    results.value = [];
    searchError.value = "";
    submitError.value = "";
    keeper.value = other.value ? suggestedKeeper(props.current, other.value) : "current";
  },
  { immediate: true },
);

watchDebounced(
  search,
  async (q) => {
    const query = q.trim();
    if (query.length < 2) { results.value = []; return; }
    searching.value = true;
    searchError.value = "";
    try {
      results.value = (await searchCustomers(query)).filter((row) => row.ref !== props.current.ref);
    } catch (failure) {
      searchError.value = httpErrorMessage(failure, "A busca falhou. Tente de novo.");
    } finally {
      searching.value = false;
    }
  },
  { debounce: 300 },
);

function choose(row: CustomerRowProjection) {
  other.value = row;
  keeper.value = suggestedKeeper(props.current, row);
}

const pair = computed(() => (other.value ? mergePair(props.current.ref, other.value.ref, keeper.value) : null));

// A prévia acompanha o par: trocar quem fica muda o que migra e qual lacuna se tapa.
watch(
  () => (props.open && pair.value ? `${pair.value.source_ref}>${pair.value.target_ref}` : ""),
  async (key) => {
    preview.value = null;
    previewError.value = "";
    if (!key || !pair.value) return;
    loadingPreview.value = true;
    const requested = key;
    try {
      const response = await fetchMergePreview(pair.value.source_ref, pair.value.target_ref);
      if (pair.value && `${pair.value.source_ref}>${pair.value.target_ref}` === requested) preview.value = response.preview;
    } catch (failure) {
      previewError.value = httpErrorMessage(failure, "Não foi possível calcular o que muda.");
    } finally {
      loadingPreview.value = false;
    }
  },
  { immediate: true },
);

// [quem sai, quem fica]
const sides = computed<Side[]>(() => {
  if (!other.value) return [];
  const current: Side = props.current;
  return keeper.value === "current" ? [other.value, current] : [current, other.value];
});

function swap() {
  keeper.value = keeper.value === "current" ? "other" : "current";
}

function requestOpen(open: boolean) {
  if (!open && busy.value) return;
  emit("update:open", open);
}

async function confirm() {
  if (!pair.value || !preview.value || busy.value) return;
  busy.value = true;
  submitError.value = "";
  try {
    const result = await postMerge(pair.value.source_ref, pair.value.target_ref);
    emit("merged", { targetRef: result.target_ref, sourceRef: result.source_ref });
    emit("update:open", false);
  } catch (failure) {
    submitError.value = httpErrorMessage(failure, "Não foi possível unificar os cadastros.");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <UiDialog :open="open" @update:open="requestOpen">
    <UiDialogContent class="max-h-[90dvh] overflow-y-auto sm:max-w-2xl" data-customer-merge-dialog>
      <UiDialogHeader>
        <UiDialogTitle>Unificar cadastros</UiDialogTitle>
        <UiDialogDescription>
          Use quando os dois cadastros são a mesma pessoa. Um deles deixa de existir e tudo o que é dele passa para o outro.
        </UiDialogDescription>
      </UiDialogHeader>

      <!-- 1. Escolher o outro cadastro -->
      <div v-if="!other" class="space-y-2">
        <label class="block text-sm font-medium" for="merge-search">Com qual cadastro?</label>
        <input
          id="merge-search"
          v-model="search"
          type="search"
          autocomplete="off"
          placeholder="Nome, telefone, CPF, e-mail ou código"
          class="h-control w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
        />
        <p v-if="searchError" role="alert" class="text-sm text-destructive">{{ searchError }}</p>
        <p v-else-if="searching" class="text-sm text-muted-foreground">Buscando…</p>
        <p v-else-if="search.trim().length >= 2 && !results.length" class="text-sm text-muted-foreground">Nenhum outro cadastro com essa busca.</p>
        <ul v-if="results.length" class="divide-y rounded-md border">
          <li v-for="row in results" :key="row.ref">
            <button
              type="button"
              class="flex min-h-control w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition hover:bg-accent"
              @click="choose(row)"
            >
              <span>
                <span class="font-medium">{{ row.name }}</span>
                <span class="ml-2 font-mono text-xs text-muted-foreground">{{ row.ref }}</span>
              </span>
              <span class="text-xs text-muted-foreground">{{ row.phone_display || "Sem telefone" }} · {{ row.orders_label }}</span>
            </button>
          </li>
        </ul>
      </div>

      <!-- 2 e 3. Quem fica, e o que muda -->
      <template v-else>
        <!-- Quem sai à esquerda, quem fica à direita: a leitura segue a seta. -->
        <div class="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-stretch">
          <article
            v-for="(side, index) in sides"
            :key="side.ref"
            class="rounded-lg border p-3 text-sm"
            :class="[
              index === 0 ? 'border-dashed opacity-80 sm:order-1' : 'border-primary bg-primary/5 sm:order-3',
            ]"
            :data-merge-side="index === 0 ? 'source' : 'target'"
          >
            <p class="text-xs font-semibold uppercase tracking-wide" :class="index === 0 ? 'text-muted-foreground' : 'text-primary'">
              {{ index === 0 ? "Deixa de existir" : "Fica" }}
            </p>
            <p class="mt-1 font-medium">{{ side.name }}</p>
            <p class="font-mono text-xs text-muted-foreground">{{ side.ref }}</p>
            <dl class="mt-2 space-y-0.5 text-xs">
              <div class="flex gap-1"><dt class="text-muted-foreground">Telefone:</dt><dd>{{ side.phone_display || "sem telefone" }}</dd></div>
              <div v-if="side.source_label" class="flex gap-1"><dt class="text-muted-foreground">Origem:</dt><dd>{{ side.source_label }}</dd></div>
            </dl>
          </article>
          <div class="flex items-center justify-center sm:order-2">
            <button
              type="button"
              class="inline-flex min-h-control items-center gap-1.5 rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
              :disabled="busy"
              data-merge-swap
              @click="swap"
            >
              <Icon name="lucide:arrow-left-right" class="size-4" />
              Trocar quem fica
            </button>
          </div>
        </div>

        <div class="space-y-3 rounded-lg bg-muted/40 p-3 text-sm" aria-live="polite">
          <p v-if="loadingPreview" class="text-muted-foreground">Calculando o que muda…</p>
          <p v-else-if="previewError" role="alert" class="text-destructive">{{ previewError }}</p>
          <template v-else-if="preview">
            <p>{{ preview.summary }}</p>
            <div v-if="preview.moves.length">
              <p class="font-medium">Passa para o cadastro que fica:</p>
              <ul class="mt-1 list-inside list-disc" data-merge-moves>
                <li v-for="move in preview.moves" :key="move.ref">{{ move.label }}</li>
              </ul>
            </div>
            <p v-else class="text-muted-foreground">O cadastro que sai não tem pedidos, contatos nem endereços para passar.</p>
            <div v-if="preview.fills.length">
              <p class="font-medium">O cadastro que fica ganha o que não tinha:</p>
              <ul class="mt-1 list-inside list-disc">
                <li v-for="fill in preview.fills" :key="fill.field_label">{{ fill.field_label }}: {{ fill.value }}</li>
              </ul>
            </div>
            <p v-if="preview.loyalty_label">{{ preview.loyalty_label }}.</p>
            <p class="text-muted-foreground">{{ preview.undo_notice }}</p>
          </template>
        </div>

        <p v-if="submitError" role="alert" class="text-sm text-destructive">{{ submitError }}</p>
      </template>

      <UiDialogFooter>
        <button
          v-if="other && !initialOther"
          type="button"
          class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
          :disabled="busy"
          @click="other = null"
        >
          Escolher outro cadastro
        </button>
        <button
          type="button"
          class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
          :disabled="busy"
          @click="requestOpen(false)"
        >
          Voltar
        </button>
        <button
          v-if="other"
          type="button"
          :disabled="busy || !preview || loadingPreview"
          class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          data-merge-confirm
          @click="confirm"
        >
          {{ busy ? "Unificando…" : "Unificar os dois cadastros" }}
        </button>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
