<script setup lang="ts">
// Canais — venda (loja online, WhatsApp, iFood, PDV) e exibição (📺 menuboard na
// TV, 🛰 Google/Meta). Todo card tem a mesma estrutura: CABEÇALHO com o toggle
// "Ativo", CORPO com o estado, RODAPÉ com as ações. O toggle é o mesmo em todos:
// abre o modal de período + motivo + gerente (`ChannelSwitchDialog`).
// Nos feeds o operador também escolhe as coleções e a rotação de páginas da TV, e
// abre/prevê a saída. A ORDEM das coleções é global (reordenável no Catálogo).
import type {
  ChannelSwitchProjection,
  CollectionOptionProjection,
  FeedProjection,
} from "~/types/feeds";
import { IFOOD_CHANNEL_REF } from "~/presentation/ifoodStore";

const {
  readMetadata,
  realtime,
  board,
  pending,
  error,
  errorMsg,
  refresh,
  isBusy,
  switchChannel,
  setCollections,
  setRotation,
  setAutomatic,
} = useFeedBoard();
const catalogChannels = computed(() => board.value?.catalog_channels ?? []);
const feeds = computed<FeedProjection[]>(() => board.value?.feeds ?? []);
const allCollections = computed<CollectionOptionProjection[]>(
  () => board.value?.all_collections ?? [],
);
const loading = computed(() => pending.value && !board.value);
// O checklist vivo de cada canal (o que falta, e o botão que resolve).
const { healthOf } = useChannelHealth();

// O aviso da fila de Pedidos chega aqui com `?focus=<ref>`: o card daquele canal —
// onde mora o toggle — vai para a linha de foco assim que a leitura o traz.
const route = useRoute();
const focusKey = computed(() => {
  const wanted = typeof route.query.focus === "string" ? route.query.focus : "";
  const known = [...catalogChannels.value, ...feeds.value].some(
    (channel) => channel.ref === wanted,
  );
  return wanted && known ? wanted : null;
});
useNextFocus(focusKey);

// saída servida pelo Django (menuboard/feed), não pelo host do Gestor.
const runtimeConfig = useRuntimeConfig();
const djangoBase = runtimeConfig.public.djangoBaseUrl as string;
const outputHref = (sc: FeedProjection) => `${djangoBase}${sc.output_path}`;
// o Admin é porta humana e tem host próprio — não é a mesma base da saída.
const adminBase = runtimeConfig.public.adminBaseUrl as string;

// O toggle não liga nem desliga direto: abre o modal (período, motivo, gerente).
// O interruptor segue mostrando o estado do servidor até o gesto ser confirmado.
const switchRef = ref<string | null>(null);
const switchTarget = computed<ChannelSwitchProjection | null>(() => {
  if (!switchRef.value) return null;
  return (
    feeds.value.find((feed) => feed.ref === switchRef.value)?.switch ??
    catalogChannels.value.find((channel) => channel.ref === switchRef.value)
      ?.switch ??
    null
  );
});
function openSwitch(ref_: string) {
  switchRef.value = ref_;
}
const submitSwitch = (
  request: Parameters<typeof switchChannel>[1],
  approval?: Record<string, string>,
) => switchChannel(switchRef.value!, request, approval);
const switchColor = (sw: ChannelSwitchProjection | null | undefined) =>
  sw?.closed_by_shop ? "neutral" : "success";
const switchLabel = (
  name: string,
  sw: ChannelSwitchProjection | null | undefined,
) =>
  sw?.is_active ? `${name}: ligado. Desligar…` : `${name}: desligado. Ligar…`;

// Rascunhos pertencem ao feed e à pessoa (a página é remontada na troca de identidade).
const actionFor = (sc: FeedProjection, field: string) =>
  sc.actions.find((action) => action.ref === field);
const baseFor = (sc: FeedProjection, field: string) =>
  String(actionFor(sc, field)?.payload_schema.base_revision || "");
const editRef = ref<string | null>(null);
const collectionDrafts = ref<
  Record<string, { values: string[]; base: string }>
>({});
const draft = computed<string[]>({
  get: () =>
    editRef.value ? (collectionDrafts.value[editRef.value]?.values ?? []) : [],
  set: (values) => {
    if (editRef.value && collectionDrafts.value[editRef.value])
      collectionDrafts.value[editRef.value]!.values = [...values];
  },
});
const collectionOptions = computed(() =>
  allCollections.value.map((option) => ({
    value: option.ref,
    label: option.name,
    hint: `${option.product_count} ${option.product_count === 1 ? "produto" : "produtos"}`,
  })),
);
function openEdit(sc: FeedProjection) {
  collectionDrafts.value[sc.ref] ??= {
    values: sc.collections.map((c) => c.ref),
    base: baseFor(sc, "collections"),
  };
  editRef.value = sc.ref;
}
const collectionConflict = (sc: FeedProjection) =>
  !!collectionDrafts.value[sc.ref] &&
  collectionDrafts.value[sc.ref]!.base !== baseFor(sc, "collections");
function resolveCollections(sc: FeedProjection, keep: boolean) {
  collectionDrafts.value[sc.ref] = {
    values: keep ? [...draft.value] : sc.collections.map((c) => c.ref),
    base: baseFor(sc, "collections"),
  };
}
async function applyEdit(sc: FeedProjection) {
  if (collectionConflict(sc)) return;
  const ok = await setCollections(
    sc.ref,
    [...draft.value],
    collectionDrafts.value[sc.ref]?.base,
  );
  if (ok) {
    Reflect.deleteProperty(collectionDrafts.value, sc.ref);
    if (editRef.value === sc.ref) editRef.value = null;
  }
}

const rotationRef = ref<string | null>(null);
const rotationDrafts = ref<
  Record<string, { seconds: number; items: number; base: string }>
>({});
const draftSeconds = computed({
  get: () =>
    rotationRef.value
      ? (rotationDrafts.value[rotationRef.value]?.seconds ?? 0)
      : 0,
  set: (value: number) => {
    if (rotationRef.value && rotationDrafts.value[rotationRef.value])
      rotationDrafts.value[rotationRef.value]!.seconds = value;
  },
});
const draftItems = computed({
  get: () =>
    rotationRef.value
      ? (rotationDrafts.value[rotationRef.value]?.items ?? 0)
      : 0,
  set: (value: number) => {
    if (rotationRef.value && rotationDrafts.value[rotationRef.value])
      rotationDrafts.value[rotationRef.value]!.items = value;
  },
});
function openRotation(sc: FeedProjection) {
  rotationDrafts.value[sc.ref] ??= {
    seconds: sc.rotate_seconds,
    items: sc.items_per_page,
    base: baseFor(sc, "rotation"),
  };
  rotationRef.value = sc.ref;
}
const rotationConflict = (sc: FeedProjection) =>
  !!rotationDrafts.value[sc.ref] &&
  rotationDrafts.value[sc.ref]!.base !== baseFor(sc, "rotation");
function resolveRotation(sc: FeedProjection, keep: boolean) {
  rotationDrafts.value[sc.ref] = {
    seconds: keep ? draftSeconds.value : sc.rotate_seconds,
    items: keep ? draftItems.value : sc.items_per_page,
    base: baseFor(sc, "rotation"),
  };
}
async function applyRotation(sc: FeedProjection) {
  if (rotationConflict(sc)) return;
  const ok = await setRotation(
    sc.ref,
    Number(draftSeconds.value) || 0,
    Number(draftItems.value) || 0,
    rotationDrafts.value[sc.ref]?.base,
  );
  if (ok) {
    Reflect.deleteProperty(rotationDrafts.value, sc.ref);
    if (rotationRef.value === sc.ref) rotationRef.value = null;
  }
}

const automaticRef = ref<string | null>(null);
const automaticDrafts = ref<
  Record<string, { messages: [string, string]; base: string }>
>({});
const automaticMessages = computed<[string, string]>(() =>
  automaticRef.value
    ? (automaticDrafts.value[automaticRef.value]?.messages ?? ["", ""])
    : ["", ""],
);
const projectedAutomaticMessages = (sc: FeedProjection): [string, string] => [
  sc.automatic?.idle_messages[0] ?? "",
  sc.automatic?.idle_messages[1] ?? "",
];
function openAutomatic(sc: FeedProjection) {
  if (!sc.automatic) return;
  automaticDrafts.value[sc.ref] ??= {
    messages: projectedAutomaticMessages(sc),
    base: baseFor(sc, "automatic"),
  };
  automaticRef.value = sc.ref;
}
const automaticConflict = (sc: FeedProjection) =>
  !!automaticDrafts.value[sc.ref] &&
  automaticDrafts.value[sc.ref]!.base !== baseFor(sc, "automatic");
function resolveAutomatic(sc: FeedProjection, keep: boolean) {
  if (!sc.automatic) return;
  automaticDrafts.value[sc.ref] = {
    messages: keep
      ? ([...automaticMessages.value] as [string, string])
      : projectedAutomaticMessages(sc),
    base: baseFor(sc, "automatic"),
  };
}
async function applyAutomaticMessage(sc: FeedProjection) {
  if (!sc.automatic || automaticConflict(sc)) return;
  const messages = automaticMessages.value
    .map((message) => message.trim())
    .filter(Boolean);
  const ok = await setAutomatic(
    sc.ref,
    sc.automatic.enabled,
    messages,
    automaticDrafts.value[sc.ref]?.base,
  );
  if (ok) {
    Reflect.deleteProperty(automaticDrafts.value, sc.ref);
    if (automaticRef.value === sc.ref) automaticRef.value = null;
  }
}
async function applyAutomaticToggle(sc: FeedProjection, enabled: boolean) {
  if (!sc.automatic) return;
  await setAutomatic(
    sc.ref,
    enabled,
    sc.automatic.idle_messages,
    baseFor(sc, "automatic"),
  );
}
const hasDraft = computed(() =>
  feeds.value.some((sc) => {
    const collections = collectionDrafts.value[sc.ref];
    const rotation = rotationDrafts.value[sc.ref];
    const automatic = automaticDrafts.value[sc.ref];
    return (
      (collections &&
        JSON.stringify([...collections.values].sort()) !==
          JSON.stringify(sc.collections.map((c) => c.ref).sort())) ||
      (rotation &&
        (rotation.seconds !== sc.rotate_seconds ||
          rotation.items !== sc.items_per_page)) ||
      (automatic &&
        JSON.stringify(automatic.messages) !==
          JSON.stringify(projectedAutomaticMessages(sc)))
    );
  }),
);
const confirmDiscard = useConfirm();
onBeforeRouteLeave(
  () =>
    !hasDraft.value ||
    confirmDiscard({
      title: "Sair sem salvar as alterações dos canais?",
      description:
        "As coleções, a rotação ou as mensagens que você alterou e ainda não salvou se perdem.",
      confirmLabel: "Descartar e sair",
    }),
);

useHead({ title: "Canais" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Canais" :filters-wrap="false">
      <template #status>
        <span class="hidden op-micro text-muted-foreground lg:inline"
          >Venda e exibição do catálogo</span
        >
      </template>
      <template #filters>
        <p class="hidden op-micro text-muted-foreground lg:block">
          <span class="tabular-nums">{{
            feeds.length + catalogChannels.length
          }}</span>
          canais
        </p>
        <!-- criar/configurar a fundo (novo canal de exibição, opções) é no Admin -->
        <NuxtButton
          :to="`${adminBase}/admin/shop/channel/`"
          target="_blank"
          icon="i-lucide-settings"
          trailing-icon="i-lucide-external-link"
          label="Admin"
          color="neutral"
          variant="outline"
          title="Configurar canais"
        />
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Atualizar"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
        <ReadFreshness
          inline
          :metadata="readMetadata"
          :failed="Boolean(error)"
          :realtime="realtime"
        />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <NuxtAlert
        v-if="errorMsg"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :description="errorMsg"
      />
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível atualizar os canais"
        :description="
          board
            ? 'Exibindo a última leitura disponível.'
            : 'Tente atualizar para consultar os canais.'
        "
        :actions="[
          {
            label: 'Tentar de novo',
            color: 'error',
            variant: 'outline',
            onClick: () => refresh(),
          },
        ]"
      />
      <!-- skeleton -->
      <div v-if="loading" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <NuxtSkeleton
          v-for="i in 3"
          :key="i"
          class="h-44 w-full"
          aria-label="Carregando feed"
        />
      </div>

      <div
        v-else-if="feeds.length"
        class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
      >
        <h2 class="text-sm font-semibold sm:col-span-2 xl:col-span-3">
          Feeds e telas
        </h2>
        <NuxtCard
          v-for="sc in feeds"
          :key="sc.ref"
          as="article"
          class="grid grid-rows-[auto_minmax(0,1fr)_auto]"
          :data-channel-card="sc.ref"
          :data-focus-target="sc.ref"
        >
          <template #header>
            <div class="flex items-start gap-3" data-card-header>
              <NuxtAvatar :icon="`i-lucide-${sc.kind_icon}`" size="md" />
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium text-foreground">
                  {{ sc.name }}
                </p>
                <p class="text-xs text-muted-foreground">{{ sc.kind_label }}</p>
              </div>
              <NuxtSwitch
                v-if="sc.switch"
                :color="switchColor(sc.switch)"
                :model-value="sc.switch.is_active"
                :disabled="isBusy(sc.ref) || !sc.switch.enabled"
                :aria-label="switchLabel(sc.name, sc.switch)"
                :title="
                  sc.switch.enabled
                    ? switchLabel(sc.name, sc.switch)
                    : sc.switch.disabled_reason
                "
                data-channel-switch
                @update:model-value="openSwitch(sc.ref)"
              />
            </div>
          </template>

          <div class="flex h-full flex-col gap-3">
            <ChannelSwitchState v-if="sc.switch" :sw="sc.switch" />

            <NuxtAlert
              v-if="sc.automatic"
              color="neutral"
              variant="subtle"
              :icon="
                sc.automatic.is_sleeping
                  ? 'i-lucide-moon-star'
                  : 'i-lucide-sunrise'
              "
              title="Automático"
              :description="sc.automatic.state_line"
              data-automatic-row
            >
              <template #actions>
                <NuxtSwitch
                  :model-value="sc.automatic.enabled"
                  :disabled="
                    isBusy(sc.ref) || !actionFor(sc, 'automatic')?.enabled
                  "
                  :aria-label="`${sc.name}: modo automático ${sc.automatic.enabled ? 'ligado; desligar' : 'desligado; ligar'}`"
                  :title="
                    actionFor(sc, 'automatic')?.reason ||
                    'Usar o horário da loja, com 15 min antes e depois'
                  "
                  data-automatic-switch
                  @update:model-value="
                    (enabled: boolean) => applyAutomaticToggle(sc, enabled)
                  "
                />
              </template>
            </NuxtAlert>

            <!-- corpo: coleções exibidas -->
            <div
              class="flex min-h-8 flex-wrap items-center gap-1.5"
              data-card-body
            >
              <NuxtBadge
                v-for="c in sc.collections"
                :key="c.ref"
                :color="c.exists ? 'neutral' : 'error'"
                variant="subtle"
                :icon="c.exists ? undefined : 'i-lucide-triangle-alert'"
                :label="c.name"
              />
              <span
                v-if="!sc.collections.length"
                class="text-xs text-muted-foreground/70"
                >Nenhuma coleção: não há nada a exibir.</span
              >
            </div>

            <ChannelHealthChecklist
              :health="healthOf(sc.ref)"
              @choose-collections="openEdit(sc)"
            />
          </div>

          <template #footer>
            <div class="flex flex-wrap items-center gap-1.5" data-card-footer>
              <NuxtPopover
                :open="editRef === sc.ref"
                :content="{ align: 'start' }"
                @update:open="
                  (v) => {
                    if (!v) editRef = null;
                    else openEdit(sc);
                  }
                "
              >
                <NuxtButton
                  icon="i-lucide-layers"
                  label="Coleções"
                  color="neutral"
                  variant="outline"
                  :disabled="!actionFor(sc, 'collections')?.enabled"
                  :title="actionFor(sc, 'collections')?.reason"
                  data-open-editor
                />
                <template #content>
                  <div class="w-72 space-y-3 p-4">
                    <NuxtAlert
                      v-if="collectionConflict(sc)"
                      color="warning"
                      variant="subtle"
                      title="As coleções mudaram no servidor"
                      :description="`Agora: ${sc.collections.map((c) => c.name).join(', ') || 'nenhuma coleção'}. Sua seleção foi preservada.`"
                      :actions="[
                        {
                          label: 'Manter minha seleção',
                          color: 'warning',
                          variant: 'outline',
                          onClick: () => resolveCollections(sc, true),
                        },
                        {
                          label: 'Usar valor atual',
                          color: 'warning',
                          variant: 'outline',
                          onClick: () => resolveCollections(sc, false),
                        },
                      ]"
                    />
                    <NuxtFormField label="Coleções exibidas">
                      <NuxtCheckboxGroup
                        v-model="draft"
                        :items="collectionOptions"
                      />
                    </NuxtFormField>
                    <div class="flex justify-end gap-2">
                      <NuxtButton
                        color="neutral"
                        variant="ghost"
                        label="Descartar"
                        @click="
                          delete collectionDrafts[sc.ref];
                          editRef = null;
                        "
                      />
                      <NuxtButton
                        label="Salvar coleções"
                        :disabled="
                          isBusy(sc.ref) ||
                          collectionConflict(sc) ||
                          !actionFor(sc, 'collections')?.enabled
                        "
                        @click="applyEdit(sc)"
                      />
                    </div>
                  </div>
                </template>
              </NuxtPopover>

              <NuxtPopover
                v-if="sc.capability === 'display'"
                :content="{ align: 'start' }"
                :open="rotationRef === sc.ref"
                @update:open="
                  (v) => {
                    if (!v) rotationRef = null;
                    else openRotation(sc);
                  }
                "
              >
                <NuxtButton
                  icon="i-lucide-timer"
                  :label="
                    sc.rotate_seconds > 0 ? `${sc.rotate_seconds} s` : 'Rotação'
                  "
                  color="neutral"
                  variant="outline"
                  :disabled="!actionFor(sc, 'rotation')?.enabled"
                  :title="
                    actionFor(sc, 'rotation')?.reason ||
                    (sc.rotate_seconds > 0
                      ? `Rotação de páginas: a cada ${sc.rotate_seconds} s, ${sc.items_per_page} itens por tela`
                      : 'Rotação de páginas desligada')
                  "
                />
                <template #content>
                  <div class="w-72 space-y-3 p-4">
                    <NuxtAlert
                      v-if="rotationConflict(sc)"
                      color="warning"
                      variant="subtle"
                      title="A rotação mudou no servidor"
                      :description="`Agora: ${sc.rotate_seconds} s e ${sc.items_per_page} itens. Seu rascunho foi preservado.`"
                      :actions="[
                        {
                          label: 'Manter meus valores',
                          color: 'warning',
                          variant: 'outline',
                          onClick: () => resolveRotation(sc, true),
                        },
                        {
                          label: 'Usar valor atual',
                          color: 'warning',
                          variant: 'outline',
                          onClick: () => resolveRotation(sc, false),
                        },
                      ]"
                    />
                    <NuxtFormField label="Trocar a cada" hint="segundos">
                      <NuxtInput
                        v-model.number="draftSeconds"
                        class="w-full"
                        type="number"
                        :min="0"
                        :step="1"
                        inputmode="numeric"
                      />
                    </NuxtFormField>
                    <NuxtFormField
                      label="Itens por tela"
                      description="Zere os dois campos para mostrar tudo sem rotação."
                    >
                      <NuxtInput
                        v-model.number="draftItems"
                        class="w-full"
                        type="number"
                        :min="0"
                        :step="1"
                        inputmode="numeric"
                      />
                    </NuxtFormField>
                    <div class="flex justify-end gap-2">
                      <NuxtButton
                        color="neutral"
                        variant="ghost"
                        label="Descartar"
                        @click="
                          delete rotationDrafts[sc.ref];
                          rotationRef = null;
                        "
                      />
                      <NuxtButton
                        label="Salvar rotação"
                        :disabled="
                          isBusy(sc.ref) ||
                          rotationConflict(sc) ||
                          !actionFor(sc, 'rotation')?.enabled
                        "
                        @click="applyRotation(sc)"
                      />
                    </div>
                  </div>
                </template>
              </NuxtPopover>

              <NuxtPopover
                v-if="sc.automatic"
                :content="{ align: 'start' }"
                :open="automaticRef === sc.ref"
                @update:open="
                  (v) => {
                    if (!v) automaticRef = null;
                    else openAutomatic(sc);
                  }
                "
              >
                <NuxtButton
                  icon="i-lucide-message-square-text"
                  label="Descanso"
                  color="neutral"
                  variant="outline"
                  :disabled="!actionFor(sc, 'automatic')?.enabled"
                  :title="
                    actionFor(sc, 'automatic')?.reason ||
                    'Configurar a mensagem do descanso de tela'
                  "
                />
                <template #content>
                  <div class="w-80 space-y-3 p-4">
                    <NuxtAlert
                      v-if="automaticConflict(sc)"
                      color="warning"
                      variant="subtle"
                      title="A configuração mudou no servidor"
                      description="Seu texto foi preservado."
                      :actions="[
                        {
                          label: 'Manter meu texto',
                          color: 'warning',
                          variant: 'outline',
                          onClick: () => resolveAutomatic(sc, true),
                        },
                        {
                          label: 'Usar valor atual',
                          color: 'warning',
                          variant: 'outline',
                          onClick: () => resolveAutomatic(sc, false),
                        },
                      ]"
                    />
                    <NuxtFormField
                      label="Frase 1"
                      :hint="`${automaticMessages[0].length}/240`"
                      description="A TV alterna as frases, uma passagem completa por vez."
                    >
                      <NuxtTextarea
                        v-model="automaticMessages[0]"
                        class="w-full"
                        :rows="3"
                        :maxlength="240"
                        placeholder="Atendimento de seg. a sáb., das 9h às 18h"
                      />
                    </NuxtFormField>
                    <NuxtFormField label="Frase 2" hint="opcional">
                      <NuxtTextarea
                        v-model="automaticMessages[1]"
                        class="w-full"
                        :rows="3"
                        :maxlength="240"
                        placeholder="Nelson Boulangerie: minha padaria favorita"
                      />
                    </NuxtFormField>
                    <div class="flex justify-end gap-2">
                      <NuxtButton
                        color="neutral"
                        variant="ghost"
                        label="Descartar"
                        @click="
                          delete automaticDrafts[sc.ref];
                          automaticRef = null;
                        "
                      />
                      <NuxtButton
                        label="Salvar mensagens"
                        :disabled="
                          isBusy(sc.ref) ||
                          automaticConflict(sc) ||
                          !automaticMessages[0].trim() ||
                          !actionFor(sc, 'automatic')?.enabled
                        "
                        @click="applyAutomaticMessage(sc)"
                      />
                    </div>
                  </div>
                </template>
              </NuxtPopover>

              <NuxtButton
                :to="outputHref(sc)"
                target="_blank"
                :icon="
                  sc.capability === 'display'
                    ? 'i-lucide-external-link'
                    : 'i-lucide-code-xml'
                "
                :label="sc.capability === 'display' ? 'Abrir TV' : 'Ver feed'"
                color="neutral"
                variant="outline"
                :title="sc.output_path"
              />
            </div>
          </template>
        </NuxtCard>
      </div>

      <NuxtEmpty
        v-else-if="!error && !catalogChannels.length"
        icon="i-lucide-monitor-off"
        title="Nenhum canal configurado"
        description="Configure os canais no Admin."
      />
      <section
        v-if="!loading && catalogChannels.length"
        class="mt-6 space-y-3"
        aria-label="Canais de venda"
      >
        <h2 class="text-sm font-semibold">Canais de venda</h2>
        <p class="text-xs text-muted-foreground">
          Envio de produtos: o que a casa registrou ao mandar o catálogo a cada
          canal.
        </p>
        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <NuxtCard
            v-for="channel in catalogChannels"
            :key="channel.ref"
            as="article"
            class="grid grid-rows-[auto_minmax(0,1fr)_auto]"
            :data-focus-target="channel.ref"
            :data-channel-card="channel.ref"
          >
            <template #header>
              <div class="flex items-start gap-3" data-card-header>
                <h3 class="min-w-0 flex-1 truncate font-medium">
                  {{ channel.name }}
                </h3>
                <NuxtSwitch
                  v-if="channel.switch"
                  :color="switchColor(channel.switch)"
                  :model-value="channel.switch.is_active"
                  :disabled="isBusy(channel.ref) || !channel.switch.enabled"
                  :aria-label="switchLabel(channel.name, channel.switch)"
                  :title="
                    channel.switch.enabled
                      ? switchLabel(channel.name, channel.switch)
                      : channel.switch.disabled_reason
                  "
                  data-channel-switch
                  @update:model-value="openSwitch(channel.ref)"
                />
              </div>
            </template>

            <div class="flex h-full flex-col gap-2" data-card-body>
              <ChannelSwitchState v-if="channel.switch" :sw="channel.switch" />
              <p class="text-sm text-muted-foreground">
                {{ channel.diagnostic }}
              </p>
              <ChannelHealthChecklist :health="healthOf(channel.ref)" />
              <!-- com checklist, a contagem crua sai: o que pede ação já está nele -->
              <p
                v-if="channel.observed && !healthOf(channel.ref)"
                class="text-xs tabular-nums"
              >
                Envio de produtos: {{ channel.synced }} sincronizados ·
                {{ channel.pending }} pendentes · {{ channel.errors }} com erro
                · {{ channel.retracted }} retirados · {{ channel.skipped }} não
                enviados
              </p>
              <p
                v-else-if="!healthOf(channel.ref)"
                class="text-xs text-muted-foreground"
              >
                Ainda sem registros de envio de produtos.
              </p>
              <IFoodChannelStore v-if="channel.ref === IFOOD_CHANNEL_REF" />
            </div>

            <template #footer>
              <div class="flex flex-wrap items-center gap-2" data-card-footer>
                <NuxtButton
                  :to="`/channels/${encodeURIComponent(channel.ref)}/catalog`"
                  label="Revisar vínculos"
                  color="neutral"
                  variant="outline"
                />
                <NuxtButton
                  :to="channel.catalog_path"
                  label="Ver produtos no Catálogo"
                  color="neutral"
                  variant="ghost"
                />
              </div>
            </template>
          </NuxtCard>
        </div>
      </section>
    </section>

    <ChannelSwitchDialog
      :open="Boolean(switchTarget)"
      :sw="switchTarget"
      :managers="board?.managers ?? []"
      :viewer-name="board?.viewer_name ?? ''"
      :busy="Boolean(switchRef && isBusy(switchRef))"
      :submit="submitSwitch"
      @update:open="
        (value: boolean) => {
          if (!value) switchRef = null;
        }
      "
    />
  </main>
</template>
