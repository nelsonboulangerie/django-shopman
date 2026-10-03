<script setup lang="ts">
// Sale Workspace · product grid (spec §2.2) — image-forward grade + rail de
// categorias. Consumes the catalog Projection through `presentation/catalog`
// (favourite-ordered categories, name/code filter); price and availability are
// sealed in the Projection (price_display) and only rendered. Search and
// the active collection are grid-local presentation state. Emits `add`; the
// shell resolves the session command.
import type { POSCartItem, POSCollectionProjection, POSProductProjection } from "~/types/pos";
import { cartQtyForSku, enterTargetProduct, filterProducts, gridEntries, orderCollections } from "~/presentation/catalog";

const props = defineProps<{
  products: POSProductProjection[];
  collections: POSCollectionProjection[];
  favoriteRefs: string[];
  cartItems: POSCartItem[];
  pending: boolean;
}>();

const emit = defineEmits<{ add: [POSProductProjection] }>();

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
  { key: "roomy", label: "Ampla", icon: "lucide:square", cols: "grid-cols-2 @xl:grid-cols-3 @4xl:grid-cols-4" },
];
const DENSITY_STORAGE_KEY = "pos.productDensity";
const density = ref<Density>("cozy");
const densityCols = computed(() => DENSITIES.find((d) => d.key === density.value)?.cols ?? DENSITIES[1]!.cols);
const densityIcon = computed(() => DENSITIES.find((d) => d.key === density.value)?.icon ?? DENSITIES[1]!.icon);

onMounted(() => {
  const stored = localStorage.getItem(DENSITY_STORAGE_KEY);
  if (stored === "compact" || stored === "cozy" || stored === "roomy") density.value = stored;
});

function setDensity(value: Density) {
  density.value = value;
  if (import.meta.client) localStorage.setItem(DENSITY_STORAGE_KEY, value);
}

const orderedCollections = computed(() => orderCollections(props.collections, props.favoriteRefs));
const filteredProducts = computed(() =>
  filterProducts(props.products, { collectionRef: activeCollection.value, query: search.value }),
);

// Cartão de escolha: sem busca, produtos do mesmo `choice_group` viram um tile só
// que abre a escolha; com busca, cada produto aparece sozinho (o Enter lança).
const entries = computed(() => gridEntries(filteredProducts.value, props.products, search.value));

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
  if (!target) return;
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
  <section class="flex h-full min-h-0 flex-col gap-3">
    <div class="flex shrink-0 items-center gap-2">
      <PosSearchField ref="searchInputRef" v-model="search" kbd="F3" placeholder="Buscar produto por nome ou código" autofocus @keydown.enter.prevent="onSearchEnter" @keydown.esc.prevent="onSearchEscape" />
      <UiPopover>
        <UiPopoverTrigger as-child>
          <UiButton variant="outline" size="icon" class="size-11 shrink-0" aria-label="Densidade da grade" title="Densidade da grade">
            <Icon :name="densityIcon" class="size-5" />
          </UiButton>
        </UiPopoverTrigger>
        <UiPopoverContent align="end" class="w-44 p-1">
          <p class="px-2 py-1.5 text-xs font-medium text-muted-foreground">Densidade da grade</p>
          <button
            v-for="opt in DENSITIES"
            :key="opt.key"
            type="button"
            class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition hover:bg-accent"
            :class="density === opt.key ? 'bg-accent font-medium text-accent-foreground' : ''"
            @click="setDensity(opt.key)"
          >
            <Icon :name="opt.icon" class="size-4 shrink-0" />
            <span class="flex-1">{{ opt.label }}</span>
            <Icon v-if="density === opt.key" name="lucide:check" class="size-4 shrink-0 text-primary" />
          </button>
        </UiPopoverContent>
      </UiPopover>
    </div>

    <div class="-mx-1 flex shrink-0 gap-1.5 overflow-x-auto px-1 pb-1 no-scrollbar">
      <button
        type="button"
        class="flex h-9 shrink-0 items-center whitespace-nowrap rounded-full border px-3 text-sm font-medium transition"
        :class="activeCollection === '' ? 'border-primary bg-primary/5' : 'hover:border-primary/50 hover:bg-accent'"
        @click="activeCollection = ''"
      >
        Tudo
      </button>
      <button
        v-for="collection in orderedCollections"
        :key="collection.ref"
        type="button"
        class="flex h-9 shrink-0 items-center whitespace-nowrap rounded-full border px-3 text-sm font-medium transition"
        :class="activeCollection === collection.ref ? 'border-primary bg-primary/5' : 'hover:border-primary/50 hover:bg-accent'"
        @click="activeCollection = collection.ref"
      >
        {{ collection.name }}
      </button>
    </div>

    <div class="@container -mx-1 px-1 md:min-h-0 md:flex-1 md:overflow-y-auto">
      <!-- Skeleton só no PRIMEIRO carregamento: um refresh de fundo com a grade
           já populada não pisca 12 tiles pulsando em cima do catálogo. -->
      <div v-if="pending && !products.length" class="grid gap-2.5" :class="densityCols">
        <div v-for="idx in 12" :key="idx" class="aspect-[4/3] animate-pulse rounded-md border bg-muted" />
      </div>
      <div v-else-if="!filteredProducts.length" class="rounded-md border border-dashed p-8 text-center text-muted-foreground">
        Nenhum produto encontrado.
      </div>
      <div v-else class="grid gap-2.5" :class="densityCols">
        <template v-for="entry in entries" :key="entry.key">
          <PosProductGroupTile
            v-if="entry.kind === 'group'"
            :group="entry.group"
            :cart-items="cartItems"
            @add="emit('add', $event)"
          />
          <PosProductTile
            v-else
            :product="entry.product"
            :qty="productQty(entry.product.sku)"
            :disabled="entry.product.sold_out"
            @add="emit('add', $event)"
          />
        </template>
      </div>
    </div>
  </section>
</template>
