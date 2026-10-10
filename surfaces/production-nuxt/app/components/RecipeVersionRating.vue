<script setup lang="ts">
// Nota da versão selecionada: a média de cada critério e a geral, e o botão de
// avaliar (0 a 5 por critério ativo). Os critérios são do Admin; a tela não
// conhece nenhum pelo nome. Rascunho também recebe nota (D24). Avaliar de novo
// substitui a nota anterior deste operador. Basta ler o inventário para avaliar.
import type { EntryActionResult } from "~/composables/useRecipeEntry";
import type {
  RatingCriterionProjection,
  RecipeVersionProjection,
  VersionRatingProjection,
} from "~/types/recipeBook";
import {
  RATING_SCALE,
  initialScores,
  missingCriteria,
  overallLabel,
  ratingFor,
  scoresForPayload,
} from "~/presentation/recipeRating";

const props = defineProps<{
  version: RecipeVersionProjection | null;
  criteria: readonly RatingCriterionProjection[];
  ratings: readonly VersionRatingProjection[];
  busy: boolean;
  rate: (number: number, scores: Record<string, number>) => Promise<EntryActionResult>;
}>();

const rating = computed(() => ratingFor(props.ratings, props.version?.number));

const open = ref(false);
const scores = ref<Record<string, number | null>>({});
const serverError = ref("");
const missing = computed(() => missingCriteria(props.criteria, scores.value));

function openRate() {
  scores.value = initialScores(rating.value);
  serverError.value = "";
  open.value = true;
}

function pick(criterionId: number, value: number) {
  scores.value = { ...scores.value, [String(criterionId)]: value };
}

async function confirmRate() {
  if (!props.version || missing.value.length) return;
  const result = await props.rate(props.version.number, scoresForPayload(props.criteria, scores.value));
  if (result.ok) {
    open.value = false;
    useSonner.success(`Nota da versão ${props.version.number} salva.`);
  } else {
    serverError.value = result.message ?? "";
  }
}
</script>

<template>
  <section v-if="version" class="rounded-md border bg-card p-3" aria-labelledby="recipe-rating-title">
    <div class="mb-2 flex items-center gap-2">
      <h3 id="recipe-rating-title" class="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Nota da versão {{ version.number }}
      </h3>
      <NuxtButton
        v-if="criteria.length"
        class="ml-auto"
        color="neutral"
        variant="outline"
        icon="i-lucide-star"
        :label="rating?.rated_by_me ? 'Mudar minha nota' : 'Avaliar'"
        @click="openRate"
      />
    </div>

    <p v-if="!criteria.length" class="text-sm text-muted-foreground">Nenhum critério de nota ativo. Ative um no Admin.</p>
    <template v-else>
      <p class="text-sm">
        <b class="tabular-nums">{{ overallLabel(rating) }}</b>
        <span class="ml-1 text-xs text-muted-foreground">{{ rating?.ratings_count_display ?? "Nenhuma avaliação" }}</span>
      </p>
      <dl v-if="rating?.ratings_count" class="mt-2 grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1 text-sm">
        <template v-for="item in rating.criteria" :key="item.criterion_id">
          <dt class="truncate text-muted-foreground">{{ item.name }}</dt>
          <dd class="text-right tabular-nums">{{ item.average_display || "sem nota" }}</dd>
          <dd class="text-right text-xs tabular-nums text-muted-foreground">
            <template v-if="item.my_score !== null">sua: {{ item.my_score }}</template>
          </dd>
        </template>
      </dl>
      <p v-if="rating?.rated_by_me" class="mt-1 text-xs text-muted-foreground">Você avaliou em {{ rating.my_rated_at_display }}.</p>
    </template>

    <NuxtModal
      v-model:open="open"
      :title="`Avaliar a versão ${version.number}`"
      description="Dê uma nota de 0 a 5 a cada critério. Se você já avaliou esta versão, a nota nova substitui a anterior."
      :ui="{ content: 'sm:max-w-md' }"
    >
      <template #body>
        <form id="recipe-rating-form" class="grid gap-4" @submit.prevent="confirmRate">
          <fieldset v-for="criterion in criteria" :key="criterion.id" class="grid gap-1.5">
            <legend class="text-sm font-medium">{{ criterion.name }}</legend>
            <p v-if="criterion.description" class="text-xs text-muted-foreground">{{ criterion.description }}</p>
            <div class="flex flex-wrap gap-1.5" role="radiogroup" :aria-label="`Nota de ${criterion.name}`">
              <NuxtButton
                v-for="value in RATING_SCALE"
                :key="value"
                role="radio"
                class="min-w-11 justify-center tabular-nums"
                color="neutral"
                variant="outline"
                :active="scores[String(criterion.id)] === value"
                active-color="primary"
                active-variant="solid"
                :label="String(value)"
                :aria-checked="scores[String(criterion.id)] === value"
                :aria-label="`${criterion.name}: ${value} de 5`"
                @click="pick(criterion.id, value)"
              />
            </div>
          </fieldset>
          <p v-if="missing.length" class="text-xs text-muted-foreground">
            Falta a nota de: {{ missing.map((criterion) => criterion.name).join(", ") }}.
          </p>
          <p v-if="serverError" class="text-sm text-destructive">{{ serverError }}</p>
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="open = false" />
          <NuxtButton
            type="submit"
            form="recipe-rating-form"
            label="Salvar nota"
            :disabled="busy || missing.length > 0"
          />
        </div>
      </template>
    </NuxtModal>
  </section>
</template>
