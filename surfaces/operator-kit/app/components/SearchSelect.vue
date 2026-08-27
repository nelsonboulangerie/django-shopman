<script setup lang="ts">
// Campo de busca com seleção — o substituto do <select> nativo quando a lista
// deixou de caber na cabeça do operador. Digitar estreita; ↑/↓ andam; Enter
// escolhe; Esc desiste sem trocar nada.
//
// Genérico de propósito: não conhece o domínio. O app traduz o que ele tem para
// SearchSelectOption e recebe de volta o `value`. A busca lê rótulo E dica, então
// quem sabe o código chega tão rápido quanto quem sabe o nome.
//
// A lista é local e inteira: nada de debounce nem de request por tecla. O filtro
// é a função pura de `presentation/searchSelect` — o componente só cuida do
// teclado, do foco e do que aparece.
import {
  filterOptions,
  highlightForValue,
  moveHighlight,
  selectedLabel,
} from "../presentation/searchSelect";
import type { SearchSelectOption } from "../types/searchSelect";

const props = withDefaults(
  defineProps<{
    options: SearchSelectOption[];
    /** Valor escolhido (v-model). Vazio = nada escolhido: o campo mostra o placeholder. */
    modelValue: string;
    placeholder?: string;
    /** Nome do campo para leitor de tela — não há rótulo visível. */
    ariaLabel?: string;
    /** Altura e fundo do campo, para casar com a tela que hospeda (ex.: "h-11 bg-card"). */
    inputClass?: string;
    emptyText?: string;
    disabled?: boolean;
  }>(),
  {
    placeholder: "Buscar",
    ariaLabel: "Buscar",
    inputClass: "h-10 bg-card",
    emptyText: "Nada encontrado",
    disabled: false,
  },
);

const emit = defineEmits<{ "update:modelValue": [string] }>();

const root = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLInputElement | null>(null);
const menuRef = ref<HTMLElement | null>(null);
const open = ref(false);
const query = ref("");
const highlighted = ref(-1);

// Um id por instância: a tela de recebimento renderiza um campo por linha, e
// aria-controls/aria-activedescendant só valem se apontarem para o listbox certo.
const uid = useId();
const listboxId = `search-select-${uid}`;
function optionId(index: number): string {
  return `${listboxId}-option-${index}`;
}

const visible = computed(() => filterOptions(props.options, query.value));
const selected = computed(() => selectedLabel(props.options, props.modelValue));

// Fechado, o campo mostra o que está escolhido; aberto, mostra o que se digita.
// O rótulo escolhido vira placeholder na abertura, para a lista abrir inteira sem
// o operador ter de apagar o texto antes de buscar outra coisa.
const fieldValue = computed(() => (open.value ? query.value : selected.value));
const fieldPlaceholder = computed(() =>
  open.value && selected.value ? selected.value : props.placeholder,
);

// A lista vai para o <body> (Teleport) com posição fixa, e não dentro da linha.
// Motivo concreto: a tabela do desktop mora num `overflow-x-auto`, e overflow-x
// declarado transforma o overflow-y em `auto` — uma lista posicionada dentro da
// célula nasce RECORTADA pela borda da tabela. Foi o que aconteceu na primeira
// versão: a lista abria cortada em cima e embaixo, inútil justamente na tela
// desktop-first do recebimento.
const MENU_MAX_HEIGHT = 256;
const MENU_MIN_HEIGHT = 96;
const MENU_GAP = 4;
const menuStyle = ref<Record<string, string>>({});

function updateMenuPosition() {
  const field = inputRef.value;
  if (!field) return;
  const rect = field.getBoundingClientRect();
  const below = window.innerHeight - rect.bottom - MENU_GAP;
  const above = rect.top - MENU_GAP;
  // Abre para cima só quando embaixo não cabe e em cima cabe mais — linha no pé
  // da tela ainda mostra a lista inteira.
  const upward = below < MENU_MIN_HEIGHT && above > below;
  const room = Math.max(MENU_MIN_HEIGHT, Math.min(MENU_MAX_HEIGHT, upward ? above : below));
  menuStyle.value = {
    position: "fixed",
    left: `${Math.round(rect.left)}px`,
    width: `${Math.round(rect.width)}px`,
    maxHeight: `${Math.round(room)}px`,
    ...(upward ?
      { bottom: `${Math.round(window.innerHeight - rect.top + MENU_GAP)}px` }
    : { top: `${Math.round(rect.bottom + MENU_GAP)}px` }),
  };
}

function scrollHighlightIntoView() {
  if (!import.meta.client) return;
  nextTick(() => {
    if (highlighted.value < 0) return;
    document.getElementById(optionId(highlighted.value))?.scrollIntoView({ block: "nearest" });
  });
}

function openList() {
  if (props.disabled || open.value) return;
  open.value = true;
  query.value = "";
  highlighted.value = highlightForValue(visible.value, props.modelValue);
  if (import.meta.client) nextTick(updateMenuPosition);
  scrollHighlightIntoView();
}

function close() {
  open.value = false;
  query.value = "";
  highlighted.value = -1;
}

function pick(option: SearchSelectOption) {
  emit("update:modelValue", option.value);
  close();
}

function onInput(event: Event) {
  if (props.disabled) return;
  // Digitar reabre a lista depois de um Enter, e nesse caminho ela ainda não foi
  // posicionada nesta abertura: reancora no campo antes de aparecer.
  const reopening = !open.value;
  open.value = true;
  query.value = (event.target as HTMLInputElement).value;
  if (reopening && import.meta.client) nextTick(updateMenuPosition);
  // Digitou: o destaque volta para o topo do que sobrou, senão Enter escolheria
  // um item que saiu da lista.
  highlighted.value = visible.value.length ? 0 : -1;
  scrollHighlightIntoView();
}

function onArrow(event: KeyboardEvent, delta: 1 | -1) {
  if (props.disabled) return;
  event.preventDefault();
  if (!open.value) {
    openList();
    return;
  }
  highlighted.value = moveHighlight(highlighted.value, delta, visible.value.length);
  scrollHighlightIntoView();
}

function onEnter(event: KeyboardEvent) {
  if (!open.value) return;
  // Só segura o Enter quando ele de fato escolhe algo — lista vazia deixa o Enter
  // seguir para o formulário, como o operador espera.
  const option = visible.value[highlighted.value];
  if (!option) return;
  event.preventDefault();
  pick(option);
}

// Esc fechado deixa passar: quem hospeda o campo (modal, gaveta) usa o mesmo Esc.
function onEscape(event: KeyboardEvent) {
  if (!open.value) return;
  event.preventDefault();
  event.stopPropagation();
  close();
}

// A lista está fora do root (Teleport), então "clicou fora" tem de olhar os dois:
// sem isso o pointerdown numa opção fecharia a lista antes do clique acontecer.
function onDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return;
  const target = event.target as Node;
  if (root.value?.contains(target)) return;
  if (menuRef.value?.contains(target)) return;
  close();
}

// Posição fixa não acompanha rolagem sozinha: enquanto a lista está aberta ela é
// recalculada. `capture` porque quem rola é a tabela, não a janela.
function bindReposition() {
  window.addEventListener("scroll", updateMenuPosition, true);
  window.addEventListener("resize", updateMenuPosition);
}
function unbindReposition() {
  window.removeEventListener("scroll", updateMenuPosition, true);
  window.removeEventListener("resize", updateMenuPosition);
}

watch(open, (isOpen) => {
  if (!import.meta.client) return;
  if (isOpen) bindReposition();
  else unbindReposition();
});

onMounted(() => document.addEventListener("pointerdown", onDocumentPointerDown));
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown);
  unbindReposition();
});

defineExpose({ focus: () => inputRef.value?.focus() });
</script>

<template>
  <div ref="root" class="relative">
    <Icon
      name="lucide:search"
      class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
    />
    <input
      ref="inputRef"
      type="text"
      role="combobox"
      autocomplete="off"
      aria-autocomplete="list"
      :class="[
        inputClass,
        'w-full rounded-md border border-border pl-8 pr-8 text-sm font-medium',
        'outline-none focus:ring-1 focus:ring-ring',
        disabled ? 'cursor-not-allowed opacity-60' : '',
      ]"
      :value="fieldValue"
      :placeholder="fieldPlaceholder"
      :disabled="disabled"
      :aria-label="ariaLabel"
      :aria-expanded="open"
      :aria-controls="listboxId"
      :aria-activedescendant="open && highlighted >= 0 ? optionId(highlighted) : undefined"
      @focus="openList"
      @click="openList"
      @input="onInput"
      @keydown.down="onArrow($event, 1)"
      @keydown.up="onArrow($event, -1)"
      @keydown.enter="onEnter"
      @keydown.esc="onEscape"
      @keydown.tab="close"
    />
    <Icon
      :name="open ? 'lucide:chevron-up' : 'lucide:chevron-down'"
      class="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
    />

    <Teleport to="body">
      <div
        v-if="open"
        :id="listboxId"
        ref="menuRef"
        role="listbox"
        :aria-label="ariaLabel"
        :style="menuStyle"
        class="z-40 overflow-auto rounded-md border border-border bg-card p-1 shadow-lg"
      >
        <button
          v-for="(option, index) in visible"
          :id="optionId(index)"
          :key="option.value"
          type="button"
          role="option"
          :aria-selected="index === highlighted"
          class="flex w-full items-center justify-between gap-2 rounded px-2.5 py-2 text-left transition hover:bg-accent"
          :class="index === highlighted ? 'bg-accent' : ''"
          @mousemove="highlighted = index"
          @mousedown.prevent
          @click="pick(option)"
        >
          <span class="min-w-0">
            <span class="block truncate text-sm">{{ option.label }}</span>
            <span v-if="option.hint" class="block truncate text-xs text-muted-foreground">{{ option.hint }}</span>
          </span>
          <Icon
            v-if="option.value === modelValue"
            name="lucide:check"
            class="size-4 shrink-0 text-primary"
          />
        </button>
        <p v-if="!visible.length" class="px-2.5 py-2 text-sm text-muted-foreground" role="status">
          {{ emptyText }}
        </p>
      </div>
    </Teleport>
  </div>
</template>
