<script setup lang="ts">
import type {
  ProductDetailProjection,
  ProductCollectionLink,
  ProductListingLink,
} from "~/types/catalog";

const props = defineProps<{
  detail: ProductDetailProjection;
  busy: boolean;
  saveCollections: (rows: ProductCollectionLink[]) => Promise<boolean>;
  saveListing: (
    link: ProductListingLink,
    patch: {
      price_q: number;
      min_qty: string;
      is_published: boolean;
      is_sellable: boolean;
    },
  ) => Promise<boolean>;
}>();
const emit = defineEmits<{
  "dirty-change": [dirty: boolean];
  "saving-change": [saving: boolean];
}>();
const editing = ref<string | null>(null);
const saving = ref(false);
watch(saving, (value) => emit("saving-change", value));
const pending = computed(() => props.busy || saving.value);
watch(editing, (value) => emit("dirty-change", value !== null));
const price = ref("");
const minimum = ref("");
const published = ref(false);
const sellable = ref(false);
const localError = ref("");
const collections = ref<ProductCollectionLink[]>([]);
const chooseOpen = ref(false);
function editCollections() {
  collections.value = (props.detail.collections ?? []).map((row) => ({
    ...row,
  }));
  editing.value = "collections";
  localError.value = "";
}
function choose(ref: string) {
  collections.value.push({ ref, is_primary: false, sort_order: 0 });
  chooseOpen.value = false;
}
const available = computed(() =>
  (props.detail.collection_choices ?? []).filter(
    (row) => !collections.value.some((item) => item.ref === row.ref),
  ),
);
function editListing(link: ProductListingLink) {
  editing.value = link.surface_ref;
  price.value = (link.price_q / 100).toFixed(2).replace(".", ",");
  minimum.value = link.min_qty.replace(".", ",");
  published.value = link.is_published;
  sellable.value = link.is_sellable;
  localError.value = "";
}
async function applyListing(link: ProductListingLink) {
  const amount = Number(price.value.replace(",", "."));
  const qty = minimum.value.replace(",", ".");
  if (
    !/^\d+(?:[.,]\d{1,2})?$/.test(price.value) ||
    !Number.isSafeInteger(Math.round(amount * 100)) ||
    !/^\d+(?:\.\d{1,3})?$/.test(qty) ||
    Number(qty) <= 0
  ) {
    localError.value =
      "Informe o preço em reais e uma quantidade mínima positiva, com até três casas decimais.";
    return;
  }
  saving.value = true;
  try {
    if (
      await props.saveListing(link, {
        price_q: Math.round(amount * 100),
        min_qty: qty,
        is_published: published.value,
        is_sellable: sellable.value,
      })
    )
      editing.value = null;
  } finally {
    saving.value = false;
  }
}
async function applyCollections() {
  saving.value = true;
  try {
    if (await props.saveCollections(collections.value)) editing.value = null;
  } finally {
    saving.value = false;
  }
}
const collectionName = (ref: string) =>
  props.detail.collection_choices?.find((row) => row.ref === ref)?.name ??
  "Coleção indisponível";
</script>

<template>
  <section class="space-y-4" aria-label="Vínculos">
    <h3 class="text-lg font-semibold">Vínculos</h3>
    <p class="text-sm text-muted">
      Preço, quantidade mínima, publicação e venda valem somente no canal
      editado. Salvar uma coleção não publica o produto em nenhum canal.
    </p>
    <NuxtCard variant="outline">
      <div class="space-y-3">
        <h4 class="font-medium">Canais de venda</h4>
        <p v-if="!detail.listing_links?.length" class="text-sm text-muted">
          Este produto ainda não pertence a um canal de venda.
        </p>
        <div
          v-for="link in detail.listing_links"
          :key="link.surface_ref"
          class="rounded-lg bg-muted p-3 space-y-3"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="font-medium">{{ link.name }}</span>
            <NuxtButton
              v-if="editing !== link.surface_ref"
              :label="
                link.in_listing === false ? 'Incluir no canal' : 'Editar canal'
              "
              variant="ghost"
              color="neutral"
              :disabled="pending || editing !== null || !link.action.enabled"
              @click="editListing(link)"
            />
          </div>
          <p v-if="link.action.reason" class="text-sm text-muted">
            {{ link.action.reason }}
          </p>
          <p v-if="link.in_listing === false" class="text-sm text-muted">
            Ainda não incluído neste canal. O preço inicial sugerido é o preço
            base do produto.
          </p>
          <template v-if="editing === link.surface_ref">
            <div class="grid grid-cols-2 gap-3">
              <NuxtFormField label="Preço (R$)"
                ><NuxtInput
                  v-model="price"
                  :disabled="pending"
                  inputmode="decimal"
                  class="w-full"
              /></NuxtFormField>
              <NuxtFormField
                label="Quantidade mínima"
                :error="localError || undefined"
                ><NuxtInput
                  v-model="minimum"
                  :disabled="pending"
                  inputmode="decimal"
                  class="w-full"
              /></NuxtFormField>
              <NuxtCheckbox
                v-model="published"
                :disabled="pending"
                label="Publicado neste canal"
              />
              <NuxtCheckbox
                v-model="sellable"
                :disabled="pending"
                label="Vendável neste canal"
              />
            </div>

            <div class="flex gap-2">
              <NuxtButton
                label="Aplicar"
                :loading="pending"
                @click="applyListing(link)"
              /><NuxtButton
                label="Cancelar"
                variant="ghost"
                color="neutral"
                :disabled="pending"
                @click="editing = null"
              />
            </div>
          </template>
          <p v-else class="text-sm">
            {{
              (link.price_q / 100).toLocaleString("pt-BR", {
                style: "currency",
                currency: "BRL",
              })
            }}
            · Mínimo {{ Number(link.min_qty).toLocaleString("pt-BR") }} ·
            {{ link.is_published ? "Publicado" : "Oculto" }} ·
            {{ link.is_sellable ? "Vendável" : "Venda pausada" }}
          </p>
          <details class="text-xs text-muted">
            <summary>Identificação do canal</summary>
            {{ link.surface_ref }}
          </details>
        </div>
      </div>
    </NuxtCard>
    <NuxtCard variant="outline">
      <div class="space-y-3">
        <div class="flex items-center justify-between gap-2">
          <h4 class="font-medium">Coleções</h4>
          <NuxtButton
            v-if="editing !== 'collections'"
            label="Editar coleções"
            variant="ghost"
            color="neutral"
            :disabled="pending || editing !== null"
            @click="editCollections"
          />
        </div>
        <template v-if="editing === 'collections'">
          <div
            v-for="(row, index) in collections"
            :key="row.ref"
            class="rounded-lg bg-muted p-3 space-y-2"
          >
            <div class="flex items-center justify-between gap-2">
              <span>{{ collectionName(row.ref) }}</span
              ><NuxtButton
                label="Retirar"
                variant="ghost"
                color="neutral"
                :disabled="pending"
                @click="collections.splice(index, 1)"
              />
            </div>
            <NuxtCheckbox
              :model-value="row.is_primary"
              :disabled="pending"
              label="Coleção primária"
              @update:model-value="
                (value) =>
                  collections.forEach(
                    (item) =>
                      (item.is_primary = item === row && Boolean(value)),
                  )
              "
            />
            <NuxtFormField label="Ordem do produto nesta coleção"
              ><NuxtInput
                v-model.number="row.sort_order"
                :disabled="pending"
                type="number"
                :min="0"
            /></NuxtFormField>
          </div>
          <NuxtButton
            label="Incluir coleção"
            variant="outline"
            color="neutral"
            :disabled="pending || !available.length"
            @click="chooseOpen = true"
          />
          <div class="flex gap-2">
            <NuxtButton
              label="Aplicar"
              :loading="pending"
              @click="applyCollections"
            /><NuxtButton
              label="Cancelar"
              variant="ghost"
              color="neutral"
              :disabled="pending"
              @click="editing = null"
            />
          </div>
        </template>
        <template v-else
          ><p v-if="!detail.collections?.length" class="text-sm text-muted">
            Sem coleção manual.
          </p>
          <p v-for="row in detail.collections" :key="row.ref" class="text-sm">
            {{ collectionName(row.ref) }}
            <NuxtBadge v-if="row.is_primary" color="neutral"
              >Primária</NuxtBadge
            >
            · Ordem {{ row.sort_order }}
          </p></template
        >
      </div>
    </NuxtCard>
    <NuxtModal
      v-model:open="chooseOpen"
      title="Incluir coleção"
      description="Escolha uma coleção manual. A inclusão será gravada ao aplicar."
    >
      <template #body
        ><div class="flex flex-col items-start gap-2">
          <NuxtButton
            v-for="choice in available"
            :key="choice.ref"
            :label="`${choice.name}${choice.is_active ? '' : ' (Arquivado)'}`"
            variant="ghost"
            color="neutral"
            @click="choose(choice.ref)"
          /></div
      ></template>
    </NuxtModal>
  </section>
</template>
