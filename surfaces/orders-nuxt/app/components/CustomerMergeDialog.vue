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
import {
  mergePair,
  suggestedKeeper,
  type Keeper,
  type MergeCandidateSide,
} from "~/presentation/customers";

const props = defineProps<{
  open: boolean;
  current: CustomerDetailProjection;
  // O candidato escolhido na ficha; vazio abre a busca.
  initialOther: (MergeCandidateSide & { name: string }) | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  merged: [payload: { targetRef: string; sourceRef: string }];
}>();

type Side = MergeCandidateSide & {
  name: string;
  document_display?: string;
  orders_label?: string;
};

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
let previewRun = 0;

const resultItems = computed(() =>
  results.value.map((row) => ({
    label: row.name,
    description: `${row.ref} · ${row.phone_display || "Sem telefone"} · ${row.orders_label}`,
    icon: "i-lucide-user",
    onSelect: () => choose(row),
  })),
);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    other.value = props.initialOther ? { ...props.initialOther } : null;
    search.value = "";
    results.value = [];
    searchError.value = "";
    submitError.value = "";
    keeper.value = other.value
      ? suggestedKeeper(props.current, other.value)
      : "current";
  },
  { immediate: true },
);

watchDebounced(
  search,
  async (q) => {
    const query = q.trim();
    if (query.length < 2) {
      results.value = [];
      return;
    }
    searching.value = true;
    searchError.value = "";
    try {
      results.value = (await searchCustomers(query)).filter(
        (row) => row.ref !== props.current.ref,
      );
    } catch (failure) {
      searchError.value = httpErrorMessage(
        failure,
        "A busca falhou. Tente de novo.",
      );
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

const pair = computed(() =>
  other.value
    ? mergePair(props.current.ref, other.value.ref, keeper.value)
    : null,
);

// A prévia acompanha o par: trocar quem fica muda o que migra e qual lacuna se tapa.
watch(
  () =>
    props.open && pair.value
      ? `${pair.value.source_ref}>${pair.value.target_ref}`
      : "",
  async (key) => {
    const run = ++previewRun;
    preview.value = null;
    previewError.value = "";
    loadingPreview.value = false;
    if (!key || !pair.value) return;
    loadingPreview.value = true;
    try {
      const response = await fetchMergePreview(
        pair.value.source_ref,
        pair.value.target_ref,
      );
      if (run === previewRun) preview.value = response.preview;
    } catch (failure) {
      if (run === previewRun) {
        previewError.value = httpErrorMessage(
          failure,
          "Não foi possível calcular o que muda.",
        );
      }
    } finally {
      if (run === previewRun) loadingPreview.value = false;
    }
  },
  { immediate: true },
);

// [quem sai, quem fica]
const sides = computed<Side[]>(() => {
  if (!other.value) return [];
  const current: Side = props.current;
  return keeper.value === "current"
    ? [other.value, current]
    : [current, other.value];
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
    const result = await postMerge(
      pair.value.source_ref,
      pair.value.target_ref,
    );
    emit("merged", {
      targetRef: result.target_ref,
      sourceRef: result.source_ref,
    });
    emit("update:open", false);
  } catch (failure) {
    submitError.value = httpErrorMessage(
      failure,
      "Não foi possível unificar os cadastros.",
    );
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Unificar cadastros"
    description="Use quando os dois cadastros são a mesma pessoa. Um deles deixa de existir e tudo o que é dele passa para o outro."
    scrollable
    data-customer-merge-dialog
    @update:open="requestOpen"
  >
    <template #body>
      <div class="grid gap-4">
        <!-- 1. Escolher o outro cadastro -->
        <div v-if="!other" class="space-y-2">
          <NuxtFormField label="Com qual cadastro?">
            <NuxtInput
              id="merge-search"
              v-model="search"
              type="search"
              autocomplete="off"
              placeholder="Nome, telefone, CPF, e-mail ou código"
            />
          </NuxtFormField>
          <NuxtAlert
            v-if="searchError"
            color="error"
            variant="subtle"
            :description="searchError"
          />
          <NuxtSkeleton
            v-else-if="searching"
            class="h-24 w-full"
            aria-label="Buscando cadastros"
          />
          <NuxtEmpty
            v-else-if="search.trim().length >= 2 && !results.length"
            icon="i-lucide-user-search"
            title="Nenhum outro cadastro com essa busca"
          />
          <NuxtNavigationMenu
            v-if="results.length"
            orientation="vertical"
            :items="resultItems"
            aria-label="Cadastros encontrados"
          />
        </div>

        <!-- 2 e 3. Quem fica, e o que muda -->
        <template v-else>
          <!-- Quem sai à esquerda, quem fica à direita: a leitura segue a seta. -->
          <div class="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-stretch">
            <NuxtCard
              v-for="(side, index) in sides"
              :key="side.ref"
              :variant="index === 0 ? 'outline' : 'subtle'"
              :class="index === 0 ? 'sm:order-1' : 'sm:order-3'"
              :data-merge-side="index === 0 ? 'source' : 'target'"
            >
              <NuxtBadge
                :color="index === 0 ? 'neutral' : 'primary'"
                variant="subtle"
                :label="index === 0 ? 'Deixa de existir' : 'Fica'"
              />
              <p class="mt-1 font-medium">{{ side.name }}</p>
              <p class="font-mono text-xs text-muted-foreground">
                {{ side.ref }}
              </p>
              <dl class="mt-2 space-y-0.5 text-xs">
                <div class="flex gap-1">
                  <dt class="text-muted-foreground">Telefone:</dt>
                  <dd>{{ side.phone_display || "sem telefone" }}</dd>
                </div>
                <div v-if="side.source_label" class="flex gap-1">
                  <dt class="text-muted-foreground">Origem:</dt>
                  <dd>{{ side.source_label }}</dd>
                </div>
              </dl>
            </NuxtCard>
            <div class="flex items-center justify-center sm:order-2">
              <NuxtButton
                type="button"
                label="Trocar quem fica"
                icon="i-lucide-arrow-left-right"
                color="neutral"
                variant="outline"
                :disabled="busy"
                data-merge-swap
                @click="swap"
              />
            </div>
          </div>

          <NuxtAlert
            v-if="loadingPreview"
            color="neutral"
            variant="subtle"
            icon="i-line-md-loading-loop"
            description="Calculando o que muda…"
            aria-live="polite"
          />
          <NuxtAlert
            v-else-if="previewError"
            color="error"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="previewError"
            aria-live="polite"
          />
          <NuxtAlert
            v-else-if="preview"
            color="neutral"
            variant="subtle"
            aria-live="polite"
          >
            <template #description>
              <p>{{ preview.summary }}</p>
              <div v-if="preview.moves.length">
                <p class="font-medium">Passa para o cadastro que fica:</p>
                <ul class="mt-1 list-inside list-disc" data-merge-moves>
                  <li v-for="move in preview.moves" :key="move.ref">
                    {{ move.label }}
                  </li>
                </ul>
              </div>
              <p v-else class="text-muted-foreground">
                O cadastro que sai não tem pedidos, contatos nem endereços para
                passar.
              </p>
              <div v-if="preview.fills.length">
                <p class="font-medium">
                  O cadastro que fica ganha o que não tinha:
                </p>
                <ul class="mt-1 list-inside list-disc">
                  <li v-for="fill in preview.fills" :key="fill.field_label">
                    {{ fill.field_label }}: {{ fill.value }}
                  </li>
                </ul>
              </div>
              <p v-if="preview.loyalty_label">{{ preview.loyalty_label }}.</p>
              <p class="text-muted-foreground">{{ preview.undo_notice }}</p>
            </template>
          </NuxtAlert>

          <NuxtAlert
            v-if="submitError"
            color="error"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="submitError"
          />
        </template>
      </div>
    </template>
    <template #footer>
      <NuxtButton
        v-if="other && !initialOther"
        type="button"
        label="Escolher outro cadastro"
        color="neutral"
        variant="outline"
        :disabled="busy"
        @click="other = null"
      />
      <NuxtButton
        type="button"
        label="Voltar"
        color="neutral"
        variant="outline"
        :disabled="busy"
        @click="requestOpen(false)"
      />
      <NuxtButton
        v-if="other"
        type="button"
        :label="busy ? 'Unificando…' : 'Unificar os dois cadastros'"
        :disabled="busy || !preview || loadingPreview"
        color="primary"
        :loading="busy"
        data-merge-confirm
        @click="confirm"
      />
    </template>
  </NuxtModal>
</template>
