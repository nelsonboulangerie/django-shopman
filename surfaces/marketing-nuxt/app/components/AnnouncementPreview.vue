<script setup lang="ts">
// Preview fiel: uma resposta batch usa um único snapshot factual para todos os canais.
// Epoch + AbortController impedem que uma resposta antiga substitua o texto mais recente.
import { scenesFromDraftArtifacts } from "~/presentation/simulatedPreview";

const props = defineProps<{
  body: string;
  /** SKU da ocorrência real. Vazio usa somente a amostra do formulário. */
  sku?: string;
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
  code: string;
  title: string;
  detail: string;
  fieldDetail: string;
  retryable: boolean;
  repairHref: string;
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
    props.sku || "",
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
          sku: props.sku || "",
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
  const code = typeof data.code === "string" ? data.code : "";
  const isMediaProblem =
    code.startsWith("marketing_media_") || code === "instagram_media_required";
  const retryable = data.retryable === true;
  const rawFields = data.field_errors;
  let fieldDetail = "";
  if (rawFields && typeof rawFields === "object") {
    const first = Object.values(rawFields)[0];
    if (Array.isArray(first)) fieldDetail = String(first[0] || "");
    else if (first) fieldDetail = String(first);
  }
  return {
    code,
    title: isMediaProblem
      ? "Corrija a imagem para gerar a prévia"
      : retryable
        ? "Não foi possível atualizar a prévia agora"
        : "Revise os dados para gerar a prévia",
    detail:
      typeof data.detail === "string"
        ? data.detail
        : "Não foi possível atualizar a prévia agora.",
    fieldDetail,
    retryable,
    repairHref: isMediaProblem ? "/templates" : "",
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
const publicationFormat = computed(() =>
  String(artifact.value?.provider_fields.publication_format || ""),
);
const isInstagramStory = computed(
  () =>
    activePlatform.value === "instagram" && publicationFormat.value === "story",
);
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

/** ⚠️ Fonte do retrato grande NESTA tela: o RASCUNHO corrente, já resolvido pelo
 *  servidor nesta mesma resposta. É o ponto — aqui o gestor está editando, e o que ele
 *  precisa ver em tamanho real é o efeito da edição que está fazendo agora. A caixa de
 *  confirmação faz o oposto, e por um motivo igualmente explícito: lá o retrato sai do
 *  corpo congelado do comando.
 *
 *  Nenhuma chamada a mais: os artefatos já estão aqui. Abrir a prévia grande não pede
 *  nada ao servidor. */
const simulatedScenes = computed(() =>
  preview.value
    ? scenesFromDraftArtifacts({
        previews: preview.value.previews,
        platformLabels: props.platformLabels,
      })
    : [],
);
</script>

<template>
  <aside
    class="rounded-lg border border-border bg-muted/30 p-3"
    :aria-busy="pending"
    aria-labelledby="announcement-preview-title"
  >
    <!-- ⚠️ Cabeçalho, corpo e RODAPÉ. O que o gestor veio ver é o conteúdo; o resto é
         procedência (de qual modelo saiu, de que produto é o exemplo, de quando são os
         dados) e procedência se lê depois, não antes. Antes disso tudo dividia a
         primeira linha com o título, e o botão que abre o tamanho real ficava no meio
         da frase — ele é a ação do cartão e mora no canto, onde a mão procura. -->
    <div class="flex items-center gap-2">
      <p
        id="announcement-preview-title"
        class="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Prévia
      </p>
      <Icon
        v-if="pending"
        name="lucide:loader-circle"
        class="size-3 animate-spin text-muted-foreground motion-reduce:animate-none"
      />
      <!-- O olho abre o mesmo conteúdo em tamanho real, no lugar onde a pessoa vai
           ver. Aqui, enquanto ainda dá para mexer: descobrir um enquadramento ruim só
           na hora do disparo custa voltar uma tela. -->
      <!-- A margem negativa deixa o alvo de toque com os 44px inteiros sem engordar a
           linha do cabeçalho: no menor mobile, cada 20px a mais empurra a decisão para
           fora da dobra. -->
      <AnnouncementSimulatedPreview
        :scenes="simulatedScenes"
        trigger-class="-my-3 ml-auto"
      />
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
      <p class="font-medium">{{ problem.title }}</p>
      <p class="mt-1 text-xs text-muted-foreground">{{ problem.detail }}</p>
      <p v-if="problem.fieldDetail" class="mt-1 text-xs text-muted-foreground">
        {{ problem.fieldDetail }}
      </p>
      <UiButton
        v-if="problem.retryable"
        type="button"
        variant="outline"
        class="mt-2"
        @click="retry"
      >
        <Icon name="lucide:refresh-cw" class="size-4" />
        Tentar novamente
      </UiButton>
      <UiButton
        v-else-if="problem.repairHref"
        :to="problem.repairHref"
        variant="outline"
        class="mt-2"
      >
        <Icon name="lucide:image" class="size-4" />
        Corrigir imagem nos modelos
      </UiButton>
    </div>

    <template v-else-if="preview && artifact">
      <div
        v-if="Object.keys(preview.previews).length > 1"
        class="mt-3 flex flex-wrap gap-1.5"
        role="tablist"
        aria-label="Plataforma da prévia"
      >
        <!-- Abas permanecem nativas para preservar role=tab, aria-selected e navegação semântica. -->
        <button
          v-for="(_, platform) in preview.previews"
          :key="platform"
          type="button"
          role="tab"
          class="min-h-11 rounded-md border px-3 text-sm font-medium"
          :class="
            platform === activePlatform
              ? 'border-primary bg-primary/10 text-foreground'
              : 'border-border bg-card text-muted-foreground'
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
        class="mt-3 flex items-start gap-1.5 rounded-md bg-card px-2 py-1.5 text-xs text-muted-foreground"
      >
        <Icon name="lucide:sparkles" class="mt-0.5 size-3.5 shrink-0" />
        Se você usar uma sugestão da IA, a prévia refaz.
      </p>

      <div v-if="isWhatsapp" class="mt-3" role="tabpanel">
        <p class="mb-1 text-xs font-medium text-muted-foreground">
          {{ platformLabel }}
        </p>
        <div
          class="max-w-[18rem] overflow-hidden rounded-lg rounded-tl-none bg-card shadow-sm"
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
      </div>

      <div v-else-if="isInstagramStory" class="mt-3" role="tabpanel">
        <p class="mb-1 text-xs font-medium text-muted-foreground">
          Story do Instagram
        </p>
        <div
          class="aspect-[9/16] w-full max-w-[14rem] overflow-hidden rounded-xl border border-border bg-card"
        >
          <img
            :src="artifact.image_url"
            :alt="preview.product_name"
            class="size-full object-cover"
          />
        </div>
        <div
          class="mt-2 rounded-md bg-card px-3 py-2 text-xs text-muted-foreground"
        >
          <p class="font-medium text-foreground">O que será publicado</p>
          <p>A imagem vertical acima, como Story público e efêmero.</p>
          <p class="mt-1">
            O texto do rascunho fica no comprovante desta decisão; ele não é
            inserido automaticamente sobre a imagem.
          </p>
        </div>
      </div>

      <div v-else class="mt-3" role="tabpanel">
        <p class="mb-1 text-xs font-medium text-muted-foreground">
          {{ platformLabel
          }}<template v-if="publicationFormat">
            ·
            {{
              publicationFormat === "feed" ? "Feed" : "Atualização padrão"
            }}</template
          >
        </p>
        <div
          class="max-w-[18rem] overflow-hidden rounded-lg border border-border bg-card"
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
        class="mt-3 flex items-start gap-1.5 rounded-md bg-warning/10 px-2 py-1.5 text-xs text-warning"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-3.5 shrink-0" />
        <span>
          Sem valor nesta amostra:
          <span class="font-mono">{{ emptyFields.join(", ") }}</span
          >. Aqui é um exemplo: cada pessoa recebe o nome dela.
        </span>
      </p>

      <!-- ⚠️ Uma frase só não servia aqui: "sairá sem imagem" valia para mensagem e
           para postagem ao mesmo tempo, e os dois atos são diferentes — mensagem se
           envia e não se apaga, postagem se publica e se apaga. A prévia já sabe em
           qual plataforma está (`isWhatsapp`), então diz o ato pelo nome. -->
      <p v-if="!artifact.image_url" class="mt-2 text-xs text-muted-foreground">
        {{
          isWhatsapp
            ? "A mensagem é enviada sem foto."
            : "A postagem é publicada sem foto."
        }}
      </p>

      <!-- RODAPÉ: procedência, toda junta e DEPOIS do conteúdo — de qual modelo saiu,
           de que produto é o exemplo, de quando são os dados. Espalhada (uma linha no
           cabeçalho, outra sob a bolha, outra no canto) ela disputava a atenção com o
           que o gestor veio ver, e nenhuma das três ficava fácil de achar.
           O hash do artefato continua fora da tela: ninguém confere oito dígitos
           hexadecimais no balcão. Ele vive no `title`, para quem precisa correlacionar
           com o comprovante. -->
      <dl
        v-if="whatsappTemplate || selected?.flow || preview.sample || factTime"
        class="mt-3 space-y-0.5 border-t border-border/60 pt-2 text-xs text-muted-foreground"
      >
        <div v-if="whatsappTemplate" class="flex gap-1">
          <dt>Modelo aprovado:</dt>
          <dd class="min-w-0 truncate" :title="whatsappTemplate">
            {{ whatsappTemplate }}
          </dd>
        </div>
        <div v-if="selected?.flow" class="flex gap-1">
          <dt>Fluxo do WhatsApp:</dt>
          <dd class="min-w-0 truncate">{{ selected.flow.name }}</dd>
        </div>
        <div v-if="preview.sample" class="flex gap-1">
          <dt>Exemplo com:</dt>
          <dd class="min-w-0 truncate" :title="preview.sku">
            {{ preview.product_name || preview.sku }}
          </dd>
        </div>
        <div v-if="factTime" class="flex gap-1">
          <dt>Dados conferidos às:</dt>
          <dd
            :title="`Dados de ${preview.facts.as_of}${shortHash ? ` · versão ${shortHash}` : ''}`"
          >
            {{ factTime }}
          </dd>
        </div>
      </dl>
    </template>

    <div
      v-else-if="preview"
      class="mt-2 rounded-md bg-warning/10 p-3 text-xs text-warning"
      role="alert"
    >
      A resposta não trouxe a plataforma escolhida.
      <UiButton type="button" variant="link" class="ml-1" @click="retry">
        Tentar de novo
      </UiButton>
    </div>
  </aside>
</template>
