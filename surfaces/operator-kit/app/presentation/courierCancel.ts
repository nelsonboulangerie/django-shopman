// O cancelamento pedido de uma corrida da TaOn, como aviso de tela. O estado vem
// do servidor (`courier.cancel_state`, a mesma fonte no Gestor e no PDV):
//  - `pending`: pedido enviado, a TaOn ainda não confirmou (espera, não é erro);
//  - `unknown`: o envio ficou sem resposta (confere-se na central antes de reenviar);
//  - `failed`: a TaOn recusou, ou nada foi enviado. A corrida segue aberta.
// A frase também é do servidor; aqui só se escolhe a cor e o ícone do aviso.

/** O que a projeção manda (`courier.cancel_state` no pedido). */
export interface CourierCancelState {
  state: string;
  message: string;
  at: string;
}

export interface CourierCancelNotice {
  color: "info" | "warning" | "error";
  icon: string;
  message: string;
}

/** O aviso, ou `null` quando não há cancelamento pedido. */
export function courierCancelNotice(
  state: string | null | undefined,
  message: string | null | undefined,
): CourierCancelNotice | null {
  if (!state || !message) return null;
  if (state === "pending") return { color: "info", icon: "i-lucide-hourglass", message };
  if (state === "unknown") return { color: "warning", icon: "i-lucide-circle-help", message };
  return { color: "error", icon: "i-lucide-triangle-alert", message };
}
