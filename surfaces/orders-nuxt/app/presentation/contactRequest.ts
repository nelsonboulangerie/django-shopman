// Ouvidoria aberta no pedido: o cliente pediu para falar com o responsável.
//
// Duas portas, o mesmo caso: depois de avaliar com nota baixa (`rating`, com as
// estrelas e o comentário) ou porque quis cancelar com o preparo já começado
// (`cancellation`). Pela régua do dono (06/11/2026), depois do preparo o pedido
// não se cancela: o responsável conversa com o cliente e marca Resolvido.

import type { ContactRequestProjection } from "~/generated/ordersContract";

export interface ContactRequestNotice {
  title: string;
  description: string;
  /** A nota em estrelas só existe na ouvidoria da avaliação. */
  showsRating: boolean;
}

export function contactRequestNotice(request: ContactRequestProjection): ContactRequestNotice {
  const when = request.requested_at_display;
  if (request.origin === "cancellation") {
    return {
      title: "Ouvidoria aberta: o cliente queria cancelar",
      description:
        `O cliente quis cancelar, mas o preparo já tinha começado, e pediu para falar com o responsável (${when}). ` +
        "O pedido segue; chame o cliente e marque Resolvido com o que foi combinado.",
      showsRating: false,
    };
  }
  return {
    title: "Ouvidoria aberta",
    description: request.comment
      ? `O cliente pediu para falar com o responsável (${when}). Comentário: ${request.comment}`
      : `O cliente pediu para falar com o responsável (${when}). Não deixou comentário.`,
    showsRating: true,
  };
}
