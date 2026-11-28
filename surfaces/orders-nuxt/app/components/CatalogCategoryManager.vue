<script setup lang="ts">
import { formatClock } from "../../../operator-kit/app/presentation/clock";
import type {
  CatalogBindingReviewProjection,
  CatalogRemoteCategory,
} from "~/generated/ordersContract";

const props = defineProps<{
  board: CatalogBindingReviewProjection;
  busy: boolean;
  stale: boolean;
  change: (body: Record<string, unknown>) => Promise<boolean>;
}>();

const editing = ref<Record<string, "name" | "index">>({});
const names = ref<Record<string, string>>({});
const positions = ref<Record<string, number>>({});
const mappings = ref<Record<string, string>>({});
// A categoria do iFood nasce de uma coleção da casa (o iFood é reflexo do
// Catálogo): mesmo nome, já ligada a ela. Não há nome digitado aqui.
async function createFromCollection(collectionRef: string) {
  if (blocked.value) return;
  if (
    await props.change({
      action: "create",
      catalog_ref: props.board.catalog_ref,
      collection_ref: collectionRef,
    })
  )
    stamp(`collection:${collectionRef}`);
}

// Selo no próprio gesto: "Gravado no iFood às 13h55", por cartão.
const confirmed = ref<Record<string, string>>({});
function stamp(key: string) {
  const at = formatClock(new Date());
  confirmed.value = { ...confirmed.value, [key]: `Gravado no iFood às ${at}` };
}

const blocked = computed(
  () => props.busy || props.stale || !props.board.category_action.enabled,
);

function start(category: CatalogRemoteCategory, field: "name" | "index") {
  editing.value[category.ref] = field;
  names.value[category.ref] = category.name;
  positions.value[category.ref] = category.index;
}

function cancel(categoryRef: string) {
  const next = { ...editing.value };
  Reflect.deleteProperty(next, categoryRef);
  editing.value = next;
}

async function saveName(category: CatalogRemoteCategory) {
  const name = names.value[category.ref]?.trim();
  if (!name || blocked.value) return;
  if (
    await props.change({
      action: "rename",
      catalog_ref: props.board.catalog_ref,
      category_ref: category.ref,
      name,
    })
  ) {
    stamp(category.ref);
    cancel(category.ref);
  }
}

async function savePosition(category: CatalogRemoteCategory) {
  const index = Number(positions.value[category.ref]);
  if (!Number.isInteger(index) || index < 0 || blocked.value) return;
  if (
    await props.change({
      action: "reorder",
      catalog_ref: props.board.catalog_ref,
      category_ref: category.ref,
      index,
    })
  ) {
    stamp(category.ref);
    cancel(category.ref);
  }
}

function selectedCategory(collectionRef: string, current: string) {
  return mappings.value[collectionRef] ?? current;
}

function cancelMapping(collectionRef: string) {
  const next = { ...mappings.value };
  Reflect.deleteProperty(next, collectionRef);
  mappings.value = next;
}

async function saveMapping(collectionRef: string, current: string) {
  const categoryRef = selectedCategory(collectionRef, current);
  if (!categoryRef || categoryRef === current || blocked.value) return;
  if (
    await props.change({
      action: "map",
      catalog_ref: props.board.catalog_ref,
      category_ref: categoryRef,
      collection_ref: collectionRef,
    })
  ) {
    stamp(`collection:${collectionRef}`);
    const next = { ...mappings.value };
    Reflect.deleteProperty(next, collectionRef);
    mappings.value = next;
  }
}
</script>

<template>
  <section aria-label="Categorias do iFood">
    <NuxtCard variant="outline">
      <div class="space-y-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <h2 class="op-title">Categorias do iFood</h2>
          <NuxtBadge
            color="neutral"
            :label="`${board.categories.length} categorias`"
          />
        </div>

        <NuxtAlert
          v-if="board.categories_error"
          color="warning"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="A lista atual não pôde ser confirmada"
          :description="board.categories_error"
        />

        <NuxtEmpty
          v-if="!board.categories.length"
          icon="i-lucide-list-tree"
          title="Nenhuma categoria disponível"
          description="Carregue uma captura do catálogo e atualize a página."
        />

        <div
          v-else
          class="grid items-stretch gap-3 md:grid-cols-2 xl:grid-cols-3"
        >
          <NuxtCard
            v-for="category in board.categories"
            :key="category.ref"
            variant="soft"
            class="h-full"
            as="article"
            :aria-label="category.name"
          >
            <div class="flex h-full flex-col gap-3">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <h3 class="break-words font-semibold">{{ category.name }}</h3>
                  <p class="text-sm text-muted-foreground">
                    Posição {{ category.index }} ·
                    {{ category.mapped_collections }}
                    {{
                      category.mapped_collections === 1
                        ? "coleção ligada"
                        : "coleções ligadas"
                    }}
                  </p>
                </div>
                <NuxtBadge
                  color="neutral"
                  :label="
                    category.status === 'AVAILABLE'
                      ? 'Disponível'
                      : 'Indisponível'
                  "
                />
              </div>
              <NuxtBadge
                v-if="confirmed[category.ref]"
                color="success"
                icon="i-lucide-circle-check"
                class="self-start"
                :label="confirmed[category.ref]"
                data-category-confirmed
              />

              <div v-if="editing[category.ref] === 'name'" class="space-y-2">
                <NuxtFormField label="Nome da categoria">
                  <NuxtInput v-model="names[category.ref]" class="max-w-sm" />
                </NuxtFormField>
                <div class="flex flex-wrap gap-2">
                  <NuxtButton
                    label="Aplicar"
                    :loading="busy"
                    :disabled="blocked || !names[category.ref]?.trim()"
                    @click="saveName(category)"
                  />
                  <NuxtButton
                    label="Cancelar"
                    color="neutral"
                    variant="ghost"
                    :disabled="busy"
                    @click="cancel(category.ref)"
                  />
                </div>
              </div>

              <div
                v-else-if="editing[category.ref] === 'index'"
                class="space-y-2"
              >
                <NuxtFormField label="Posição na lista">
                  <NuxtInput
                    v-model.number="positions[category.ref]"
                    class="max-w-32"
                    type="number"
                    min="0"
                    max="9999"
                  />
                </NuxtFormField>
                <div class="flex flex-wrap gap-2">
                  <NuxtButton
                    label="Aplicar"
                    :loading="busy"
                    :disabled="blocked"
                    @click="savePosition(category)"
                  />
                  <NuxtButton
                    label="Cancelar"
                    color="neutral"
                    variant="ghost"
                    :disabled="busy"
                    @click="cancel(category.ref)"
                  />
                </div>
              </div>

              <div v-else class="mt-auto flex flex-wrap gap-2">
                <NuxtButton
                  label="Renomear"
                  icon="i-lucide-pencil"
                  color="neutral"
                  variant="ghost"
                  :disabled="blocked"
                  @click="start(category, 'name')"
                />
                <NuxtButton
                  label="Alterar posição"
                  icon="i-lucide-list-ordered"
                  color="neutral"
                  variant="ghost"
                  :disabled="blocked"
                  @click="start(category, 'index')"
                />
              </div>
            </div>
          </NuxtCard>
        </div>

        <div
          v-if="board.collections.length && board.categories.length"
          class="space-y-3"
        >
          <div>
            <h3 class="font-semibold">Coleções da casa</h3>
            <p class="text-sm text-muted-foreground">
              Escolha a categoria do iFood para cada coleção publicada.
            </p>
          </div>
          <div class="grid items-stretch gap-3 md:grid-cols-2">
            <NuxtCard
              v-for="collection in board.collections"
              :key="collection.ref"
              variant="soft"
              class="h-full"
            >
              <div class="flex h-full flex-col gap-3">
                <div>
                  <p class="font-medium">{{ collection.name }}</p>
                  <p class="text-sm text-muted-foreground">
                    {{
                      collection.category_name ||
                      "Ainda sem categoria escolhida"
                    }}
                  </p>
                </div>
                <NuxtBadge
                  v-if="confirmed[`collection:${collection.ref}`]"
                  color="success"
                  icon="i-lucide-circle-check"
                  class="self-start"
                  :label="confirmed[`collection:${collection.ref}`]"
                  data-collection-confirmed
                />
                <NuxtButton
                  v-if="!collection.category_ref"
                  label="Criar no iFood com este nome"
                  icon="i-lucide-plus"
                  color="neutral"
                  variant="outline"
                  class="self-start"
                  :loading="busy"
                  :disabled="blocked"
                  data-category-from-collection
                  @click="createFromCollection(collection.ref)"
                />
                <NuxtFormField
                  :label="
                    collection.category_ref
                      ? 'Categoria no iFood'
                      : 'Ou escolha uma categoria que já existe'
                  "
                >
                  <NuxtSelect
                    class="w-full"
                    :model-value="
                      selectedCategory(
                        collection.ref,
                        collection.category_ref,
                      ) || undefined
                    "
                    :items="
                      board.categories.map((category) => ({
                        label: category.name,
                        value: category.ref,
                      }))
                    "
                    placeholder="Escolha uma categoria"
                    :disabled="blocked"
                    @update:model-value="
                      mappings[collection.ref] = String($event)
                    "
                  />
                </NuxtFormField>
                <div
                  v-if="
                    selectedCategory(
                      collection.ref,
                      collection.category_ref,
                    ) !== collection.category_ref
                  "
                  class="mt-auto flex flex-wrap gap-2"
                >
                  <NuxtButton
                    label="Aplicar"
                    :loading="busy"
                    :disabled="blocked"
                    @click="
                      saveMapping(collection.ref, collection.category_ref)
                    "
                  />
                  <NuxtButton
                    label="Cancelar"
                    color="neutral"
                    variant="ghost"
                    :disabled="busy"
                    @click="cancelMapping(collection.ref)"
                  />
                </div>
              </div>
            </NuxtCard>
          </div>
        </div>
      </div>
    </NuxtCard>
  </section>
</template>
