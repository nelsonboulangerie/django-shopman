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
      <UiButton
        v-if="canEdit && !full"
        type="button"
        class="ml-auto"
        variant="outline"
        size="sm"
        @click="openAdd"
      >
        <Icon name="lucide:plus" class="size-4" /> Adicionar
      </UiButton>
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
        <UiButton
          v-if="canEdit"
          type="button"
          variant="ghost"
          size="icon-sm"
          :aria-label="`Remover a fonte ${reference.title}`"
          :title="`Remover a fonte ${reference.title}`"
          :disabled="busy"
          @click="removeIndex = index"
        >
          <Icon name="lucide:x" class="size-4" />
        </UiButton>
      </li>
    </ul>
    <p v-else class="text-sm text-muted-foreground">Nenhuma fonte ainda.</p>

    <!-- ── Adicionar ─────────────────────────────────────────────────────── -->
    <UiDialog :open="addOpen" @update:open="(v) => (addOpen = v)">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Adicionar fonte</UiDialogTitle>
          <UiDialogDescription>Um livro, um vídeo ou um artigo de onde a receita veio.</UiDialogDescription>
        </UiDialogHeader>
        <form class="grid gap-3" @submit.prevent="confirmAdd">
          <label class="grid gap-1 text-xs font-medium text-muted-foreground">
            Título
            <UiInput
              v-model="draft.title"
              type="text"
              autofocus
              placeholder="Ex.: Tartine Bread, de Chad Robertson"
              :aria-invalid="errors.title ? 'true' : undefined"
            />
            <span v-if="errors.title" class="text-destructive">{{ errors.title }}</span>
          </label>
          <label class="grid gap-1 text-xs font-medium text-muted-foreground">
            Link (opcional)
            <UiInput
              v-model="draft.url"
              type="url"
              inputmode="url"
              placeholder="https://"
              :aria-invalid="errors.url ? 'true' : undefined"
            />
            <span v-if="errors.url" class="text-destructive">{{ errors.url }}</span>
          </label>
          <label class="grid gap-1 text-xs font-medium text-muted-foreground">
            Nota (opcional)
            <UiTextarea v-model="draft.note" :rows="2" placeholder="Ex.: página 48, a fórmula base" />
            <span v-if="errors.note" class="text-destructive">{{ errors.note }}</span>
          </label>
          <p v-if="serverError" class="text-sm text-destructive">{{ serverError }}</p>
          <UiDialogFooter>
            <UiButton type="button" variant="outline" @click="addOpen = false">
              Cancelar
            </UiButton>
            <UiButton type="submit" :disabled="busy">
              Adicionar
            </UiButton>
          </UiDialogFooter>
        </form>
      </UiDialogContent>
    </UiDialog>

    <!-- ── Remover (pede confirmação) ────────────────────────────────────── -->
    <UiDialog :open="removing !== null" @update:open="(v) => { if (!v) removeIndex = null; }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Remover a fonte</UiDialogTitle>
          <UiDialogDescription>"{{ removing?.title }}" sai das fontes desta receita.</UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter>
          <UiButton type="button" variant="outline" @click="removeIndex = null">
            Cancelar
          </UiButton>
          <UiButton type="button" :disabled="busy" @click="confirmRemove">
            Remover
          </UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </section>
</template>
