// PRÉVIA DAS DUAS ARRUMAÇÕES DAS AÇÕES DA COMANDA (PR #1636, escolha do dono).
//
// A: o topo da comanda só LÊ (itens, cozinha em palavra) e o que age na comanda
//    inteira desce para o pé: "Enviar à cozinha" empilhado acima do Pagamento.
//    No editor da linha, a quantidade à esquerda e "Remover" isolado à direita.
// B: "Enviar à cozinha" sobe para o topo da comanda, ao lado da contagem (onde
//    estão as linhas novas); o pé é só o Pagamento. No editor da linha, as ações
//    comuns (quantidade, desconto, observação) numa faixa e "Remover" sozinho numa
//    faixa própria, abaixo de uma divisória.
//
// `?acoes=b` (ou `?acoes=a`) troca e fica lembrado neste dispositivo. Escolhida a
// arrumação, este arquivo e o ramo perdedor saem do código.
const STORAGE_KEY = "pos.preview.actions-layout";

export type PosActionsLayout = "a" | "b";

export function usePosActionsPreview() {
  const layout = useState<PosActionsLayout>("pos-actions-layout", () => "a");
  if (import.meta.client) {
    let chosen: string | null;
    try {
      chosen = new URLSearchParams(window.location.search).get("acoes");
      if (chosen === "a" || chosen === "b") window.localStorage.setItem(STORAGE_KEY, chosen);
      else chosen = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      chosen = null;
    }
    if (chosen === "a" || chosen === "b") layout.value = chosen;
  }
  return layout;
}
