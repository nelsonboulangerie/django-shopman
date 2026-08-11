<script setup lang="ts">
// Como a mensagem vai ficar, antes de existir cliente.
//
// ⚠️ Existe porque até agora o gestor escrevia `{{product_name}}` e só descobria o resultado
// quando a mensagem chegava no celular de alguém. Variável com nome errado renderiza vazio em
// SILÊNCIO — foi assim que passaram um `customer_name` que ninguém mandava e uma foto em
// caminho relativo que a Meta não consegue baixar.
//
// A resolução é do servidor, pelo mesmo caminho do envio. Este componente só desenha.
import { platformsSummary } from "~/presentation/campaign";

const props = defineProps<{
  /** O texto do modelo, com as variáveis cruas. */
  body: string;
  /** Plataformas escolhidas na campanha — desenhamos só o que vai sair. */
  platforms: string[];
  promotionRef?: string;
  /** O modelo delega o texto à IA? A prévia diz isso em vez de fingir que sabe o resultado. */
  useAi?: boolean;
  /** Há template aprovado do WhatsApp escolhido? Muda o que o cliente lê. */
  whatsappTemplate?: string;
  /** Rótulos vindos do backend — a prévia não inventa nome de plataforma. */
  platformLabels: Record<string, string>;
}>();

type Preview = {
  sku: string;
  body: string;
  product_name: string;
  product_image_url: string;
  link: string;
  hashtags: string[];
  fields: Record<string, string>;
  ai_writes: boolean;
};

const preview = ref<Preview | null>(null);
const pending = ref(false);

// Debounce: a prévia acompanha a digitação, mas uma chamada por tecla é desperdício.
let timer: ReturnType<typeof setTimeout> | null = null;

watch(
  () => [props.body, props.promotionRef, props.useAi],
  () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(load, 400);
  },
  { immediate: true },
);

onBeforeUnmount(() => { if (timer) clearTimeout(timer); });

async function load() {
  pending.value = true;
  try {
    preview.value = await $fetch<Preview>("/api/v1/backstage/marketing/preview/", {
      method: "POST",
      body: { body: props.body, promotion_ref: props.promotionRef || "", use_ai: props.useAi },
    });
  } catch {
    // Prévia é conveniência: falhar aqui não pode atrapalhar quem está escrevendo.
    preview.value = null;
  } finally {
    pending.value = false;
  }
}

const showsWhatsapp = computed(() => props.platforms.includes("whatsapp"));
const publications = computed(() =>
  props.platforms.filter((p) => p !== "whatsapp"),
);

/** O corpo já traz o link (o modelo termina em `{{link}}`)? Então não repetimos embaixo:
 *  a prévia mostrando duas vezes ensinaria o gestor a caçar um bug que não existe. */
const linkIsInBody = computed(
  () => !!preview.value?.link && (preview.value?.body || "").includes(preview.value.link),
);

/** Variáveis que ficaram vazias — o achado que a prévia existe para entregar. */
const emptyFields = computed(() =>
  Object.entries(preview.value?.fields || {})
    .filter(([, value]) => !value)
    .map(([key]) => key),
);
</script>

<template>
  <aside class="rounded-lg border border-border bg-muted/30 p-3">
    <div class="flex items-center gap-2">
      <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Prévia</p>
      <Icon v-if="pending" name="lucide:loader-circle" class="size-3 animate-spin text-muted-foreground" />
      <span v-if="preview?.product_name" class="ml-auto truncate text-xs text-muted-foreground">
        com {{ preview.product_name }}
      </span>
    </div>

    <p v-if="!preview && !pending" class="mt-2 text-xs text-muted-foreground">
      Escreva o texto para ver como fica.
    </p>

    <template v-else-if="preview">
      <!-- A IA escreve no envio: prometer o texto final aqui seria invenção. -->
      <p
        v-if="preview.ai_writes"
        class="mt-2 flex items-start gap-1.5 rounded-md bg-background px-2 py-1.5 text-xs text-muted-foreground"
      >
        <Icon name="lucide:sparkles" class="mt-0.5 size-3.5 shrink-0" />
        A IA escreve o texto no envio. Abaixo está o formato de referência, com as variáveis
        resolvidas.
      </p>

      <!-- WhatsApp: bolha. Com template aprovado, o texto é o da Meta — dizer isso aqui
           evita o gestor ajustar uma frase que o cliente não vai ler. -->
      <div v-if="showsWhatsapp" class="mt-3">
        <p class="mb-1 text-xs font-medium text-muted-foreground">WhatsApp</p>
        <div class="max-w-[18rem] overflow-hidden rounded-lg rounded-tl-none bg-background shadow-sm">
          <img
            v-if="preview.product_image_url"
            :src="preview.product_image_url"
            :alt="preview.product_name"
            class="h-32 w-full object-cover"
          >
          <div class="px-3 py-2">
            <p class="whitespace-pre-line text-sm">{{ preview.body || "…" }}</p>
            <p
              v-if="preview.link && !linkIsInBody"
              class="mt-1 truncate text-xs text-primary"
            >{{ preview.link }}</p>
          </div>
        </div>
        <p v-if="whatsappTemplate" class="mt-1.5 text-xs text-muted-foreground">
          Há template aprovado escolhido: no WhatsApp o cliente lê o texto da Meta, e este
          modelo entra só com as variáveis abaixo.
        </p>
      </div>

      <!-- Publicação: uma peça, sem destinatário. -->
      <div v-if="publications.length" class="mt-3">
        <p class="mb-1 text-xs font-medium text-muted-foreground">
          {{ platformsSummary(publications, platformLabels) }}
        </p>
        <div class="max-w-[18rem] overflow-hidden rounded-lg border border-border bg-background">
          <img
            v-if="preview.product_image_url"
            :src="preview.product_image_url"
            :alt="preview.product_name"
            class="aspect-square w-full object-cover"
          >
          <div class="px-3 py-2">
            <p class="whitespace-pre-line text-sm">{{ preview.body || "…" }}</p>
            <p v-if="preview.hashtags.length" class="mt-1 text-xs text-primary">
              {{ preview.hashtags.map((tag) => `#${tag}`).join(" ") }}
            </p>
          </div>
        </div>
      </div>

      <!-- ⚠️ O achado que a prévia existe para entregar: variável que resolveu VAZIA. Sem
           isto, ela chega em branco no aparelho e ninguém sabe por quê. -->
      <p
        v-if="emptyFields.length"
        class="mt-3 flex items-start gap-1.5 rounded-md bg-amber-500/10 px-2 py-1.5 text-xs text-amber-700 dark:text-amber-400"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-3.5 shrink-0" />
        <span>
          Sem valor agora: <span class="font-mono">{{ emptyFields.join(", ") }}</span>.
          No envio real elas são preenchidas por destinatário, mas confira se o nome está certo.
        </span>
      </p>

      <p v-if="!preview.product_image_url" class="mt-2 text-xs text-muted-foreground">
        Este produto não tem foto. A publicação sai sem imagem.
      </p>
    </template>
  </aside>
</template>
