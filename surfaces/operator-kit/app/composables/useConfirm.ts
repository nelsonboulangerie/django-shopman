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
// O tom diz o que o ato É, não o que a pergunta parece: `"danger"` (o padrão, botão
// vermelho) é descartar ou perder; `"primary"` (botão da cor da casa) é o ato normal
// que só merece confirmação (mudar a encomenda de dia, enviar). No tom `"primary"` os
// dois rótulos são obrigatórios: os padrões "Descartar"/"Continuar editando" falam de
// perda, e num ato normal mentiriam.
//
//   await confirm({ tone: "primary", title: "Mudar a encomenda de Ana para qui, 01/10?",
//     description: "...", confirmLabel: "Mudar para qui, 01/10", cancelLabel: "Manter a data" });
//
// ⚠️ O `beforeunload` (fechar a aba, recarregar) continua NATIVO: o navegador não deixa
// página nenhuma desenhar a própria caixa nesse momento. Este composable não o substitui.
import { shallowRef } from "vue";

/** O que o ato é: `"danger"` descarta/perde (vermelho); `"primary"` é ato normal (cor da casa). */
export type ConfirmTone = "danger" | "primary";

interface ConfirmBase {
  /** A pergunta, com o ato: "Descartar o preço digitado?". */
  title: string;
  /** O que se perde (e o que fica). Obrigatório: é o que decide a resposta. */
  description: string;
}

export interface DangerConfirmRequest extends ConfirmBase {
  /** Padrão. Botão do ato em vermelho: descartar, perder. */
  tone?: "danger";
  /** Rótulo do botão que descarta. Padrão: "Descartar". */
  confirmLabel?: string;
  /** Rótulo do botão que fica. Padrão: "Continuar editando". */
  cancelLabel?: string;
}

export interface PrimaryConfirmRequest extends ConfirmBase {
  /** Ato normal que só merece confirmação (reagendar, enviar): botão da cor da casa. */
  tone: "primary";
  /** Rótulo do ato, obrigatório: "Mudar para qui, 01/10". */
  confirmLabel: string;
  /** Rótulo de desistir, obrigatório: "Manter a data". */
  cancelLabel: string;
}

export type ConfirmRequest = DangerConfirmRequest | PrimaryConfirmRequest;

export interface PendingConfirm extends Required<ConfirmBase> {
  tone: ConfirmTone;
  confirmLabel: string;
  cancelLabel: string;
  resolve: (answer: boolean) => void;
}

export const CONFIRM_DEFAULTS = {
  tone: "danger",
  confirmLabel: "Descartar",
  cancelLabel: "Continuar editando",
} as const;

// Estado de módulo, não `useState`: a pergunta só nasce de um gesto no navegador, e
// precisa ser alcançável de dentro de uma guarda de rota, onde não há setup.
const pending = shallowRef<PendingConfirm | null>(null);

export function requestConfirm(request: ConfirmRequest): Promise<boolean> {
  if (import.meta.server || pending.value) return Promise.resolve(false);
  return new Promise<boolean>((resolve) => {
    pending.value = { ...CONFIRM_DEFAULTS, ...request, resolve };
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
