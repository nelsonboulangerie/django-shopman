<script setup lang="ts">
defineProps<{ open: boolean }>();
defineEmits<{ "update:open": [boolean] }>();

const groups: Array<{
  title: string;
  items: Array<{ keys: string[]; label: string }>;
}> = [
  {
    title: "Em toda a Produção",
    items: [
      { keys: ["Alt+1"], label: "Planejamento" },
      { keys: ["Alt+2"], label: "Preparação" },
      { keys: ["Alt+3"], label: "Produção" },
      { keys: ["Alt+4"], label: "Expedição" },
      { keys: ["/"], label: "Buscar por produto, SKU ou receita" },
      { keys: ["R"], label: "Atualizar os dados da tela" },
      { keys: ["?"], label: "Abrir esta ajuda" },
    ],
  },
  {
    title: "Listas e diálogos",
    items: [
      { keys: ["Tab", "Shift+Tab"], label: "Percorrer os comandos" },
      { keys: ["Enter", "Espaço"], label: "Acionar o comando em foco" },
      { keys: ["Esc"], label: "Fechar ou voltar sem confirmar" },
      { keys: ["Enter"], label: "Confirmar uma quantidade digitada" },
    ],
  },
  {
    title: "QC e timer",
    items: [
      { keys: ["0–9"], label: "Digitar quantidade ou minutos" },
      { keys: ["Backspace"], label: "Apagar o último dígito" },
      { keys: ["C", "Delete"], label: "Limpar o número" },
      { keys: ["Enter numérico"], label: "Confirmar pelo numpad físico" },
      { keys: ["Enter"], label: "Iniciar o timer; quando tocar, marcar Visto" },
    ],
  },
];
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>Atalhos do teclado</UiDialogTitle>
        <UiDialogDescription>
          Toque e teclado executam os mesmos comandos. Os atalhos pausam sob
          bloqueio, confirmação ou edição de texto.
        </UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
        <section
          v-for="group in groups"
          :key="group.title"
          class="grid gap-1.5"
        >
          <p
            class="text-xs font-medium uppercase tracking-wide text-muted-foreground"
          >
            {{ group.title }}
          </p>
          <ul class="grid gap-1">
            <li
              v-for="item in group.items"
              :key="item.label"
              class="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm odd:bg-muted/40"
            >
              <span class="min-w-0">{{ item.label }}</span>
              <span class="flex shrink-0 items-center gap-1">
                <kbd
                  v-for="key in item.keys"
                  :key="key"
                  class="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground"
                  aria-hidden="true"
                  >{{ key }}</kbd
                >
              </span>
            </li>
          </ul>
        </section>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
