// A pergunta "descartar o que não foi salvo?" no diálogo da casa, e não no
// `window.confirm` do navegador.
//
// O `window.confirm` é desenhado pelo navegador, fora do contrato visual e de toque
// da casa: fonte do sistema, botões "OK"/"Cancelar" que não dizem o ato, e no app
// instalado ele aparece como uma caixa estranha sobre o kiosk. Esta peça pergunta com
// as palavras do ato ("Descartar e sair" / "Continuar editando") e devolve a resposta
// como `Promise<boolean>`, para quem antes escrevia `if (!window.confirm(...)) return`.
//
// O diálogo é montado UMA vez pelo kit (`OperatorConfirmDialog`, dentro do
// `OperatorPwaRuntime` que todo app de operador já monta): o app só chama.
//
//   const confirmDiscard = useConfirm();
//   if (!(await confirmDiscard({ title: "Descartar o preço digitado?", ... }))) return;
//
// Guarda de rota assíncrona (Vue Router 4 aceita a Promise):
//   onBeforeRouteLeave(() => !dirty.value || confirmDiscard({ ... }));
//
// ⚠️ Uma pergunta por vez. Com uma aberta, a seguinte responde `false` ("ficar") sem
// abrir: dois gatilhos do mesmo gesto (o Esc do campo e o Esc do popover, por exemplo)
// não empilham duas caixas, e "ficar" é sempre a resposta que não perde nada.
//
// ⚠️ O `beforeunload` (fechar a aba, recarregar) continua NATIVO: o navegador não deixa
// página nenhuma desenhar a própria caixa nesse momento. Este composable não o substitui.
import { shallowRef } from "vue";

export interface ConfirmRequest {
  /** A pergunta, com o ato: "Descartar o preço digitado?". */
  title: string;
  /** O que se perde (e o que fica). Obrigatório: é o que decide a resposta. */
  description: string;
  /** Rótulo do botão que descarta. Padrão: "Descartar". */
  confirmLabel?: string;
  /** Rótulo do botão que fica. Padrão: "Continuar editando". */
  cancelLabel?: string;
}

export interface PendingConfirm extends Required<ConfirmRequest> {
  resolve: (answer: boolean) => void;
}

export const CONFIRM_DEFAULT_LABELS = {
  confirmLabel: "Descartar",
  cancelLabel: "Continuar editando",
} as const;

// Estado de módulo, não `useState`: a pergunta só nasce de um gesto no navegador, e
// precisa ser alcançável de dentro de uma guarda de rota, onde não há setup.
const pending = shallowRef<PendingConfirm | null>(null);

export function requestConfirm(request: ConfirmRequest): Promise<boolean> {
  if (import.meta.server || pending.value) return Promise.resolve(false);
  return new Promise<boolean>((resolve) => {
    pending.value = { ...CONFIRM_DEFAULT_LABELS, ...request, resolve };
  });
}

export function answerConfirm(answer: boolean) {
  const current = pending.value;
  if (!current) return;
  pending.value = null;
  current.resolve(answer);
}

/** O estado lido pelo `OperatorConfirmDialog` (o único que monta a caixa). */
export function useConfirmState() {
  return { pending, answer: answerConfirm };
}

export function useConfirm() {
  return requestConfirm;
}
