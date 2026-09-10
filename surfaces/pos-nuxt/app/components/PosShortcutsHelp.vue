<script setup lang="ts">
// Descoberta de atalhos: um overlay calmo que LISTA o que o teclado físico faz
// no PDV. Abre pela tecla "?" (o shell é o dono do atalho) e por um botão
// discreto no cabeçalho. Só lista — quem executa é o handler global da página.
defineProps<{ open: boolean }>();
defineEmits<{ "update:open": [boolean] }>();

// O DICIONÁRIO É O CONTRATO das teclas — se uma tecla existe e não está aqui,
// ela não existe para o operador. Os grupos seguem o fluxo da venda, e dentro do
// primeiro as teclas seguem a ordem da TELA: navegação (F2–F4), depois os três
// fatos do pedido (F6–F8), que são os três chips da barra do topo na mesma
// ordem em que aparecem — quem compra, como recebe, quando quer.
const groups: Array<{ title: string; items: Array<{ keys: string[]; label: string }> }> = [
  {
    title: "Em toda a venda",
    items: [
      { keys: ["F2"], label: "Ir para as comandas (foca a referência)" },
      { keys: ["F3", "/"], label: "Buscar produto" },
      { keys: ["F4"], label: "Abrir o pagamento / atualizar a revisão" },
      { keys: ["F6"], label: "Cliente (buscar, criar, associar)" },
      { keys: ["F7"], label: "Recebimento (retirada ou entrega)" },
      { keys: ["F8"], label: "Quando (hoje ou outra data)" },
      { keys: ["Esc"], label: "Sair do campo; depois, voltar (sai do pagamento; fecha diálogos)" },
      { keys: ["?"], label: "Esta ajuda" },
    ],
  },
  {
    title: "Na comanda",
    items: [
      { keys: ["0–9"], label: "Quantidade ou desconto da linha ativa" },
      { keys: ["Backspace"], label: "Apagar no teclado da linha" },
      { keys: ["F9"], label: "Enviar à cozinha" },
      { keys: ["F10"], label: "Transferir itens para outra comanda" },
    ],
  },
  {
    title: "Na lista de itens",
    items: [
      { keys: ["Alt+S"], label: "Selecionar itens (com navegação por teclado)" },
      { keys: ["↑", "↓"], label: "Mover o foco entre itens, sem mudar as marcações" },
      { keys: ["Espaço"], label: "Marcar/desmarcar o item" },
      { keys: ["Enter"], label: "Abrir/fechar detalhes do item" },
      { keys: ["→", "←"], label: "Abrir/fechar detalhes do item" },
      { keys: ["+", "−"], label: "Ajustar quantidade fora da seleção múltipla" },
      { keys: ["Delete"], label: "Pedir remoção do item, com confirmação" },
      { keys: ["Esc"], label: "Fechar detalhes; depois, concluir seleção" },
    ],
  },
  {
    title: "No pagamento",
    items: [
      { keys: ["0–9", ","], label: "Valor da forma selecionada (vírgula = centavos)" },
      { keys: ["R", "P", "C", "D", "L"], label: "Lançar a forma: Reais (dinheiro), Pix, Crédito, Débito, Link" },
      { keys: ["="], label: "Exato: a forma selecionada assume o restante" },
      { keys: ["F9"], label: "Desconto na venda" },
      { keys: ["F10"], label: "Dividir a conta" },
      { keys: ["F"], label: "CPF na nota (liga/desliga)" },
      { keys: ["I", "M"], label: "Nota Impressa / por e-Mail (liga/desliga)" },
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
                <OperatorKbd
                  v-for="key in item.keys"
                  :key="key"
                >{{ key }}</OperatorKbd>
              </span>
            </li>
          </ul>
        </section>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
