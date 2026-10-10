<script setup lang="ts">
// Ver o anúncio do tamanho que ele vai ter, no lugar onde ele vai estar.
//
// A prévia pequena responde "o texto está certo?". Esta responde "o enquadramento está
// certo?" — e essa pergunta só tem resposta em tamanho real: a foto quadrada que corta a
// cabeça do pão no Story, a legenda que some sob a dobra do Feed, o balão de conversa que
// chega curto demais. Ela existe nos DOIS lugares onde a resposta muda alguma coisa: na
// edição, onde ainda dá para mexer, e na confirmação, onde é a última chance de olhar.
//
// ⚠️ Nada é buscado aqui. Os retratos chegam prontos de quem abre, para que abrir (ou não
// abrir) esta sobreposição jamais entre no caminho de quem só quer confirmar.
import type { SimulatedScene } from "~/presentation/simulatedPreview";

const props = withDefaults(
  defineProps<{
    scenes: SimulatedScene[];
    /** O nome que aparece como autor da postagem e como contato da conversa. */
    shopName?: string;
    /** Ajuste de posição do botão do olho no cabeçalho que o chama. A raiz é o
     *  `NuxtModal`, que não é um elemento: a classe precisa chegar ao botão. */
    triggerClass?: string;
  }>(),
  { shopName: "Nelson Boulangerie", triggerClass: "" },
);

const open = ref(false);
const activeKey = ref(props.scenes[0]?.key || "");
/** A hora do retrato é congelada na abertura: um relógio correndo dentro de uma prévia
 *  redesenharia a tela debaixo de quem está conferindo. */
const shownAt = ref("");

const scene = computed(
  () =>
    props.scenes.find((candidate) => candidate.key === activeKey.value) ||
    props.scenes[0] ||
    null,
);

watch(open, (isOpen) => {
  if (!isOpen) return;
  if (!props.scenes.some((candidate) => candidate.key === activeKey.value))
    activeKey.value = props.scenes[0]?.key || "";
  shownAt.value = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
});

/** Uma explicação por formato, dita pelo verbo do formato: postagem se publica,
 *  mensagem se envia. */
const SCENE_NOTES: Record<SimulatedScene["kind"], string> = {
  story:
    "O Story publica a imagem vertical acima, e ela fica pública por 24 horas. O texto do rascunho acompanha o comprovante desta decisão; sobre a imagem aparece só o que já estiver na arte.",
  feed: "O Feed publica a foto, o texto e as hashtags, nesta ordem, no mural público.",
  google_update:
    "O post sai no perfil do estabelecimento, para quem procurar a padaria no Google. O Google recorta a foto para caber no cartão: o que estiver perto das bordas pode sumir, então não ponha texto dentro da imagem.",
  whatsapp_message:
    "A mensagem chega assim na conversa de cada pessoa elegível, uma por pessoa. Mensagem entregue fica com quem recebeu.",
};

/** As abas: uma por formato, com o nome do formato e do lugar. */
const sceneTabs = computed(() =>
  props.scenes.map((candidate) => ({ label: candidate.label, value: candidate.key })),
);

const note = computed(() => (scene.value ? SCENE_NOTES[scene.value.kind] : ""));
</script>

<template>
  <NuxtModal
    v-if="scenes.length"
    v-model:open="open"
    fullscreen
    title="Prévia em tamanho real"
    :description="scene ? `${scene.label}, do jeito que a pessoa vai ver.` : ''"
  >
    <NuxtButton
      color="neutral"
      variant="ghost"
      square
      icon="i-lucide-eye"
      :class="triggerClass"
      data-testid="open-simulated-preview"
      aria-label="Ver a prévia em tamanho real"
    />

    <template #body>
      <div class="flex h-full min-h-0 flex-col gap-3" data-testid="simulated-preview">
        <!-- Um botão por FORMATO. Instagram e Facebook com o mesmo Feed são um retrato
             só; Story e Feed do mesmo Instagram são dois. -->
        <NuxtTabs
          v-if="scenes.length > 1"
          v-model="activeKey"
          :items="sceneTabs"
          :content="false"
          variant="pill"
          aria-label="Formato da prévia"
        />

        <div
          v-if="scene"
          class="flex min-h-0 flex-1 items-center justify-center overflow-y-auto"
          role="tabpanel"
          :aria-label="scene.label"
          :data-scene-kind="scene.kind"
        >
          <!-- STORY: vertical, tela cheia, barra de progresso e o gesto de voltar. -->
          <div
            v-if="scene.kind === 'story'"
            class="relative my-2 aspect-[9/16] h-full max-h-full overflow-hidden rounded-2xl bg-neutral-950 text-white"
          >
            <img
              v-if="scene.imageUrl"
              :src="scene.imageUrl"
              :alt="`Imagem vertical de ${scene.platformsLabel}`"
              class="size-full object-cover"
            />
            <div
              v-else
              class="grid size-full place-items-center gap-2 text-center text-white/70"
            >
              <div>
                <Icon name="lucide:image-off" class="mx-auto size-8" />
                <p class="mt-2 px-6 text-sm">
                  O Story publica sem foto nesta versão.
                </p>
              </div>
            </div>

            <div class="absolute inset-x-3 top-3 flex gap-1">
              <span
                v-for="segment in 3"
                :key="segment"
                class="h-0.5 flex-1 rounded-full"
                :class="segment === 1 ? 'bg-white' : 'bg-white/40'"
              />
            </div>
            <div
              class="absolute inset-x-3 top-6 flex items-center gap-2 pt-1 text-xs"
            >
              <!-- O chevron é o gesto de voltar do Story e fecha a prévia de verdade:
                   um controle desenhado que não faz nada ensinaria a tela a mentir. -->
              <NuxtButton
                color="neutral"
                variant="ghost"
                square
                icon="i-lucide-chevron-left"
                class="text-white"
                aria-label="Fechar a prévia"
                @click="open = false"
              />
              <span
                class="grid size-7 place-items-center rounded-full bg-white/25 text-xs font-semibold"
                aria-hidden="true"
              >
                {{ shopName.slice(0, 1) }}
              </span>
              <span class="font-semibold">{{ shopName }}</span>
              <span class="text-white/70">agora</span>
            </div>
          </div>

          <!-- FEED: o cartão do mural, com foto, texto e hashtags. -->
          <div
            v-else-if="scene.kind === 'feed'"
            class="my-4 w-full max-w-sm overflow-hidden rounded-xl border border-border bg-background shadow-sm"
          >
            <div class="flex items-center gap-2 px-3 py-2.5">
              <span
                class="grid size-8 place-items-center rounded-full bg-muted text-xs font-semibold"
                aria-hidden="true"
                >{{ shopName.slice(0, 1) }}</span
              >
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold">{{ shopName }}</p>
                <p class="text-xs text-muted-foreground">Agora</p>
              </div>
            </div>
            <img
              v-if="scene.imageUrl"
              :src="scene.imageUrl"
              :alt="`Imagem do anúncio em ${scene.platformsLabel}`"
              class="aspect-square w-full object-cover"
            />
            <div
              v-else
              class="grid aspect-square w-full place-items-center bg-muted/60 text-muted-foreground"
            >
              <div class="text-center">
                <Icon name="lucide:image-off" class="mx-auto size-7" />
                <p class="mt-2 px-6 text-xs">
                  O Feed publica sem foto nesta versão.
                </p>
              </div>
            </div>
            <div class="flex gap-3 px-3 pt-2.5 text-muted-foreground" aria-hidden="true">
              <Icon name="lucide:heart" class="size-5" />
              <Icon name="lucide:message-circle" class="size-5" />
              <Icon name="lucide:send" class="size-5" />
            </div>
            <div class="px-3 pt-2 pb-3 text-sm">
              <p class="whitespace-pre-line">
                <span class="font-semibold">{{ shopName }}</span>
                {{ scene.body }}
              </p>
              <p
                v-if="scene.hashtags.length"
                class="mt-1 break-words text-primary"
              >
                {{ scene.hashtags.join(" ") }}
              </p>
              <p
                v-if="scene.link"
                class="mt-1 break-all text-xs text-muted-foreground"
              >
                {{ scene.link }}
              </p>
            </div>
          </div>

          <!-- ATUALIZAÇÃO DO GOOGLE: o cartão de novidade do perfil do estabelecimento. -->
          <div
            v-else-if="scene.kind === 'google_update'"
            class="my-4 w-full max-w-sm overflow-hidden rounded-xl border border-border bg-background shadow-sm"
          >
            <div class="flex items-center gap-2 px-4 pt-4">
              <span
                class="grid size-8 place-items-center rounded-full bg-muted"
                aria-hidden="true"
              >
                <Icon name="lucide:map-pin" class="size-4" />
              </span>
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold">{{ shopName }}</p>
                <p class="text-xs text-muted-foreground">
                  {{ scene.google?.postTypeLabel || "Atualização" }} · agora
                </p>
              </div>
            </div>
            <img
              v-if="scene.imageUrl"
              :src="scene.imageUrl"
              :alt="`Imagem da atualização do Google`"
              class="mt-3 aspect-[4/3] w-full object-cover"
            />
            <div class="px-4 pt-3 pb-4 text-sm">
              <p v-if="scene.google?.title" class="font-semibold">
                {{ scene.google.title }}
              </p>
              <p v-if="scene.google?.period" class="text-xs text-muted-foreground">
                {{ scene.google.period }}
              </p>
              <p class="whitespace-pre-line" :class="scene.google?.title ? 'mt-1' : ''">
                {{ scene.body }}
              </p>
              <p
                v-if="scene.hashtags.length"
                class="mt-1 break-words text-xs text-muted-foreground"
              >
                {{ scene.hashtags.join(" ") }}
              </p>
              <!-- Botão desenhado: é o que o Google mostra no cartão, e aqui é retrato,
                   não controle. Por isso é um span. ⚠️ Só o botão ESCOLHIDO: até
                   25/09/2026 este retrato mostrava "Saiba mais" em todo post, com ou
                   sem botão. -->
              <span
                v-if="scene.google?.buttonLabel"
                class="mt-3 inline-flex min-h-9 items-center rounded-full border border-border px-4 text-sm font-medium text-primary"
              >
                {{ scene.google.buttonLabel }}
              </span>
            </div>
          </div>

          <!-- MENSAGEM NO WHATSAPP: balão numa conversa, sobre o fundo da conversa, com
               a hora. Vem da padaria, então chega pela esquerda, como toda mensagem
               recebida. Mensagem não é postagem e não pode ser retratada como uma. -->
          <div
            v-else
            class="my-2 flex h-full max-h-full w-full max-w-sm flex-col overflow-hidden rounded-xl border border-border shadow-sm"
          >
            <div
              class="flex items-center gap-2 bg-muted px-3 py-2.5 text-foreground"
            >
              <Icon
                name="lucide:chevron-left"
                class="size-4 text-muted-foreground"
                aria-hidden="true"
              />
              <span
                class="grid size-8 place-items-center rounded-full bg-background text-xs font-semibold"
                aria-hidden="true"
                >{{ shopName.slice(0, 1) }}</span
              >
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold">{{ shopName }}</p>
                <p class="text-xs text-muted-foreground">on-line</p>
              </div>
            </div>
            <!-- O fundo da conversa. Sem ele o balão vira um cartão, e cartão é mural:
                 o retrato diria "postagem" onde a consequência é "mensagem". -->
            <div
              class="flex min-h-56 flex-1 flex-col justify-end gap-2 bg-muted px-3 py-3"
              :style="{
                backgroundImage:
                  'radial-gradient(color-mix(in oklch, var(--foreground), transparent 85%) 1.5px, transparent 1.5px)',
                backgroundSize: '16px 16px',
              }"
            >
              <div
                class="max-w-[85%] overflow-hidden rounded-lg rounded-tl-none bg-background shadow-sm"
              >
                <img
                  v-if="scene.imageUrl"
                  :src="scene.imageUrl"
                  :alt="`Imagem da mensagem`"
                  class="h-36 w-full object-cover"
                />
                <div class="px-3 py-2">
                  <p class="whitespace-pre-line text-sm">{{ scene.body }}</p>
                  <p
                    v-if="scene.link"
                    class="mt-1 break-all text-xs text-primary"
                  >
                    {{ scene.link }}
                  </p>
                  <p class="mt-1 text-right text-xs text-muted-foreground">
                    {{ shownAt }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <p
          v-if="note"
          class="border-t border-border pt-3 text-xs text-muted-foreground"
        >
          {{ note }}
        </p>
      </div>
    </template>
  </NuxtModal>
</template>
