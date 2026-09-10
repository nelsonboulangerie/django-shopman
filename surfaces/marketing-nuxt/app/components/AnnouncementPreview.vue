<script setup lang="ts">
// Preview fiel: uma resposta batch usa um único snapshot factual para todos os canais.
// Epoch + AbortController impedem que uma resposta antiga substitua o texto mais recente.
const props = defineProps<{
  body: string;
  platforms: string[];
  platformContent?: Record<string, Record<string, unknown>>;
  promotionRef?: string;
  useAi?: boolean;
  whatsappTemplate?: string;
  platformLabels: Record<string, string>;
}>();

type Scalar = string | number | boolean | null;

type ResolvedArtifact = {
  platform: string;
  body: string;
  hashtags: string[];
  link: string;
  image_url: string;
  provider_fields: Record<string, Scalar>;
  content_version: number;
  facts_as_of: string;
  facts_hash: string;
  flow_ref?: string;
  flow_version?: number;
  flow_catalog_hash?: string;
};

type FlowPreview = {
  configured: boolean;
  name: string;
  version: number;
  catalog_as_of: string;
};

type PreviewBatch = {
  sku: string;
  sample: boolean;
  product_name: string;
  fields: Record<string, string>;
  ai_writes: boolean;
  facts: {
    schema_version: number;
    as_of: string;
    fresh_until: string;
    source_hash: string;
    sku: string;
    promotion_ref: string;
    referenced_variables: string[];
    variables: Record<string, string>;
    product: Record<string, Scalar>;
    price: Record<string, Scalar>;
    availability: Record<string, Scalar>;
    promotion: Record<string, Scalar>;
    link: Record<string, Scalar>;
  };
  previews: Record<
    string,
    {
      artifact: ResolvedArtifact;
      artifact_hash: string;
      flow?: FlowPreview;
    }
  >;
};

type PreviewProblem = {
  detail: string;
  fieldDetail: string;
  retryable: boolean;
};

const preview = ref<PreviewBatch | null>(null);
const problem = ref<PreviewProblem | null>(null);
const pending = ref(false);
const activePlatform = ref("");

let timer: ReturnType<typeof setTimeout> | null = null;
let controller: AbortController | null = null;
let epoch = 0;

watch(
  () => [
    props.body,
    props.promotionRef || "",
    props.useAi ? "1" : "0",
    props.platforms.join("\u001f"),
    JSON.stringify(props.platformContent || {}),
  ],
  scheduleLoad,
  { immediate: true },
);

onBeforeUnmount(() => {
  epoch += 1;
  if (timer) clearTimeout(timer);
  controller?.abort();
});

function scheduleLoad() {
  epoch += 1;
  const requestEpoch = epoch;
  if (timer) clearTimeout(timer);
  controller?.abort();
  controller = null;
  preview.value = null;
  problem.value = null;

  const selected = normalizedPlatforms();
  if (!props.body.trim() || selected.length === 0) {
    pending.value = false;
    activePlatform.value = selected[0] || "";
    return;
  }
  if (!selected.includes(activePlatform.value))
    activePlatform.value = selected[0] || "";
  pending.value = true;
  timer = setTimeout(() => void load(requestEpoch), 400);
}

function retry() {
  epoch += 1;
  if (timer) clearTimeout(timer);
  controller?.abort();
  preview.value = null;
  problem.value = null;
  pending.value = true;
  void load(epoch);
}

async function load(requestEpoch: number) {
  timer = null;
  const requestController = new AbortController();
  controller = requestController;
  try {
    const result = await $fetch<PreviewBatch>(
      "/api/v1/backstage/marketing/preview/",
      {
        method: "POST",
        signal: requestController.signal,
        body: {
          body: props.body,
          platforms: normalizedPlatforms(),
          platform_content: props.platformContent || {},
          promotion_ref: props.promotionRef || "",
          use_ai: props.useAi,
        },
      },
    );
    if (requestEpoch !== epoch) return;
    preview.value = result;
    const available = Object.keys(result.previews || {});
    if (!available.includes(activePlatform.value))
      activePlatform.value = available[0] || "";
  } catch (error: unknown) {
    if (requestEpoch !== epoch || requestController.signal.aborted) return;
    flagMarketingSessionError(error);
    problem.value = previewProblem(error);
  } finally {
    if (requestEpoch === epoch) pending.value = false;
    if (controller === requestController) controller = null;
  }
}

function normalizedPlatforms() {
  return [
    ...new Set(props.platforms.map((value) => value.trim()).filter(Boolean)),
  ];
}

function previewProblem(error: unknown): PreviewProblem {
  const failure = error as {
    data?: Record<string, unknown>;
    response?: { _data?: Record<string, unknown> };
  };
  const data = failure?.data || failure?.response?._data || {};
  const rawFields = data.field_errors;
  let fieldDetail = "";
  if (rawFields && typeof rawFields === "object") {
    const first = Object.values(rawFields)[0];
    if (Array.isArray(first)) fieldDetail = String(first[0] || "");
    else if (first) fieldDetail = String(first);
  }
  return {
    detail:
      typeof data.detail === "string"
        ? data.detail
        : "Não foi possível atualizar a prévia agora.",
    fieldDetail,
    retryable: data.retryable === true,
  };
}

const selected = computed(
  () => preview.value?.previews[activePlatform.value] || null,
);
const artifact = computed(() => selected.value?.artifact || null);
const platformLabel = computed(
  () => props.platformLabels[activePlatform.value] || activePlatform.value,
);
const isWhatsapp = computed(() => activePlatform.value === "whatsapp");
const linkIsInBody = computed(
  () =>
    !!artifact.value?.link && artifact.value.body.includes(artifact.value.link),
);
const emptyFields = computed(() =>
  Object.entries(preview.value?.fields || {})
    .filter(
      ([key, value]) =>
        preview.value?.facts.referenced_variables.includes(key) && !value,
    )
    .map(([key]) => key),
);
const factTime = computed(() => {
  const raw = preview.value?.facts.as_of;
  if (!raw) return "";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
});
const shortHash = computed(
  () => selected.value?.artifact_hash.slice(0, 8) || "",
);
</script>

<template>
  <aside
    class="rounded-lg border border-border bg-muted/30 p-3"
    :aria-busy="pending"
    aria-labelledby="announcement-preview-title"
  >
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
      <p
        id="announcement-preview-title"
        class="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Prévia fiel
      </p>
      <Icon
        v-if="pending"
        name="lucide:loader-circle"
        class="size-3 animate-spin text-muted-foreground motion-reduce:animate-none"
      />
      <span
        v-if="preview?.sample"
        class="ml-auto text-xs text-muted-foreground"
        :title="preview.sku"
      >
        Exemplo com {{ preview.product_name || preview.sku }}
      </span>
    </div>

    <p
      v-if="pending"
      data-testid="preview-status"
      class="mt-2 text-xs text-muted-foreground"
      role="status"
    >
      Atualizando todas as plataformas…
    </p>

    <p
      v-else-if="!body.trim() || platforms.length === 0"
      class="mt-2 text-xs text-muted-foreground"
    >
      {{
        body.trim()
          ? "Escolha uma plataforma para gerar a prévia."
          : "Escreva o texto para ver como fica."
      }}
    </p>

    <div
      v-else-if="problem"
      data-testid="preview-error"
      class="mt-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm"
      role="alert"
    >
      <p class="font-medium">A prévia não foi atualizada</p>
      <p class="mt-1 text-xs text-muted-foreground">{{ problem.detail }}</p>
      <p v-if="problem.fieldDetail" class="mt-1 text-xs text-muted-foreground">
        {{ problem.fieldDetail }}
      </p>
      <button
        type="button"
        class="mt-2 inline-flex min-h-11 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium"
        @click="retry"
      >
        <Icon name="lucide:refresh-cw" class="size-4" />
        {{ problem.retryable ? "Tentar novamente" : "Revalidar prévia" }}
      </button>
    </div>

    <template v-else-if="preview && artifact">
      <div
        class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground"
      >
        <span v-if="factTime" :title="preview.facts.as_of"
          >Dados conferidos às {{ factTime }}</span
        >
        <span v-if="shortHash" :title="selected?.artifact_hash"
          >Versão {{ shortHash }}</span
        >
      </div>

      <div
        v-if="Object.keys(preview.previews).length > 1"
        class="mt-3 flex flex-wrap gap-1.5"
        role="tablist"
        aria-label="Plataforma da prévia"
      >
        <button
          v-for="(_, platform) in preview.previews"
          :key="platform"
          type="button"
          role="tab"
          class="min-h-11 rounded-md border px-3 text-sm font-medium"
          :class="
            platform === activePlatform
              ? 'border-primary bg-primary/10 text-foreground'
              : 'border-border bg-background text-muted-foreground'
          "
          :aria-selected="platform === activePlatform"
          :data-platform="platform"
          @click="activePlatform = platform"
        >
          {{ platformLabels[platform] || platform }}
        </button>
      </div>

      <p
        v-if="preview.ai_writes"
        class="mt-3 flex items-start gap-1.5 rounded-md bg-background px-2 py-1.5 text-xs text-muted-foreground"
      >
        <Icon name="lucide:sparkles" class="mt-0.5 size-3.5 shrink-0" />
        A IA ainda pode sugerir outro texto; qualquer sugestão precisa de nova
        prévia e revisão.
      </p>

      <div v-if="isWhatsapp" class="mt-3" role="tabpanel">
        <p class="mb-1 text-xs font-medium text-muted-foreground">
          {{ platformLabel }}
        </p>
        <div
          class="max-w-[18rem] overflow-hidden rounded-lg rounded-tl-none bg-background shadow-sm"
        >
          <img
            v-if="artifact.image_url"
            :src="artifact.image_url"
            :alt="preview.product_name"
            class="h-32 w-full object-cover"
          />
          <div class="px-3 py-2">
            <p class="whitespace-pre-line text-sm">{{ artifact.body }}</p>
            <p
              v-if="artifact.link && !linkIsInBody"
              class="mt-1 break-all text-xs text-primary"
            >
              {{ artifact.link }}
            </p>
          </div>
        </div>
        <p v-if="whatsappTemplate" class="mt-1.5 text-xs text-muted-foreground">
          Modelo aprovado: {{ whatsappTemplate }}. Os campos técnicos exibidos
          pertencem à mesma versão do artefato.
        </p>
        <p v-if="selected?.flow" class="mt-1.5 text-xs text-muted-foreground">
          Fluxo conferido: {{ selected.flow.name }} · configuração v{{
            selected.flow.version
          }}. Esta é a versão selada para aprovação e envio.
        </p>
      </div>

      <div v-else class="mt-3" role="tabpanel">
        <p class="mb-1 text-xs font-medium text-muted-foreground">
          {{ platformLabel }}
        </p>
        <div
          class="max-w-[18rem] overflow-hidden rounded-lg border border-border bg-background"
        >
          <img
            v-if="artifact.image_url"
            :src="artifact.image_url"
            :alt="preview.product_name"
            class="aspect-square w-full object-cover"
          />
          <div class="px-3 py-2">
            <p class="whitespace-pre-line text-sm">{{ artifact.body }}</p>
            <p
              v-if="artifact.hashtags.length"
              class="mt-1 break-words text-xs text-primary"
            >
              {{ artifact.hashtags.map((tag) => `#${tag}`).join(" ") }}
            </p>
            <p
              v-if="artifact.link && !linkIsInBody"
              class="mt-1 break-all text-xs text-primary"
            >
              {{ artifact.link }}
            </p>
          </div>
        </div>
      </div>

      <p
        v-if="emptyFields.length"
        class="mt-3 flex items-start gap-1.5 rounded-md bg-amber-500/10 px-2 py-1.5 text-xs text-amber-700 dark:text-amber-400"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-3.5 shrink-0" />
        <span>
          Sem valor nesta amostra:
          <span class="font-mono">{{ emptyFields.join(", ") }}</span
          >. Campos por destinatário serão resolvidos apenas no boundary
          protegido.
        </span>
      </p>

      <p v-if="!artifact.image_url" class="mt-2 text-xs text-muted-foreground">
        Esta plataforma sairá sem imagem nesta versão.
      </p>
    </template>

    <div
      v-else-if="preview"
      class="mt-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-400"
      role="alert"
    >
      A resposta não trouxe a plataforma escolhida.
      <button type="button" class="ml-1 min-h-11 underline" @click="retry">
        Revalidar
      </button>
    </div>
  </aside>
</template>
