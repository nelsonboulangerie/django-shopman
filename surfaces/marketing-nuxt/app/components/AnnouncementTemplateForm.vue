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
const platformVariants = ref<Record<string, Record<string, unknown>>>({});
const instagramFormat = ref<"story" | "feed">("story");
const customImageUrl = ref("");

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
  platform_variants: "Formato e imagem por plataforma",
};

function cloneVariants(
  value: unknown,
): Record<string, Record<string, unknown>> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return JSON.parse(JSON.stringify(value)) as Record<
    string,
    Record<string, unknown>
  >;
}

function imageFromVariants(
  variants: Record<string, Record<string, unknown>>,
): string {
  const legacy = (variants as Record<string, unknown>).image_url;
  if (typeof legacy === "string") return legacy;
  for (const platform of [
    "instagram",
    "facebook",
    "google_business",
    "whatsapp",
  ]) {
    const value = variants[platform]?.image_url;
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function publicationVariants(): Record<string, Record<string, unknown>> {
  const variants = cloneVariants(platformVariants.value);
  Reflect.deleteProperty(variants as Record<string, unknown>, "image_url");
  variants.instagram = {
    ...(variants.instagram || {}),
    publication_format: instagramFormat.value,
  };
  variants.facebook = {
    ...(variants.facebook || {}),
    publication_format: "feed",
  };
  variants.google_business = {
    ...(variants.google_business || {}),
    publication_format: "standard",
  };
  for (const platform of [
    "instagram",
    "facebook",
    "google_business",
    "whatsapp",
  ]) {
    const variant = { ...(variants[platform] || {}) };
    if (imageSource.value === "custom" && customImageUrl.value.trim())
      variant.image_url = customImageUrl.value.trim();
    else Reflect.deleteProperty(variant, "image_url");
    variants[platform] = variant;
  }
  return variants;
}

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
    platformVariants.value = cloneVariants(t?.platform_variants);
    const storedFormat = String(
      t?.platform_variants?.instagram?.publication_format ||
        t?.platform_variants?.instagram?.post_type ||
        "story",
    ).toLowerCase();
    instagramFormat.value = storedFormat === "feed" ? "feed" : "story";
    customImageUrl.value = imageFromVariants(platformVariants.value);
  },
  { immediate: true },
);

const canSubmit = computed(
  () =>
    !props.busy &&
    name.value.trim().length > 0 &&
    body.value.trim().length > 0 &&
    (imageSource.value !== "custom" || customImageUrl.value.trim().length > 0),
);

/** Variáveis que o corpo realmente usa — para o gestor ver o que vai ser substituído. */
const usedVariables = computed(() =>
  props.variables.filter(
    (v) =>
      body.value.includes(`{{${v}}}`) ||
      JSON.stringify(publicationVariants()).includes(`{{${v}}}`),
  ),
);

function templatePayload(): MarketingDraftPayload {
  return {
    name: name.value,
    body: body.value,
    image_source: imageSource.value,
    use_ai_generation: useAi.value,
    ai_prompt: aiPrompt.value,
    is_active: isActive.value,
    platform_variants: publicationVariants(),
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
    platform_variants: cloneVariants(template?.platform_variants),
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
  platformVariants.value = cloneVariants(payload.platform_variants);
  const restoredFormat = String(
    platformVariants.value.instagram?.publication_format ||
      platformVariants.value.instagram?.post_type ||
      "story",
  ).toLowerCase();
  instagramFormat.value = restoredFormat === "feed" ? "feed" : "story";
  customImageUrl.value = imageFromVariants(platformVariants.value);
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
    platform_variants: publicationVariants(),
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
      <label
        for="tpl-name"
        class="mb-1 block text-xs font-medium text-muted-foreground"
        >Nome do modelo</label
      >
      <UiInput
        id="tpl-name"
        v-model="name"
        type="text"
        placeholder="Saiu do forno"
      />
    </div>

    <div>
      <label
        for="tpl-body"
        class="mb-1 block text-xs font-medium text-muted-foreground"
        >Texto</label
      >
      <UiTextarea
        id="tpl-body"
        v-model="body"
        :rows="4"
        placeholder="O pão acabou de sair do forno!"
        class="resize-y"
      />

      <!-- Chips nativos inserem apenas variáveis do backend e evitam redigitação inválida. -->
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
      <label
        for="tpl-image"
        class="mb-1 block text-xs font-medium text-muted-foreground"
        >Imagem</label
      >
      <UiNativeSelect id="tpl-image" v-model="imageSource" class="w-full">
        <option
          v-for="source in IMAGE_SOURCES"
          :key="source.value"
          :value="source.value"
        >
          {{ source.label }}
        </option>
      </UiNativeSelect>
      <div v-if="imageSource === 'custom'" class="mt-3">
        <label
          for="tpl-image-url"
          class="mb-1 block text-xs font-medium text-muted-foreground"
        >
          Endereço público da imagem
        </label>
        <UiInput
          id="tpl-image-url"
          v-model="customImageUrl"
          type="url"
          inputmode="url"
          autocomplete="url"
          placeholder="https://cdn.exemplo.com/story.jpg"
        />
        <p class="mt-1 text-xs text-muted-foreground">
          A plataforma precisa conseguir baixar a imagem sem login. Para
          Stories, use JPEG e prefira uma arte vertical 9:16 pronta para
          publicar.
        </p>
      </div>
      <p
        v-else-if="imageSource === 'none' && instagramFormat === 'story'"
        class="mt-2 text-xs text-warning"
      >
        Campanhas que incluírem Instagram ficarão bloqueadas: Stories exigem
        uma imagem.
      </p>
      <p
        v-else-if="imageSource === 'product' && instagramFormat === 'story'"
        class="mt-2 text-xs text-muted-foreground"
      >
        O Story usará a foto do produto, que precisa estar em JPEG. Se o
        produto estiver sem foto, a aprovação será bloqueada antes de qualquer
        publicação.
      </p>
    </div>

    <fieldset class="rounded-lg border border-border bg-card p-4">
      <legend class="px-1 text-xs font-medium text-muted-foreground">
        Formato no Instagram
      </legend>
      <div class="grid gap-2 sm:grid-cols-2">
        <label
          class="flex cursor-pointer items-start gap-2 rounded-md border p-3"
          :class="
            instagramFormat === 'story'
              ? 'border-primary bg-primary/5'
              : 'border-border'
          "
        >
          <input
            v-model="instagramFormat"
            type="radio"
            value="story"
            class="mt-1"
          />
          <span class="text-sm">
            <span class="block font-medium">Stories — recomendado</span>
            <span class="block text-xs text-muted-foreground">
              Efêmero e urgente: é o padrão para fornadas e oportunidades do
              momento.
            </span>
          </span>
        </label>
        <label
          class="flex cursor-pointer items-start gap-2 rounded-md border p-3"
          :class="
            instagramFormat === 'feed'
              ? 'border-primary bg-primary/5'
              : 'border-border'
          "
        >
          <input
            v-model="instagramFormat"
            type="radio"
            value="feed"
            class="mt-1"
          />
          <span class="text-sm">
            <span class="block font-medium">Feed</span>
            <span class="block text-xs text-muted-foreground">
              Permanente. Só será usado quando você escolher esta opção.
            </span>
          </span>
        </label>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">
        O sistema nunca troca Stories por Feed sozinho. Facebook usa publicação
        na página; Google usa atualização padrão do estabelecimento.
      </p>
    </fieldset>

    <!-- Two server-side gates plus the credential decide availability. -->
    <fieldset
      v-if="aiAvailable"
      class="rounded-lg border border-border bg-card p-4"
    >
      <legend class="px-1 text-xs font-medium text-muted-foreground">
        Sugestão de texto
      </legend>
      <!-- Checkboxes permanecem nativos porque não há primitivo compartilhado de seleção binária. -->
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
        <label
          for="tpl-ai"
          class="mb-1 block text-xs font-medium text-muted-foreground"
          >Orientação de estilo</label
        >
        <UiTextarea
          id="tpl-ai"
          v-model="aiPrompt"
          :rows="2"
          placeholder="Fale do cheiro e do miolo. Uma frase."
          class="resize-y"
        />
        <p class="mt-1 text-xs text-muted-foreground">
          Não inclua preço, validade, estoque, link ou dados pessoais: esses
          fatos continuam sob controle do sistema.
        </p>
      </div>
    </fieldset>

    <!-- Checkbox permanece nativo porque não há primitivo compartilhado de seleção binária. -->
    <label class="flex items-center gap-2 text-sm">
      <input
        v-model="isActive"
        type="checkbox"
        class="size-4 rounded border-border"
      />
      Ativo
    </label>

    <div class="flex items-center justify-end gap-2">
      <UiButton type="button" variant="outline" @click="emit('cancel')">
        Cancelar
      </UiButton>
      <UiButton type="submit" :disabled="!canSubmit">
        {{ template ? "Salvar" : "Criar modelo" }}
      </UiButton>
    </div>
  </form>
</template>
