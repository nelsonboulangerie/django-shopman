<script setup lang="ts">
// O texto que vai para o cliente, escrito aqui.
//
// Apresentacional: o pai é dono do fetch e da escrita. O vocabulário de variáveis vem do
// backend (`options.variables`), nunca hardcoded — variável nova no domínio aparece aqui
// sem deploy de front, e a tela nunca oferece uma que o resolvedor não conhece.
import type {
  AnnouncementTemplate,
  MarketingPlatformCapability,
} from "~/types/campaign";
import PlatformCompositionEditor from "~/components/PlatformCompositionEditor.vue";
import { useMarketingDraft } from "~/composables/useMarketingDraft";
import type { MarketingDraftPayload } from "~/utils/marketingDraft";
import { marketingVariableLabel } from "~/presentation/marketingVariables";
import {
  googleBusinessEdits,
  googleBusinessOptions,
} from "~/presentation/googleBusinessPost";

const props = defineProps<{
  template: AnnouncementTemplate | null; // null = criando
  variables: string[];
  deliveryCapabilities?: MarketingPlatformCapability[];
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
const customImageUrl = ref("");

const platformCapabilities = computed(() => props.deliveryCapabilities ?? []);
const knownPlatforms = computed(() =>
  platformCapabilities.value.map((capability) => capability.platform),
);
const publicationCapabilities = computed(() =>
  platformCapabilities.value.filter(
    (capability) => capability.delivery_kind === "publication",
  ),
);
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
  platform_variants: "Composição por plataforma",
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
  for (const platform of knownPlatforms.value) {
    const value = variants[platform]?.image_url;
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function compositionFor(platform: string): Record<string, unknown> {
  return platformVariants.value[platform] || {};
}

function updateComposition(
  platform: string,
  composition: Record<string, unknown>,
) {
  platformVariants.value = {
    ...platformVariants.value,
    [platform]: composition,
  };
}

function selectedFormat(capability: MarketingPlatformCapability): string {
  const variant = compositionFor(capability.platform);
  const legacy = String(variant.post_type || "").toLowerCase();
  const requested = String(
    variant.publication_format ||
      ({ stories: "story", story: "story" }[legacy] ?? legacy) ||
      capability.default_format,
  ).toLowerCase();
  return capability.formats.some((format) => format.ref === requested)
    ? requested
    : capability.default_format;
}

const instagramNeedsMedia = computed(() => {
  const capability = platformCapabilities.value.find(
    (item) => item.platform === "instagram",
  );
  if (!capability) return false;
  return Boolean(
    capability.formats.find(
      (format) => format.ref === selectedFormat(capability),
    )?.media_required,
  );
});

function publicationVariants(): Record<string, Record<string, unknown>> {
  const variants = cloneVariants(platformVariants.value);
  Reflect.deleteProperty(variants as Record<string, unknown>, "image_url");
  for (const capability of publicationCapabilities.value) {
    const variant = { ...(variants[capability.platform] || {}) };
    const acceptsFormat = capability.formats.some((format) =>
      format.provider_fields.includes("publication_format"),
    );
    if (acceptsFormat)
      variant.publication_format = selectedFormat(capability);
    Reflect.deleteProperty(variant, "post_type");
    variants[capability.platform] = variant;
  }
  if (knownPlatforms.value.includes("google_business")) {
    const google = { ...(variants.google_business || {}) };
    for (const key of [
      "publication_format",
      "call_to_action",
      "event_title",
      "event_start",
      "event_end",
      "offer_terms",
    ]) {
      Reflect.deleteProperty(google, key);
    }
    Object.assign(
      google,
      googleBusinessEdits(
        googleBusinessOptions(variants.google_business || undefined),
      ),
    );
    variants.google_business = google;
  }
  for (const platform of knownPlatforms.value) {
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
    customImageUrl.value = imageFromVariants(platformVariants.value);
  },
  { immediate: true },
);

const googleReady = computed(() => {
  if (!knownPlatforms.value.includes("google_business")) return true;
  const options = googleBusinessOptions(
    platformVariants.value.google_business,
  );
  if (options.publication_format !== "event") return true;
  return Boolean(
    options.event_title.trim() &&
    options.event_start &&
    options.event_end &&
    options.event_end > options.event_start,
  );
});
const canSubmit = computed(
  () =>
    !props.busy &&
    name.value.trim().length > 0 &&
    body.value.trim().length > 0 &&
    platformCapabilities.value.length > 0 &&
    googleReady.value &&
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
        v-else-if="imageSource === 'none' && instagramNeedsMedia"
        class="mt-2 text-xs text-warning"
      >
        Campanhas que incluírem Instagram ficarão bloqueadas: o formato
        escolhido exige uma imagem.
      </p>
      <p
        v-else-if="imageSource === 'product' && instagramNeedsMedia"
        class="mt-2 text-xs text-muted-foreground"
      >
        Usa a foto do produto, em JPEG. Produto sem foto não dá para aprovar.
      </p>
    </div>

    <section class="space-y-3" aria-labelledby="template-compositions-title">
      <div>
        <h3 id="template-compositions-title" class="text-sm font-semibold">
          Composição por destino
        </h3>
        <p class="mt-1 text-xs text-muted-foreground">
          O texto acima é comum. Abra exceções somente quando a plataforma
          realmente precisar; formatos e opções vêm da capacidade executável.
        </p>
      </div>
      <p
        v-if="!platformCapabilities.length"
        class="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive"
        role="alert"
      >
        Não foi possível carregar os formatos que o Shopman consegue publicar.
        Atualize a tela; este modelo não será salvo no escuro.
      </p>
      <PlatformCompositionEditor
        v-for="capability in platformCapabilities"
        :key="capability.platform"
        :model-value="compositionFor(capability.platform)"
        :capability="capability"
        :base-body="body"
        :id-prefix="`tpl-${capability.platform}`"
        @update:model-value="updateComposition(capability.platform, $event)"
      />
    </section>

    <!-- Two server-side gates plus the credential decide availability. -->
    <fieldset
      v-if="aiAvailable"
      class="rounded-lg border border-border bg-card p-4"
    >
      <legend class="px-1 text-xs font-medium text-muted-foreground">
        Sugestão de texto
      </legend>
      <UiCheckbox
        v-model="useAi"
        label="Oferecer “Sugerir texto” durante a revisão"
        description="A sugestão aparece ao lado do texto e só entra no rascunho se alguém escolher usar. Nunca publica sozinha."
      />
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
          Não escreva preço, validade, estoque nem link: o sistema põe os
          atuais.
        </p>
      </div>
    </fieldset>

    <UiCheckbox v-model="isActive" label="Ativo" />

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
