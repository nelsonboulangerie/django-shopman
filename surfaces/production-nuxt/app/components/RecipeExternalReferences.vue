<script setup lang="ts">
// Fontes da receita (o identificador é `external_references`): livros, vídeos e artigos de onde ela veio. São da
// receita, não da versão (valem para todas). Ler é de todos; adicionar e remover
// pede `can_edit`. Grava pela lista inteira (PATCH da receita), e quem recusa de
// verdade é o servidor; a tela só não manda o que ele certamente recusaria.
import type { EntryActionResult } from "~/composables/useRecipeEntry";
import type { ExternalReferenceInput, ExternalReferenceProjection } from "~/types/recipeBook";
import {
  MAX_REFERENCES,
  emptyReferenceDraft,
  referenceDraftErrors,
  withReference,
  withoutReference,
} from "~/presentation/recipeReferences";

const props = defineProps<{
  references: readonly ExternalReferenceProjection[];
  canEdit: boolean;
  busy: boolean;
  save: (references: ExternalReferenceInput[]) => Promise<EntryActionResult>;
}>();

const addOpen = ref(false);
const draft = ref(emptyReferenceDraft());
const touched = ref(false);
const serverError = ref("");
const errors = computed(() => (touched.value ? referenceDraftErrors(draft.value) : {}));
const full = computed(() => props.references.length >= MAX_REFERENCES);

function openAdd() {
  draft.value = emptyReferenceDraft();
  touched.value = false;
  serverError.value = "";
  addOpen.value = true;
}

async function confirmAdd() {
  touched.value = true;
  if (Object.keys(referenceDraftErrors(draft.value)).length) return;
  const result = await props.save(withReference(props.references, draft.value));
  if (result.ok) addOpen.value = false;
  else serverError.value = result.message ?? "";
}

const removeIndex = ref<number | null>(null);
const removing = computed(() => (removeIndex.value === null ? null : props.references[removeIndex.value] ?? null));
const removeDescription = computed(() =>
  removing.value ? `"${removing.value.title}" sai das fontes desta receita.` : "",
);

async function confirmRemove() {
  if (removeIndex.value === null) return;
  const result = await props.save(withoutReference(props.references, removeIndex.value));
  if (result.ok) removeIndex.value = null;
}
</script>

<template>
  <section class="rounded-md border bg-card p-3" aria-labelledby="recipe-references-title">
    <div class="mb-2 flex items-center gap-2">
      <h3 id="recipe-references-title" class="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Fontes
      </h3>
      <NuxtButton
        v-if="canEdit && !full"
        class="ml-auto"
        color="neutral"
        variant="outline"
        icon="i-lucide-plus"
        label="Adicionar"
        @click="openAdd"
      />
    </div>
    <p class="mb-2 text-xs text-muted-foreground">Livros, vídeos e artigos de onde esta receita veio. Valem para todas as versões.</p>

    <ul v-if="references.length" class="grid gap-2">
      <li v-for="(reference, index) in references" :key="`${index}-${reference.title}`" class="flex items-start gap-2 text-sm">
        <Icon :name="reference.url ? 'lucide:link' : 'lucide:book-open'" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div class="min-w-0 flex-1">
          <a
            v-if="reference.url"
            :href="reference.url"
            target="_blank"
            rel="noopener noreferrer"
            class="font-medium text-primary underline-offset-2 hover:underline"
          >{{ reference.title }}</a>
          <span v-else class="font-medium">{{ reference.title }}</span>
          <span v-if="reference.host_display" class="ml-1 text-xs text-muted-foreground">{{ reference.host_display }}</span>
          <p v-if="reference.note" class="whitespace-pre-line text-xs text-muted-foreground">{{ reference.note }}</p>
        </div>
        <NuxtButton
          v-if="canEdit"
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          square
          :aria-label="`Remover a fonte ${reference.title}`"
          :title="`Remover a fonte ${reference.title}`"
          :disabled="busy"
          @click="removeIndex = index"
        />
      </li>
    </ul>
    <p v-else class="text-sm text-muted-foreground">Nenhuma fonte ainda.</p>

    <!-- ── Adicionar ─────────────────────────────────────────────────────── -->
    <NuxtModal
      v-model:open="addOpen"
      title="Adicionar fonte"
      description="Um livro, um vídeo ou um artigo de onde a receita veio."
      :ui="{ content: 'sm:max-w-md' }"
    >
      <template #body>
        <form id="recipe-reference-form" class="grid gap-3" @submit.prevent="confirmAdd">
          <NuxtFormField label="Título" :error="errors.title || false">
            <NuxtInput
              v-model="draft.title"
              type="text"
              autofocus
              class="w-full"
              placeholder="Ex.: Tartine Bread, de Chad Robertson"
            />
          </NuxtFormField>
          <NuxtFormField label="Link (opcional)" :error="errors.url || false">
            <NuxtInput v-model="draft.url" type="url" inputmode="url" class="w-full" placeholder="https://" />
          </NuxtFormField>
          <NuxtFormField label="Nota (opcional)" :error="errors.note || false">
            <NuxtTextarea v-model="draft.note" :rows="2" class="w-full" placeholder="Ex.: página 48, a fórmula base" />
          </NuxtFormField>
          <p v-if="serverError" class="text-sm text-destructive">{{ serverError }}</p>
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="addOpen = false" />
          <NuxtButton type="submit" form="recipe-reference-form" label="Adicionar" :disabled="busy" />
        </div>
      </template>
    </NuxtModal>

    <!-- ── Remover (pede confirmação) ────────────────────────────────────── -->
    <NuxtModal
      :open="removing !== null"
      title="Remover a fonte"
      :description="removeDescription"
      :ui="{ content: 'sm:max-w-sm' }"
      @update:open="(v: boolean) => { if (!v) removeIndex = null; }"
    >
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="removeIndex = null" />
          <NuxtButton color="error" label="Remover" :disabled="busy" @click="confirmRemove" />
        </div>
      </template>
    </NuxtModal>
  </section>
</template>
