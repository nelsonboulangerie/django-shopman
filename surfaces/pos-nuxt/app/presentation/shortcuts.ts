// O dicionário das teclas do PDV, entregue à ajuda de atalhos da suíte (V6-KIT,
// `OperatorShortcutsHelp` do kit, aberta pelo "Atalhos" do rail, por "?" e no PDV).
//
// O DICIONÁRIO É O CONTRATO das teclas: se uma tecla existe e não está aqui, ela não
// existe para o operador. Os grupos seguem o fluxo da venda, e dentro do primeiro as
// teclas seguem a ordem da TELA: navegação (F2 a F4), depois os três fatos do pedido
// (F6 a F8), que são os três chips da barra do topo na mesma ordem em que aparecem:
// quem compra, como recebe, quando quer. Só lista: quem executa é o handler da página.
import type { ShortcutGroup } from "../../../operator-kit/app/presentation/suiteChrome";

export const POS_SHORTCUT_GROUPS: ShortcutGroup[] = [
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
    title: "No modal Dividir conta",
    items: [
      { keys: ["2–6"], label: "Escolher a quantidade de pessoas e fechar" },
      { keys: ["1"], label: "Desfazer a divisão (quando ativa)" },
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

export const POS_SHORTCUTS_DESCRIPTION =
  "O PDV inteiro opera sem mouse. Os atalhos pausam enquanto um diálogo está aberto.";
