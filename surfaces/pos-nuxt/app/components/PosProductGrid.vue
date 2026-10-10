<script setup lang="ts">
// Sale Workspace · product grid (spec §2.2) — image-forward grade + rail de
// categorias. Consumes the catalog Projection through `presentation/catalog`
// (favourite-ordered categories, name/code filter); price and availability are
// sealed in the Projection (price_display) and only rendered. Search and
// the active collection are grid-local presentation state. Emits `add`; the
// shell resolves the session command.
import type { POSCartItem, POSCollectionProjection, POSProductProjection, POSTabProjection } from "~/types/pos";
import {
  FAVORITES_COLLECTION,
  HIDE_UNAVAILABLE_STORAGE_KEY,
  favoriteProducts,
  matchOpenTabs,
  cartQtyForSku,
  collectionColorMap,
  enterTargetProduct,
  filterProducts,
  gridEntries,
  hiddenUnavailableLabel,
  hideUnavailableProducts,
  orderCollections,
  parseHideUnavailable,
} from "~/presentation/catalog";

const props = defineProps<{
  products: POSProductProjection[];
  collections: POSCollectionProjection[];
  favoriteRefs: string[];
  cartItems: POSCartItem[];
  pending: boolean;
  /** As comandas do quadro: a busca acha comanda pelo número, nome ou cliente. */
  tabs?: POSTabProjection[];
  /** A comanda aberta agora (fica fora do que a busca acha). */
  currentTabRef?: string;
  /** A busca oferece "Buscar cliente" (só na venda com a barra de cliente). */
  customerSearch?: boolean;
}>();

const emit = defineEmits<{
  add: [POSProductProjection];
  openTab: [ref: string];
  findCustomer: [query: string];
}>();

// Toque (tablet, celular): sem teclas impressas, chips de 48 px com "Favoritos"
// primeiro, tile sem SKU, grade pela largura do dedo e "Ler código" pela câmera.
const coarsePointer = useMediaQuery("(pointer: coarse)");
const scannerOpen = ref(false);

const search = ref("");
const activeCollection = ref("");

// Grid density is a grid-local presentation preference (not data, not policy).
// Persisted per terminal in localStorage; defaults to "cozy" on the server so
// hydration stays stable, then the stored choice is applied after mount.
type Density = "compact" | "cozy" | "roomy";
const DENSITIES: { key: Density; label: string; icon: string; cols: string }[] = [
  // As colunas seguem a largura da GRADE (container query), não a da tela: com a
  // barra lateral estendida e a comanda ao lado, 1024px de tela davam quatro
  // tiles de 77px, e "Cappuccino" não cabia numa linha. Cada densidade garante
  // um tile mínimo (~120px compacta, ~135px padrão, ~185px ampla).
  { key: "compact", label: "Compacta", icon: "lucide:grid-3x3", cols: "grid-cols-3 @lg:grid-cols-4 @2xl:grid-cols-5 @3xl:grid-cols-6 @4xl:grid-cols-7 @5xl:grid-cols-8" },
  { key: "cozy", label: "Padrão", icon: "lucide:layout-grid", cols: "grid-cols-2 @md:grid-cols-3 @xl:grid-cols-4 @3xl:grid-cols-5 @5xl:grid-cols-6" },
  { key: "roomy", label: "Ampla", icon: "lucide:grid-2x2", cols: "grid-cols-2 @xl:grid-cols-3 @4xl:grid-cols-4" },
];
// No toque, a grade é pela largura do dedo (v3 tablet deitado: 3 colunas ao lado
// da comanda; v4 tablet em pé: 4 colunas de 188 px), sem seletor de densidade.
const TOUCH_COLS = "grid-cols-2 @lg:grid-cols-3 @3xl:grid-cols-4 @5xl:grid-cols-5";
const DENSITY_STORAGE_KEY = "pos.productDensity";
const density = ref<Density>("cozy");
const densityCols = computed(() => coarsePointer.value
  ? TOUCH_COLS
  : DENSITIES.find((d) => d.key === density.value)?.cols ?? DENSITIES[1]!.cols);
// O ponto colorido do chip de cada coleção (v4): a cor que os produtos dela já trazem.
const collectionColors = computed(() => collectionColorMap(props.products));

// Ocultar indisponíveis: preferência de exibição deste dispositivo (o olho ao
// lado da densidade). Padrão = mostrar; a regra de disponibilidade não muda.
const hideUnavailable = ref(false);

onMounted(() => {
  if (coarsePointer.value && props.favoriteRefs.length) activeCollection.value = FAVORITES_COLLECTION;
  const stored = localStorage.getItem(DENSITY_STORAGE_KEY);
  if (stored === "compact" || stored === "cozy" || stored === "roomy") density.value = stored;
  try {
    hideUnavailable.value = parseHideUnavailable(localStorage.getItem(HIDE_UNAVAILABLE_STORAGE_KEY));
  } catch {
    hideUnavailable.value = false;
  }
});

function setHideUnavailable(value: boolean) {
  hideUnavailable.value = value;
  try {
    localStorage.setItem(HIDE_UNAVAILABLE_STORAGE_KEY, value ? "1" : "0");
  } catch {
    // Sem storage, a escolha vale até recarregar.
  }
}
const hideUnavailableActionLabel = computed(() => (hideUnavailable.value ? "Mostrar indisponíveis" : "Ocultar indisponíveis"));

function setDensity(value: Density) {
  density.value = value;
  if (import.meta.client) localStorage.setItem(DENSITY_STORAGE_KEY, value);
}

const orderedCollections = computed(() => orderCollections(props.collections, props.favoriteRefs));
const matchedProducts = computed(() => {
  // A busca procura em TUDO: o chip ligado é filtro de navegação, não de busca.
  if (activeCollection.value === FAVORITES_COLLECTION && !search.value.trim()) {
    return filterProducts(favoriteProducts(props.products, props.favoriteRefs), {});
  }
  const collectionRef = activeCollection.value === FAVORITES_COLLECTION ? "" : activeCollection.value;
  return filterProducts(props.products, { collectionRef, query: search.value });
});
// "produto, código, comanda ou cliente" (v4): as comandas em uso que casam.
const matchedTabs = computed(() => matchOpenTabs(props.tabs || [], search.value, props.currentTabRef || ""));
function openMatchedTab(ref: string) {
  search.value = "";
  emit("openTab", ref);
}
function findCustomer() {
  const query = search.value.trim();
  if (!query) return;
  search.value = "";
  emit("findCustomer", query);
}
// "Ler código": o que a câmera lê entra na busca como se o leitor do balcão
// tivesse digitado (o código de barras está no índice, `gtin`), e o Enter lança.
function onScanned(code: string) {
  search.value = code;
  if (enterTargetProduct(filteredProducts.value, code)) {
    onSearchEnter();
    return;
  }
  const tab = matchedTabs.value[0];
  if (tab) openMatchedTab(tab.ref);
}
// Com o olho fechado, o indisponível sai depois da busca/coleção: o que sobra é
// a grade, e `hiddenCount` diz quantos casaram mas estão ocultos.
const visibility = computed(() => hideUnavailableProducts(matchedProducts.value, hideUnavailable.value));
const filteredProducts = computed(() => visibility.value.products);
const hiddenCount = computed(() => visibility.value.hiddenCount);

// Cartão de escolha: sem busca, produtos do mesmo `choice_group` viram um tile só
// que abre a escolha; com busca, cada produto aparece sozinho (o Enter lança).
// Oculto, a opção indisponível também sai da escolha.
const groupSource = computed(() => hideUnavailableProducts(props.products, hideUnavailable.value).products);
const entries = computed(() => gridEntries(filteredProducts.value, groupSource.value, search.value));

function productQty(sku: string): number {
  return cartQtyForSku(props.cartItems, sku);
}

// F3 focuses the search field (the shell owns the shortcut, the grid the field).
// `seed` é o search-as-you-type: uma letra digitada fora de input começa uma
// busca NOVA com aquele caractere (as teclas seguintes já caem no campo focado).
const searchInputRef = ref<{ inputRef?: HTMLInputElement | null } | null>(null);
function focusSearch(seed?: string) {
  if (seed !== undefined) search.value = seed;
  searchInputRef.value?.inputRef?.focus();
}
defineExpose({ focusSearch });

// Enter na busca adiciona o primeiro resultado DISPONÍVEL (esgotado não entra;
// com um único resultado, é ele). Depois limpa a busca e MANTÉM o foco — venda
// em sequência: digita, Enter, digita, Enter.
function onSearchEnter() {
  const target = enterTargetProduct(filteredProducts.value, search.value);
  if (!target) {
    // Sem produto: a comanda que casou sozinha abre; senão, a busca vira cliente.
    if (matchedTabs.value.length === 1) openMatchedTab(matchedTabs.value[0]!.ref);
    else if (!matchedTabs.value.length && props.customerSearch) findCustomer();
    return;
  }
  emit("add", target);
  search.value = "";
  searchInputRef.value?.inputRef?.focus();
}

// Esc na busca: limpa E DEVOLVE O TECLADO. O foco aqui deixou de ser primordial
// quando a tela passou a capturar digitação globalmente — uma letra fora de
// campo já começa uma busca nova (`focusSearch(seed)`). Preso no campo, porém, o
// teclado fica sequestrado: os dígitos viram texto de busca em vez de alimentar
// o numpad da linha, que é o instrumento do balcão. Então Esc desfaz a busca e
// sai. (O `type="search"` do browser limpa sozinho, mas mantém o foco — e era
// justamente o foco o problema.)
function onSearchEscape() {
  search.value = "";
  searchInputRef.value?.inputRef?.blur();
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-2.5">
    <!-- Busca + densidade (v4): a busca é o instrumento do balcão (44 px, Enter
         adiciona, F3 ou / focam); a densidade é um seletor segmentado à vista. -->
    <div class="flex shrink-0 items-center gap-2">
      <PosSearchField
        ref="searchInputRef"
        v-model="search"
        :kbd="coarsePointer ? undefined : ['F3', '/']"
        :hint="coarsePointer ? undefined : 'Enter adiciona'"
        :placeholder="coarsePointer ? 'Buscar produto ou comanda' : (customerSearch ? 'Buscar produto, código, comanda ou cliente' : 'Buscar produto, código ou comanda')"
        :class="coarsePointer ? 'h-14' : ''"
        :autofocus="!coarsePointer"
        @keydown.enter.prevent="onSearchEnter"
        @keydown.esc.prevent="onSearchEscape"
      />
      <NuxtButton
        v-if="coarsePointer"
        size="xl"
        color="neutral"
        variant="outline"
        class="h-14 shrink-0"
        aria-label="Ler código pela câmera"
        data-pos-scan-code
        @click="scannerOpen = true"
      >
        <Icon name="lucide:scan-barcode" class="size-6" aria-hidden="true" />
        <span class="max-sm:sr-only">Ler código</span>
      </NuxtButton>
      <NuxtFieldGroup v-else class="shrink-0" role="group" aria-label="Densidade da grade" title="Densidade da grade">
        <NuxtButton
          v-for="opt in DENSITIES"
          :key="opt.key"
          color="neutral"
          variant="outline"
          active-color="primary"
          active-variant="solid"
          :active="density === opt.key"
          :square="density !== opt.key"
          :aria-label="`Densidade ${opt.label}`"
          :aria-pressed="density === opt.key"
          :title="opt.label"
          @click="setDensity(opt.key)"
        >
          <Icon :name="opt.icon" class="size-4 shrink-0" aria-hidden="true" />
          <span v-if="density === opt.key" class="max-xl:sr-only">{{ opt.label }}</span>
        </NuxtButton>
      </NuxtFieldGroup>
    </div>

    <!-- O que a busca achou além de produto: comanda em uso e, sem comanda, o
         cliente. Uma faixa só, acima da grade, e só enquanto há busca. -->
    <div v-if="search.trim() && (matchedTabs.length || (customerSearch && !coarsePointer))" class="flex shrink-0 flex-wrap items-center gap-1.5" data-pos-search-more>
      <NuxtButton
        v-for="tab in matchedTabs"
        :key="tab.ref"
        variant="outline"
        :data-pos-search-tab="tab.ref"
        @click="openMatchedTab(tab.ref)"
      >
        <Icon name="lucide:receipt-text" class="size-4" aria-hidden="true" />
        <span class="font-semibold">Comanda {{ tab.display_ref }}</span>
        <span v-if="tab.customer_name" class="max-w-40 truncate font-normal text-muted-foreground">{{ tab.customer_name }}</span>
        <span class="font-normal text-muted-foreground tnum">{{ tab.item_count }} {{ tab.item_count === 1 ? "item" : "itens" }}</span>
      </NuxtButton>
      <NuxtButton
        v-if="customerSearch && !coarsePointer"
        color="neutral"
        variant="outline"
        data-pos-search-customer
        @click="findCustomer"
      >
        <Icon name="lucide:user-round-search" class="size-4 text-muted-foreground" aria-hidden="true" />
        Buscar cliente “<span class="max-w-40 truncate">{{ search.trim() }}</span>”
      </NuxtButton>
    </div>

    <!-- Coleções em chips (v4): 32 px no balcão, 48 px no toque com "Favoritos"
         primeiro. Ocultar indisponíveis é preferência deste dispositivo e mora no fim
         da fila (a v4 não tem o olho ao lado da busca). -->
    <div class="-mx-1 flex shrink-0 overflow-x-auto px-1 pb-1 no-scrollbar" :class="coarsePointer ? 'gap-2' : 'gap-1'">
      <NuxtButton
        v-if="coarsePointer && favoriteRefs.length"
        size="xl"
        color="neutral"
        variant="outline"
        active-color="primary"
        active-variant="solid"
        :active="activeCollection === FAVORITES_COLLECTION"
        class="shrink-0 whitespace-nowrap rounded-full"
        :aria-pressed="activeCollection === FAVORITES_COLLECTION"
        data-pos-chip-favorites
        @click="activeCollection = FAVORITES_COLLECTION"
      >
        <Icon name="lucide:star" class="size-4 text-primary" aria-hidden="true" />
        Favoritos
      </NuxtButton>
      <NuxtButton
        :size="coarsePointer ? 'xl' : 'md'"
        color="neutral"
        variant="outline"
        active-color="primary"
        active-variant="solid"
        :active="activeCollection === ''"
        class="shrink-0 whitespace-nowrap rounded-full"
        :aria-pressed="activeCollection === ''"
        @click="activeCollection = ''"
      >
        <Icon v-if="activeCollection === ''" name="lucide:check" class="size-3.5" aria-hidden="true" />
        Tudo
      </NuxtButton>
      <NuxtButton
        v-for="collection in orderedCollections"
        :key="collection.ref"
        :size="coarsePointer ? 'xl' : 'md'"
        color="neutral"
        variant="outline"
        active-color="primary"
        active-variant="solid"
        :active="activeCollection === collection.ref"
        class="shrink-0 whitespace-nowrap rounded-full"
        :aria-pressed="activeCollection === collection.ref"
        @click="activeCollection = collection.ref"
      >
        <Icon v-if="activeCollection === collection.ref" name="lucide:check" class="size-3.5" aria-hidden="true" />
        <span
          v-else
          class="size-2 shrink-0 rounded-full bg-muted-foreground"
          :style="collectionColors.get(collection.ref) ? { background: collectionColors.get(collection.ref) } : undefined"
          aria-hidden="true"
        />
        {{ collection.name }}
      </NuxtButton>
      <NuxtButton
        :size="coarsePointer ? 'xl' : 'md'"
        color="neutral"
        variant="ghost"
        active-color="primary"
        active-variant="soft"
        :active="hideUnavailable"
        class="shrink-0 whitespace-nowrap rounded-full"
        :aria-label="hideUnavailableActionLabel"
        :aria-pressed="hideUnavailable"
        :title="hideUnavailableActionLabel"
        data-pos-hide-unavailable
        @click="setHideUnavailable(!hideUnavailable)"
      >
        <Icon :name="hideUnavailable ? 'lucide:eye-off' : 'lucide:eye'" class="size-3.5" aria-hidden="true" />
        {{ hideUnavailable ? `Indisponíveis ocultos${hiddenCount ? ` (${hiddenCount})` : ""}` : "Ocultar indisponíveis" }}
      </NuxtButton>
    </div>

    <div class="@container -mx-1 px-1 md:min-h-0 md:flex-1 md:overflow-y-auto">
      <!-- Skeleton só no PRIMEIRO carregamento: um refresh de fundo com a grade
           já populada não pisca 12 tiles pulsando em cima do catálogo. -->
      <div v-if="pending && !products.length" class="grid gap-2.5" :class="densityCols">
        <UiSkeleton
          v-for="idx in 12"
          :key="idx"
          class="h-[150px] rounded-lg border"
          label="Carregando produto"
        />
      </div>
      <div
        v-else-if="!filteredProducts.length && hiddenCount > 0"
        class="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center text-muted-foreground"
        data-pos-hidden-unavailable-empty
      >
        <p>Nenhum produto disponível encontrado. {{ hiddenUnavailableLabel(hiddenCount) }}.</p>
        <UiButton variant="outline" @click="setHideUnavailable(false)">
          <Icon name="lucide:eye" class="size-4" />
          Mostrar indisponíveis
        </UiButton>
      </div>
      <div v-else-if="!filteredProducts.length" class="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
        Nenhum produto encontrado.
      </div>
      <div v-else class="grid content-start gap-2.5 pb-2" :class="densityCols">
        <template v-for="entry in entries" :key="entry.key">
          <PosProductGroupTile
            v-if="entry.kind === 'group'"
            :touch="coarsePointer"
            :group="entry.group"
            :cart-items="cartItems"
            @add="emit('add', $event)"
          />
          <PosProductTile
            v-else
            :touch="coarsePointer"
            :product="entry.product"
            :qty="productQty(entry.product.sku)"
            :disabled="entry.product.sold_out"
            @add="emit('add', $event)"
          />
        </template>
      </div>
    </div>
    <PosCodeScanner v-model:open="scannerOpen" title="Ler código do produto ou da comanda" @code="onScanned" @type="focusSearch()" />
  </section>
</template>
