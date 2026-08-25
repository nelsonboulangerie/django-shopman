<script setup lang="ts">
// Descoberta de atalhos: um overlay calmo que LISTA o que o teclado físico faz
// no PDV. Abre pela tecla "?" (o shell é o dono do atalho) e por um botão
// discreto no cabeçalho. Só lista — quem executa é o handler global da página.
defineProps<{ open: boolean }>();
defineEmits<{ "update:open": [boolean] }>();

const groups: Array<{ title: string; items: Array<{ keys: string[]; label: string }> }> = [
  {
    title: "Em toda a venda",
    items: [
      { keys: ["F2"], label: "Ir para as comandas (foca a referência)" },
      { keys: ["F3", "/"], label: "Buscar produto" },
      { keys: ["F4"], label: "Abrir o pagamento / atualizar a revisão" },
      { keys: ["F6"], label: "Cliente (buscar, criar, CPF na nota)" },
      { keys: ["Esc"], label: "Voltar (sai do pagamento; fecha diálogos)" },
      { keys: ["?"], label: "Esta ajuda" },
    ],
  },
  {
    title: "Na comanda",
    items: [
      { keys: ["0–9"], label: "Quantidade, desconto ou preço da linha ativa" },
      { keys: ["Backspace"], label: "Apagar no teclado da linha" },
    ],
  },
  {
    title: "No pagamento",
    items: [
      { keys: ["0–9", ","], label: "Valor da forma selecionada (vírgula = centavos)" },
      { keys: ["="], label: "Exato: a forma selecionada assume o restante" },
      { keys: ["Backspace"], label: "Apagar um dígito do valor (Limpar, na tela, zera a linha)" },
      { keys: ["Enter"], label: "Validar a venda (com o total coberto)" },
    ],
  },
  {
    title: "Na venda concluída",
    items: [
      { keys: ["F2"], label: "Nova venda (sempre)" },
      { keys: ["Enter"], label: "Nova venda (sem troco a conferir nem PIX aguardando)" },
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
          O PDV inteiro opera sem mouse. Os atalhos pausam enquanto um diálogo está aberto.
        </UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
        <section v-for="group in groups" :key="group.title" class="grid gap-1.5">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">{{ group.title }}</p>
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
                >{{ key }}</kbd>
              </span>
            </li>
          </ul>
        </section>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
