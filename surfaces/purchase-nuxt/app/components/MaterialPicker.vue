<script setup lang="ts">
import type { Material } from "~/types/purchase";

/**
 * Escolher o insumo com BUSCA, e não rolando uma lista de dezenas.
 *
 * Um `<select>` nativo com 56 insumos é castigo no celular: o operador tem a
 * caixa na mão, o entregador esperando, e precisa achar "Manteiga francesa"
 * arrastando. Aqui ele digita "mant" e acaba.
 *
 * Sem biblioteca de componente (convenção da casa): é um botão que abre um
 * painel com campo de texto e a lista filtrada. A busca ignora acento e casa
 * tanto pelo nome quanto pelo SKU — o operador às vezes lê o código da etiqueta.
 *
 * O painel é um combobox de verdade: o campo de busca tem `role="combobox"`, a
 * lista tem `role="listbox"`, e o item em destaque é apontado por
 * `aria-activedescendant`. Assim ↑ ↓ Home End Enter Esc andam na lista sem
 * tirar o cursor de dentro do campo, que é onde o operador está digitando.
 *
 * ⚠️ Quem usa este componente NÃO pode envolvê-lo num `<label>`. Um `<label>`
 * sem `for` adota o primeiro controle rotulável de dentro — aqui, o botão que
 * abre o painel — e reencaminha para ele todo clique que caia em parte NÃO
 * interativa da label, inclusive o véu de "fechar ao tocar fora" logo abaixo.
 * O painel fechava e reabria no MESMO clique: dropdown que não fecha nunca e
 * escolha que parecia ignorada. Rotule com um `<span id>` e passe `labelledBy`.
 */
const props = defineProps<{
  materials: Material[];
  modelValue: string;
  placeholder?: string;
  /** `id` do texto que nomeia o campo. Ver o aviso acima: nunca um `<label>`. */
  labelledBy?: string;
}>();

const emit = defineEmits<{ "update:modelValue": [sku: string] }>();

const open = ref(false);
const query = ref("");
/** Item em destaque na lista. Só significa algo com o painel aberto. */
const active = ref(0);
const search = useTemplateRef<HTMLInputElement>("search");
const trigger = useTemplateRef<HTMLButtonElement>("trigger");
const list = useTemplateRef<HTMLUListElement>("list");

const uid = useId();
const listId = `${uid}-list`;
const valueId = `${uid}-value`;
const optionId = (index: number) => `${uid}-option-${index}`;

const selected = computed(() => props.materials.find((item) => item.sku === props.modelValue) ?? null);

/** "Insumo, Manteiga francesa" — o rótulo do campo E o que está escolhido. */
const triggerLabelledBy = computed(() => (props.labelledBy ? `${props.labelledBy} ${valueId}` : valueId));

/** Sem acento e sem caixa: "manteiga" acha "Manteiga", "acucar" acha "Açúcar". */
function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

const results = computed(() => {
  const needle = fold(query.value.trim());
  if (!needle) return props.materials;
  const terms = needle.split(/\s+/);
  return props.materials.filter((material) => {
    const haystack = fold(`${material.name} ${material.sku} ${material.category}`);
    return terms.every((term) => haystack.includes(term));
  });
});

/** O destaque nunca aponta para fora da lista que está na tela. */
const activeIndex = computed(() => {
  if (!results.value.length) return -1;
  return Math.min(Math.max(active.value, 0), results.value.length - 1);
});

const activeId = computed(() => (activeIndex.value < 0 ? undefined : optionId(activeIndex.value)));

// Filtrou de novo: o destaque volta para o primeiro resultado, que é o que o
// Enter vai pegar.
watch(query, () => {
  active.value = 0;
});

async function scrollActiveIntoView() {
  await nextTick();
  const option = list.value?.querySelector<HTMLElement>('[data-active="true"]');
  if (option && typeof option.scrollIntoView === "function") option.scrollIntoView({ block: "nearest" });
}

function move(delta: number) {
  const total = results.value.length;
  if (!total) return;
  active.value = (activeIndex.value + delta + total) % total;
  void scrollActiveIntoView();
}

async function openPicker() {
  open.value = true;
  query.value = "";
  await nextTick();
  // Depois do `nextTick` porque o `watch(query)` acima já rodou: abrir com um
  // insumo escolhido deixa o destaque EM CIMA dele, não no primeiro da lista.
  active.value = Math.max(0, results.value.findIndex((material) => material.sku === props.modelValue));
  search.value?.focus();
  void scrollActiveIntoView();
}

function closePicker(returnFocus = true) {
  if (!open.value) return;
  open.value = false;
  // O foco volta para o botão: quem abriu pelo teclado não é largado no corpo
  // da página.
  if (returnFocus) void nextTick(() => trigger.value?.focus());
}

function choose(sku: string) {
  emit("update:modelValue", sku);
  closePicker();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    move(1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    move(-1);
  } else if (event.key === "Home") {
    event.preventDefault();
    active.value = 0;
    void scrollActiveIntoView();
  } else if (event.key === "End") {
    event.preventDefault();
    active.value = results.value.length - 1;
    void scrollActiveIntoView();
  } else if (event.key === "Enter") {
    event.preventDefault();
    const material = results.value[activeIndex.value];
    if (material) choose(material.sku);
  } else if (event.key === "Escape") {
    // Fecha SÓ o painel; sem o stop, o Esc atravessaria para quem estiver por
    // cima (modal, gaveta) e fecharia a tela inteira junto.
    event.preventDefault();
    event.stopPropagation();
    closePicker();
  } else if (event.key === "Tab") {
    closePicker(false);
  }
}
</script>

<template>
  <div class="relative">
    <button
      ref="trigger"
      type="button"
      class="flex h-11 w-full items-center justify-between gap-2 rounded-md border border-border bg-card px-3 text-left text-sm text-foreground"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-labelledby="triggerLabelledBy"
      @click="openPicker"
    >
      <span :id="valueId" class="truncate" :class="selected ? 'font-medium' : 'text-muted-foreground'">
        {{ selected?.name ?? (placeholder ?? "Escolher insumo") }}
      </span>
      <Icon name="lucide:search" class="size-4 shrink-0 text-muted-foreground" />
    </button>

    <!-- Fecha ao tocar fora. Um `fixed` inerte cobrindo a tela é mais confiável
         no celular que ouvir clique no documento, que briga com o scroll.
         O `.prevent` diz que o clique foi CONSUMIDO pela dispensa: sem ele, um
         `<label>` ancestral rodaria seu comportamento de ativação sobre o botão
         que abre e reabriria o painel no mesmo gesto. -->
    <div v-if="open" class="fixed inset-0 z-40" @click.prevent="closePicker()" />

    <div v-if="open" class="absolute inset-x-0 top-full z-50 mt-1 rounded-md border border-border bg-card shadow-lg">
      <div class="border-b border-border p-2">
        <input
          ref="search"
          v-model="query"
          type="search"
          class="h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
          placeholder="Buscar insumo"
          role="combobox"
          autocomplete="off"
          aria-autocomplete="list"
          aria-expanded="true"
          :aria-controls="listId"
          :aria-activedescendant="activeId"
          :aria-labelledby="labelledBy"
          @keydown="onKeydown"
        />
      </div>

      <p v-if="!results.length" class="px-3 py-3 text-sm text-muted-foreground">Nenhum insumo com "{{ query }}".</p>
      <ul
        v-else
        :id="listId"
        ref="list"
        role="listbox"
        :aria-labelledby="labelledBy"
        class="max-h-64 overflow-y-auto py-1"
      >
        <li
          v-for="(material, index) in results"
          :id="optionId(index)"
          :key="material.sku"
          role="option"
          :aria-selected="material.sku === modelValue"
          :data-active="index === activeIndex"
          class="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2.5 text-left text-sm"
          :class="[
            index === activeIndex ? 'bg-accent' : '',
            material.sku === modelValue ? 'font-semibold text-primary' : '',
          ]"
          @pointerdown.prevent
          @click="choose(material.sku)"
          @pointerenter="active = index"
        >
          <span class="min-w-0">
            <span class="block truncate">{{ material.name }}</span>
            <span class="block truncate text-xs text-muted-foreground">{{ material.sku }} · conta em {{ material.unit }}</span>
          </span>
          <Icon v-if="material.sku === modelValue" name="lucide:check" class="size-4 shrink-0" />
        </li>
      </ul>
    </div>
  </div>
</template>
