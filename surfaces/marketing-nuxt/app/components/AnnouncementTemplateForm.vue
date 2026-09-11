<script setup lang="ts">
// O texto que vai para o cliente, escrito aqui.
//
// Apresentacional: o pai é dono do fetch e da escrita. O vocabulário de variáveis vem do
// backend (`options.variables`), nunca hardcoded — variável nova no domínio aparece aqui
// sem deploy de front, e a tela nunca oferece uma que o resolvedor não conhece.
import type { AnnouncementTemplate } from "~/types/campaign";
import { useMarketingDraft } from "~/composables/useMarketingDraft";
import type { MarketingDraftPayload } from "~/utils/marketingDraft";
import { marketingVariableLabel } from "~/presentation/marketingVariables";

const props = defineProps<{
  template: AnnouncementTemplate | null; // null = criando
  variables: string[];
  /** Há credencial de IA no ambiente? Sem ela o bloco de IA não aparece. */
  aiAvailable?: boolean;
  busy?: boolean;
  draftOwner?: string;
}>();

const emit = defineEmits<{
  submit: [payload: Record<string, unknown>];
  cancel: [];
}>();

const name = ref("");
const body = ref("");
const imageSource = ref("product");
const useAi = ref(false);
const aiPrompt = ref("");
const isActive = ref(true);

const IMAGE_SOURCES = [
  { value: "product", label: "Foto do produto" },
  { value: "gallery", label: "Galeria do produto" },
  { value: "custom", label: "Imagem fixa" },
  { value: "none", label: "Sem imagem" },
];

const DRAFT_LABELS = {
  name: "Nome",
  body: "Texto",
  image_source: "Imagem",
  use_ai_generation: "Uso de IA",
  ai_prompt: "Instrução para IA",
  is_active: "Modelo ativo",
};

// Estado novo a cada modelo aberto — senão o formulário herdaria o anterior.
watch(
  () => props.template?.pk ?? null,
  () => {
    const t = props.template;
    name.value = t?.name ?? "";
    body.value = t?.body ?? "";
    imageSource.value = t?.image_source || "product";
    useAi.value = Boolean(t?.use_ai_generation);
    aiPrompt.value = t?.ai_prompt ?? "";
    isActive.value = t?.is_active ?? true;
  },
  { immediate: true },
);

const canSubmit = computed(
  () =>
    !props.busy && name.value.trim().length > 0 && body.value.trim().length > 0,
);

/** Variáveis que o corpo realmente usa — para o gestor ver o que vai ser substituído. */
const usedVariables = computed(() =>
  props.variables.filter((v) => body.value.includes(`{{${v}}}`)),
);

function templatePayload(): MarketingDraftPayload {
  return {
    name: name.value,
    body: body.value,
    image_source: imageSource.value,
    use_ai_generation: useAi.value,
    ai_prompt: aiPrompt.value,
    is_active: isActive.value,
  };
}

function templateBase(): MarketingDraftPayload {
  const template = props.template;
  return {
    name: template?.name ?? "",
    body: template?.body ?? "",
    image_source: template?.image_source || "product",
    use_ai_generation: Boolean(template?.use_ai_generation),
    ai_prompt: template?.ai_prompt ?? "",
    is_active: template?.is_active ?? true,
  };
}

function applyTemplateDraft(payload: MarketingDraftPayload) {
  name.value = typeof payload.name === "string" ? payload.name : "";
  body.value = typeof payload.body === "string" ? payload.body : "";
  imageSource.value =
    typeof payload.image_source === "string" ? payload.image_source : "product";
  useAi.value = Boolean(payload.use_ai_generation);
  aiPrompt.value =
    typeof payload.ai_prompt === "string" ? payload.ai_prompt : "";
  isActive.value = payload.is_active !== false;
}

const draft = useMarketingDraft({
  owner: () => props.draftOwner ?? "",
  resource: () => `template:${props.template?.pk ?? "new"}`,
  version: () => props.template?.updated_at ?? "new",
  base: templateBase,
  current: templatePayload,
  apply: applyTemplateDraft,
});

function insertVariable(variable: string) {
  body.value = `${body.value}{{${variable}}}`;
}

function submit() {
  if (!canSubmit.value) return;
  draft.flush();
  emit("submit", {
    name: name.value.trim(),
    body: body.value.trim(),
    image_source: imageSource.value,
    use_ai_generation: useAi.value,
    ai_prompt: aiPrompt.value.trim(),
    is_active: isActive.value,
    // O backend guarda as variáveis declaradas do modelo; mandamos as que o corpo usa,
    // para a documentação não divergir do texto.
    variables: usedVariables.value,
  });
}
</script>

<template>
  <form class="space-y-5" @submit.prevent="submit">
    <DraftRecoveryNotice
      :state="draft.state.value"
      :saved-at="draft.savedAt.value"
      :conflicts="draft.conflicts.value"
      :labels="DRAFT_LABELS"
      @keep-local="draft.keepLocal()"
      @keep-server="draft.keepServer()"
      @discard="draft.discard()"
    />
    <div>
      <label for="tpl-name" class="mb-1 block text-sm font-medium"
        >Nome do modelo</label
      >
      <input
        id="tpl-name"
        v-model="name"
        type="text"
        placeholder="Saiu do forno"
        class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
      />
    </div>

    <div>
      <label for="tpl-body" class="mb-1 block text-sm font-medium">Texto</label>
      <textarea
        id="tpl-body"
        v-model="body"
        rows="4"
        placeholder="O pão acabou de sair do forno!"
        class="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
      ></textarea>

      <!-- Vocabulário vindo do backend: clicar insere. Digitar {{nome_errado}} renderiza
           vazio na cara do cliente, e um botão evita o erro de digitação. -->
      <p class="mt-2 text-xs text-muted-foreground">Variáveis disponíveis</p>
      <div class="mt-1 flex flex-wrap gap-1">
        <button
          v-for="variable in variables"
          :key="variable"
          type="button"
          :title="`Insere {{${variable}}}`"
          class="rounded border border-border px-2 py-1 text-xs transition hover:bg-muted"
          :class="
            usedVariables.includes(variable)
              ? 'border-primary text-primary'
              : ''
          "
          @click="insertVariable(variable)"
        >
          {{ marketingVariableLabel(variable) }}
        </button>
      </div>
    </div>

    <div>
      <label for="tpl-image" class="mb-1 block text-sm font-medium"
        >Imagem</label
      >
      <UiNativeSelect
        id="tpl-image"
        v-model="imageSource"
        class="w-full"
      >
        <option
          v-for="source in IMAGE_SOURCES"
          :key="source.value"
          :value="source.value"
        >
          {{ source.label }}
        </option>
      </UiNativeSelect>
    </div>

    <!-- Two server-side gates plus the credential decide availability. -->
    <fieldset
      v-if="aiAvailable"
      class="rounded-lg border border-border bg-card p-4"
    >
      <legend class="px-1 text-sm font-medium">Sugestão de texto</legend>
      <label class="flex items-start gap-2 text-sm">
        <input
          v-model="useAi"
          type="checkbox"
          class="mt-0.5 size-4 rounded border-border"
        />
        <span>
          Oferecer “Sugerir texto” durante a revisão
          <span class="block text-xs text-muted-foreground">
            A sugestão aparece ao lado do texto e só entra no rascunho se alguém
            escolher usar. Nunca publica sozinha.
          </span>
        </span>
      </label>
      <div v-if="useAi" class="mt-3">
        <label for="tpl-ai" class="mb-1 block text-xs font-medium"
          >Orientação de estilo</label
        >
        <textarea
          id="tpl-ai"
          v-model="aiPrompt"
          rows="2"
          placeholder="Fale do cheiro e do miolo. Uma frase."
          class="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
        ></textarea>
        <p class="mt-1 text-xs text-muted-foreground">
          Não inclua preço, validade, estoque, link ou dados pessoais: esses
          fatos continuam sob controle do sistema.
        </p>
      </div>
    </fieldset>

    <label class="flex items-center gap-2 text-sm">
      <input
        v-model="isActive"
        type="checkbox"
        class="size-4 rounded border-border"
      />
      Ativo
    </label>

    <div class="flex items-center justify-end gap-2">
      <button
        type="button"
        class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
        @click="emit('cancel')"
      >
        Cancelar
      </button>
      <button
        type="submit"
        :disabled="!canSubmit"
        class="rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition disabled:opacity-40"
      >
        {{ template ? "Salvar" : "Criar modelo" }}
      </button>
    </div>
  </form>
</template>
