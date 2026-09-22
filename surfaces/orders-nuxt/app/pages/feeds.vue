<script setup lang="ts">
// Canais — venda (loja online, WhatsApp, iFood, PDV) e exibição (📺 menuboard na
// TV, 🛰 Google/Meta). Todo card tem a mesma estrutura: CABEÇALHO com o toggle
// "Ativo", CORPO com o estado, RODAPÉ com as ações. O toggle é o mesmo em todos:
// abre o modal de período + motivo + gerente (`ChannelSwitchDialog`).
// Nos feeds o operador também escolhe as coleções e a rotação de páginas da TV, e
// abre/prevê a saída. A ORDEM das coleções é global (reordenável no Catálogo).
import type { ChannelSwitchProjection, CollectionOptionProjection, FeedProjection } from "~/types/feeds";
import { IFOOD_CHANNEL_REF } from "~/presentation/ifoodStore";

const { readMetadata, realtime, board, pending, error, errorMsg, refresh, isBusy, switchChannel, setCollections, setRotation } = useFeedBoard();
const catalogChannels = computed(() => board.value?.catalog_channels ?? []);
const feeds = computed<FeedProjection[]>(() => board.value?.feeds ?? []);
const allCollections = computed<CollectionOptionProjection[]>(() => board.value?.all_collections ?? []);
const loading = computed(() => pending.value && !board.value);
// O checklist vivo de cada canal (o que falta, e o botão que resolve).
const { healthOf } = useChannelHealth();

// O aviso da fila de Pedidos chega aqui com `?focus=<ref>`: o card daquele canal —
// onde mora o toggle — vai para a linha de foco assim que a leitura o traz.
const route = useRoute();
const focusKey = computed(() => {
  const wanted = typeof route.query.focus === "string" ? route.query.focus : "";
  const known = [...catalogChannels.value, ...feeds.value].some((channel) => channel.ref === wanted);
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
  return feeds.value.find((feed) => feed.ref === switchRef.value)?.switch
    ?? catalogChannels.value.find((channel) => channel.ref === switchRef.value)?.switch
    ?? null;
});
function openSwitch(ref_: string) {
  switchRef.value = ref_;
}
const submitSwitch = (request: Parameters<typeof switchChannel>[1], approval?: Record<string, string>) =>
  switchChannel(switchRef.value!, request, approval);
const switchTone = (sw: ChannelSwitchProjection | null | undefined) => (sw?.closed_by_shop ? "muted" : "success");
const switchLabel = (name: string, sw: ChannelSwitchProjection | null | undefined) =>
  sw?.is_active ? `${name}: ligado. Desligar…` : `${name}: desligado. Ligar…`;

// Rascunhos pertencem ao feed e à pessoa (a página é remontada na troca de identidade).
const actionFor = (sc: FeedProjection, field: string) => sc.actions.find((action) => action.ref === field);
const baseFor = (sc: FeedProjection, field: string) => String(actionFor(sc, field)?.payload_schema.base_revision || "");
const editRef = ref<string | null>(null);
const collectionDrafts = ref<Record<string, { values: string[]; base: string }>>({});
const draft = computed({
  get: () => new Set(editRef.value ? collectionDrafts.value[editRef.value]?.values ?? [] : []),
  set: (values: Set<string>) => { if (editRef.value && collectionDrafts.value[editRef.value]) collectionDrafts.value[editRef.value]!.values = [...values]; },
});
function openEdit(sc: FeedProjection) {
  collectionDrafts.value[sc.ref] ??= { values: sc.collections.map((c) => c.ref), base: baseFor(sc, "collections") };
  editRef.value = sc.ref;
}
function toggleDraft(ref_: string) {
  const next = new Set(draft.value);
  if (next.has(ref_)) next.delete(ref_); else next.add(ref_);
  draft.value = next;
}
const collectionConflict = (sc: FeedProjection) => !!collectionDrafts.value[sc.ref] && collectionDrafts.value[sc.ref]!.base !== baseFor(sc, "collections");
function resolveCollections(sc: FeedProjection, keep: boolean) {
  collectionDrafts.value[sc.ref] = { values: keep ? [...draft.value] : sc.collections.map((c) => c.ref), base: baseFor(sc, "collections") };
}
async function applyEdit(sc: FeedProjection) {
  if (collectionConflict(sc)) return;
  const ok = await setCollections(sc.ref, [...draft.value], collectionDrafts.value[sc.ref]?.base);
  if (ok) { Reflect.deleteProperty(collectionDrafts.value, sc.ref); if (editRef.value === sc.ref) editRef.value = null; }
}

const rotationRef = ref<string | null>(null);
const rotationDrafts = ref<Record<string, { seconds: number; items: number; base: string }>>({});
const draftSeconds = computed({
  get: () => rotationRef.value ? rotationDrafts.value[rotationRef.value]?.seconds ?? 0 : 0,
  set: (value: number) => { if (rotationRef.value && rotationDrafts.value[rotationRef.value]) rotationDrafts.value[rotationRef.value]!.seconds = value; },
});
const draftItems = computed({
  get: () => rotationRef.value ? rotationDrafts.value[rotationRef.value]?.items ?? 0 : 0,
  set: (value: number) => { if (rotationRef.value && rotationDrafts.value[rotationRef.value]) rotationDrafts.value[rotationRef.value]!.items = value; },
});
function openRotation(sc: FeedProjection) {
  rotationDrafts.value[sc.ref] ??= { seconds: sc.rotate_seconds, items: sc.items_per_page, base: baseFor(sc, "rotation") };
  rotationRef.value = sc.ref;
}
const rotationConflict = (sc: FeedProjection) => !!rotationDrafts.value[sc.ref] && rotationDrafts.value[sc.ref]!.base !== baseFor(sc, "rotation");
function resolveRotation(sc: FeedProjection, keep: boolean) {
  rotationDrafts.value[sc.ref] = { seconds: keep ? draftSeconds.value : sc.rotate_seconds, items: keep ? draftItems.value : sc.items_per_page, base: baseFor(sc, "rotation") };
}
async function applyRotation(sc: FeedProjection) {
  if (rotationConflict(sc)) return;
  const ok = await setRotation(sc.ref, Number(draftSeconds.value) || 0, Number(draftItems.value) || 0, rotationDrafts.value[sc.ref]?.base);
  if (ok) { Reflect.deleteProperty(rotationDrafts.value, sc.ref); if (rotationRef.value === sc.ref) rotationRef.value = null; }
}
const hasDraft = computed(() => feeds.value.some((sc) => {
  const collections = collectionDrafts.value[sc.ref];
  const rotation = rotationDrafts.value[sc.ref];
  return (collections && JSON.stringify([...collections.values].sort()) !== JSON.stringify(sc.collections.map((c) => c.ref).sort())) ||
    (rotation && (rotation.seconds !== sc.rotate_seconds || rotation.items !== sc.items_per_page));
}));
onBeforeRouteLeave(() => !hasDraft.value || window.confirm("Há alterações de feed não salvas. Sair e descartá-las?"));

useHead({ title: "Canais" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <UiToolbar>
      <div class="flex items-center gap-2">
        <Icon name="lucide:monitor-play" class="size-4 text-muted-foreground" />
        <h1 class="text-sm font-semibold">Canais</h1>
        <span class="text-xs text-muted-foreground">Venda e exibição do catálogo</span>
      </div>
      <template #end>
        <p class="hidden text-xs text-muted-foreground sm:block">
          <span class="tabular-nums">{{ feeds.length + catalogChannels.length }}</span> canais
        </p>
        <!-- criar/configurar a fundo (novo canal de exibição, opções) é no Admin -->
        <a
          :href="`${adminBase}/admin/shop/channel/`" target="_blank" rel="noopener"
          class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-3 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
          title="Configurar canais"
        >
          <Icon name="lucide:settings" class="size-4" />
          <span class="hidden sm:inline">Admin</span>
          <Icon name="lucide:external-link" class="size-3.5 opacity-60" />
        </a>
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </UiToolbar>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" :realtime="realtime" />

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <p v-if="errorMsg" role="alert" class="mb-3 text-sm text-destructive">{{ errorMsg }}</p>
      <div v-if="error" role="alert" class="mb-3 rounded-md border border-destructive p-3 text-sm">
        Não foi possível atualizar os feeds. {{ board ? "Exibindo a última leitura disponível." : "Tente atualizar para consultar os feeds." }}
        <button type="button" class="ml-2 min-h-11 underline" @click="refresh()">Tentar novamente</button>
      </div>
      <!-- skeleton -->
      <div v-if="loading" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div v-for="i in 3" :key="i" class="h-40 animate-pulse rounded-xl border border-border bg-muted/40"></div>
      </div>

      <div v-else-if="feeds.length" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <h2 class="text-sm font-semibold sm:col-span-2 xl:col-span-3">Feeds e telas</h2>
        <article
          v-for="sc in feeds" :key="sc.ref"
          class="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-card p-4 outline-none transition"
          :data-channel-card="sc.ref"
          :data-focus-target="sc.ref"
          :class="sc.is_active ? '' : 'opacity-80'"
        >
          <!-- cabeçalho: tipo + nome + toggle "Ativo" -->
          <div class="flex items-start gap-3" data-card-header>
            <span class="grid size-9 shrink-0 place-items-center rounded-md border bg-muted/40 text-foreground">
              <Icon :name="`lucide:${sc.kind_icon}`" class="size-4" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate font-medium text-foreground">{{ sc.name }}</p>
              <p class="text-xs text-muted-foreground">{{ sc.kind_label }}</p>
            </div>
            <UiSwitch
              v-if="sc.switch"
              :tone="switchTone(sc.switch)"
              :model-value="sc.switch.is_active"
              :disabled="isBusy(sc.ref) || !sc.switch.enabled"
              :aria-label="switchLabel(sc.name, sc.switch)"
              :title="sc.switch.enabled ? switchLabel(sc.name, sc.switch) : sc.switch.disabled_reason"
              data-channel-switch
              @update:model-value="openSwitch(sc.ref)"
            />
          </div>
          <ChannelSwitchState v-if="sc.switch" :sw="sc.switch" />

          <!-- corpo: coleções exibidas -->
          <div class="flex min-h-8 flex-wrap items-center gap-1.5" data-card-body>
            <span
              v-for="c in sc.collections" :key="c.ref"
              class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
              :class="c.exists ? 'border-border text-muted-foreground' : 'border-destructive/40 text-destructive'"
            >
              <Icon v-if="!c.exists" name="lucide:triangle-alert" class="size-3" />
              {{ c.name }}
            </span>
            <span v-if="!sc.collections.length" class="text-xs text-muted-foreground/70">Nenhuma coleção — nada a exibir.</span>
          </div>

          <ChannelHealthChecklist :health="healthOf(sc.ref)" @choose-collections="openEdit(sc)" />

          <!-- rodapé: ações -->
          <div class="mt-auto flex items-center gap-1.5 border-t border-border pt-3" data-card-footer>
            <UiPopover :open="editRef === sc.ref" @update:open="(v) => { if (!v) editRef = null; else openEdit(sc); }">
              <UiPopoverTrigger as-child>
                <button type="button" :disabled="!actionFor(sc, 'collections')?.enabled" :title="actionFor(sc, 'collections')?.reason" class="min-h-control min-w-control inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent">
                  <Icon name="lucide:layers" class="size-3.5" /> Coleções
                </button>
              </UiPopoverTrigger>
              <UiPopoverContent align="start" :side-offset="6" class="w-60 p-2">
                <p class="mb-1 px-1 text-xs font-medium text-muted-foreground">Coleções exibidas</p>
                <div v-if="collectionConflict(sc)" role="alert" class="mb-2 text-xs">
                  <p>No servidor: {{ sc.collections.map((c) => c.name).join(', ') || 'nenhuma coleção' }}. Sua seleção foi preservada.</p>
                  <button type="button" class="min-h-11 underline" @click="resolveCollections(sc, true)">Manter minha seleção</button>
                  <button type="button" class="min-h-11 underline" @click="resolveCollections(sc, false)">Usar valor atual</button>
                </div>
                <div class="max-h-60 overflow-auto">
                  <label
                    v-for="opt in allCollections" :key="opt.ref"
                    class="flex min-h-control cursor-pointer items-center gap-2 rounded px-1.5 py-1.5 text-sm transition hover:bg-accent"
                  >
                    <input type="checkbox" :checked="draft.has(opt.ref)" class="size-4 rounded border-border accent-foreground" @change="toggleDraft(opt.ref)" />
                    <span class="flex-1 truncate">{{ opt.name }}</span>
                    <span class="text-xs tabular-nums text-muted-foreground/60">{{ opt.product_count }}</span>
                  </label>
                </div>
                <div class="mt-2 flex justify-end gap-1.5 border-t border-border pt-2">
                  <button type="button" class="min-h-control min-w-control rounded-md border px-2.5 py-1.5 text-xs font-medium transition hover:bg-accent" @click="delete collectionDrafts[sc.ref]; editRef = null">Descartar</button>
                  <button type="button" :disabled="isBusy(sc.ref) || collectionConflict(sc) || !actionFor(sc, 'collections')?.enabled" class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" @click="applyEdit(sc)">Aplicar</button>
                </div>
              </UiPopoverContent>
            </UiPopover>

            <UiPopover
              v-if="sc.capability === 'display'"
              :open="rotationRef === sc.ref" @update:open="(v) => { if (!v) rotationRef = null; else openRotation(sc); }"
            >
              <UiPopoverTrigger as-child>
                <button
                  type="button" :disabled="!actionFor(sc, 'rotation')?.enabled" class="min-h-control min-w-control inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent"
                  :title="actionFor(sc, 'rotation')?.reason || (sc.rotate_seconds > 0 ? `Rotação de páginas: a cada ${sc.rotate_seconds} s, ${sc.items_per_page} itens por tela` : 'Rotação de páginas desligada')"
                >
                  <Icon name="lucide:timer" class="size-3.5" />
                  {{ sc.rotate_seconds > 0 ? `${sc.rotate_seconds} s` : "Rotação" }}
                </button>
              </UiPopoverTrigger>
              <UiPopoverContent align="start" :side-offset="6" class="w-64 p-3">
                <p class="mb-2 text-xs font-medium text-muted-foreground">Rotação de páginas</p>
                <div v-if="rotationConflict(sc)" role="alert" class="mb-2 text-xs">
                  <p>No servidor: {{ sc.rotate_seconds }} s e {{ sc.items_per_page }} itens. Seu rascunho foi preservado.</p>
                  <button type="button" class="min-h-11 underline" @click="resolveRotation(sc, true)">Manter meus valores</button>
                  <button type="button" class="min-h-11 underline" @click="resolveRotation(sc, false)">Usar valor atual</button>
                </div>
                <div class="grid gap-2">
                  <label class="min-h-control flex items-center justify-between gap-2 text-sm">
                    <span>Trocar a cada</span>
                    <span class="inline-flex items-center gap-1">
                      <input
                        v-model.number="draftSeconds" type="number" min="0" step="1" inputmode="numeric"
                        class="min-h-control h-8 w-16 rounded-md border border-border bg-background px-2 text-right text-sm tabular-nums"
                      />
                      <span class="text-xs text-muted-foreground">s</span>
                    </span>
                  </label>
                  <label class="min-h-control flex items-center justify-between gap-2 text-sm">
                    <span>Itens por tela</span>
                    <input
                      v-model.number="draftItems" type="number" min="0" step="1" inputmode="numeric"
                      class="min-h-control h-8 w-16 rounded-md border border-border bg-background px-2 text-right text-sm tabular-nums"
                    />
                  </label>
                </div>
                <p class="mt-2 text-xs text-muted-foreground/70">Zere os dois para mostrar tudo numa tela só, sem rotação.</p>
                <div class="mt-2 flex justify-end gap-1.5 border-t border-border pt-2">
                  <button type="button" class="min-h-control min-w-control rounded-md border px-2.5 py-1.5 text-xs font-medium transition hover:bg-accent" @click="delete rotationDrafts[sc.ref]; rotationRef = null">Descartar</button>
                  <button type="button" :disabled="isBusy(sc.ref) || rotationConflict(sc) || !actionFor(sc, 'rotation')?.enabled" class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" @click="applyRotation(sc)">Aplicar</button>
                </div>
              </UiPopoverContent>
            </UiPopover>

            <a
              :href="outputHref(sc)" target="_blank" rel="noopener"
              class="ml-auto inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent"
              :title="sc.output_path"
            >
              <Icon :name="sc.capability === 'display' ? 'lucide:external-link' : 'lucide:code-xml'" class="size-3.5" />
              {{ sc.capability === "display" ? "Abrir TV" : "Ver feed" }}
            </a>
          </div>
        </article>
      </div>

      <div v-else-if="!error && !catalogChannels.length" class="grid place-items-center rounded-xl border border-dashed border-border py-16 text-center">
        <Icon name="lucide:monitor-off" class="mb-2 size-8 text-muted-foreground/40" />
        <p class="text-sm text-muted-foreground">Nenhum canal configurado. Configure os canais no Admin.</p>
      </div>
      <section v-if="!loading && catalogChannels.length" class="mt-6 space-y-3" aria-label="Canais de venda">
        <h2 class="text-sm font-semibold">Canais de venda</h2>
        <p class="text-xs text-muted-foreground">
          Envio de produtos: o que a casa registrou ao mandar o catálogo a cada canal.
        </p>
        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="channel in catalogChannels" :key="channel.ref"
            class="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-card p-4 outline-none transition"
            :class="channel.is_active ? '' : 'opacity-80'"
            :data-focus-target="channel.ref"
            :data-channel-card="channel.ref"
          >
            <!-- cabeçalho: nome + toggle "Ativo" -->
            <div class="flex items-start gap-3" data-card-header>
              <h3 class="min-w-0 flex-1 truncate font-medium">{{ channel.name }}</h3>
              <UiSwitch
                v-if="channel.switch"
                :tone="switchTone(channel.switch)"
                :model-value="channel.switch.is_active"
                :disabled="isBusy(channel.ref) || !channel.switch.enabled"
                :aria-label="switchLabel(channel.name, channel.switch)"
                :title="channel.switch.enabled ? switchLabel(channel.name, channel.switch) : channel.switch.disabled_reason"
                data-channel-switch
                @update:model-value="openSwitch(channel.ref)"
              />
            </div>
            <!-- corpo: estado do canal e do envio de produtos -->
            <div class="flex flex-col gap-2" data-card-body>
              <ChannelSwitchState v-if="channel.switch" :sw="channel.switch" />
              <p class="text-sm text-muted-foreground">{{ channel.diagnostic }}</p>
              <ChannelHealthChecklist :health="healthOf(channel.ref)" />
              <!-- com checklist, a contagem crua sai: o que pede ação já está nele -->
              <p v-if="channel.observed && !healthOf(channel.ref)" class="text-xs tabular-nums">
                Envio de produtos: {{ channel.synced }} sincronizados · {{ channel.pending }} pendentes · {{ channel.errors }} com erro · {{ channel.retracted }} retirados · {{ channel.skipped }} não enviados
              </p>
              <p v-else-if="!healthOf(channel.ref)" class="text-xs text-muted-foreground">Ainda sem registros de envio de produtos.</p>
              <IFoodChannelStore v-if="channel.ref === IFOOD_CHANNEL_REF" />
            </div>
            <!-- rodapé: ações -->
            <div class="mt-auto flex flex-wrap items-center gap-2 border-t border-border pt-3" data-card-footer>
              <NuxtLink :to="`/channels/${encodeURIComponent(channel.ref)}/catalog`" class="inline-flex min-h-control items-center rounded-md border px-3 text-sm hover:bg-accent">Revisar vínculos</NuxtLink>
              <NuxtLink :to="channel.catalog_path" class="inline-flex min-h-control items-center rounded-md border px-3 text-sm hover:bg-accent">Ver produtos no Catálogo</NuxtLink>
            </div>
          </article>
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
      @update:open="(value: boolean) => { if (!value) switchRef = null; }"
    />
  </main>
</template>
