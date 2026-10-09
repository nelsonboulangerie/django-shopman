<script setup lang="ts">
import type { ReadMetadata } from "~/types/readMetadata";
import ActionList from "~/components/ActionList.vue";
import {
  EXIT_SELECTION_LABEL,
  SORT_OPTIONS,
  type SortKey,
  type ViewMode,
} from "~/presentation/board";

const props = withDefaults(
  defineProps<{
    metadata?: ReadMetadata | null;
    failed?: boolean;
    pending?: boolean;
    sort: SortKey;
    viewMode: ViewMode;
    soundOn: boolean;
    soundBlocked: boolean;
    attentionPending: boolean;
    selecting: boolean;
    full?: boolean;
    canShowAll?: boolean;
    queueAvailable?: boolean;
    mode?: "dropdown" | "panel";
  }>(),
  { mode: "panel" },
);

const emit = defineEmits<{
  refresh: [];
  acknowledge: [];
  select: [];
  sort: [key: SortKey];
  view: [mode: ViewMode];
  sound: [];
  export: [];
  print: [];
  showAll: [];
}>();

const items = computed(() => {
  const primary = [
    {
      label: "Atualizar",
      icon: "i-lucide-refresh-cw",
      kbds: ["R"],
      loading: props.pending,
      onSelect: () => emit("refresh"),
    },
    ...(props.attentionPending
      ? [
          {
            label: "Visto",
            icon: "i-lucide-check",
            onSelect: () => emit("acknowledge"),
          },
        ]
      : []),
    ...(props.full
      ? [
          {
            label:
              props.soundOn && props.soundBlocked
                ? "Som bloqueado: ativar"
                : props.soundOn
                  ? "Som ligado"
                  : "Som desligado",
            icon: props.soundOn ? "i-lucide-volume-2" : "i-lucide-volume-x",
            onSelect: () => emit("sound"),
          },
        ]
      : []),
    ...(props.canShowAll
      ? [
          {
            label: "Mostrar as 3 colunas",
            icon: "i-lucide-columns-3",
            onSelect: () => emit("showAll"),
          },
        ]
      : []),
    ...(!props.full
      ? [
          {
            label:
              props.viewMode === "board"
                ? props.queueAvailable
                  ? "Voltar à grade"
                  : "Voltar à lista"
                : "Ver em colunas",
            icon: "i-lucide-columns-3",
            kbds: ["V"],
            onSelect: () =>
              emit(
                "view",
                props.viewMode === "board"
                  ? props.queueAvailable
                    ? "queue"
                    : "table"
                  : "board",
              ),
          },
        ]
      : []),
    {
      label: props.selecting ? EXIT_SELECTION_LABEL : "Selecionar pedidos",
      icon: "i-lucide-list-checks",
      onSelect: () => emit("select"),
    },
  ];

  const full = props.full
    ? [
        { type: "label" as const, label: "Ordenar" },
        ...SORT_OPTIONS.map((option) => ({
          label: option.label,
          icon:
            props.sort === option.key
              ? "i-lucide-check"
              : "i-lucide-arrow-up-down",
          onSelect: () => emit("sort", option.key),
        })),
        { type: "label" as const, label: "Ver como" },
        ...(props.queueAvailable
          ? [
              {
                label: "Grade",
                icon:
                  props.viewMode === "queue"
                    ? "i-lucide-check"
                    : "i-lucide-layout-grid",
                onSelect: () => emit("view", "queue"),
              },
            ]
          : []),
        {
          label: "Colunas",
          icon:
            props.viewMode === "board"
              ? "i-lucide-check"
              : "i-lucide-columns-3",
          onSelect: () => emit("view", "board"),
        },
        {
          label: "Lista",
          icon: props.viewMode === "table" ? "i-lucide-check" : "i-lucide-list",
          onSelect: () => emit("view", "table"),
        },
      ]
    : [];

  return [
    [{ type: "label" as const, slot: "freshness", label: "Leitura da fila" }],
    primary,
    ...(full.length ? [full] : []),
    [
      {
        label: "Exportar CSV",
        icon: "i-lucide-download",
        onSelect: () => emit("export"),
      },
      {
        label: "Imprimir fila",
        icon: "i-lucide-printer",
        onSelect: () => emit("print"),
      },
    ],
  ];
});

</script>

<template>
  <OperatorMoreMenu
    v-if="mode === 'dropdown'"
    :items="items"
    label="Mais ações da fila"
    data-board-more
  >
    <template #freshness>
      <ReadFreshness inline :metadata="metadata" :failed="failed" />
    </template>
  </OperatorMoreMenu>

  <div v-else data-board-menu>
    <ReadFreshness :metadata="metadata" :failed="failed" />
    <ActionList :items="items" aria-label="Ações da fila" />
  </div>
</template>
