// A linha de rodapé do cartão de oferta: pode ir numa campanha, ou o porquê de não.
//
// Antes dizia "Regra comercial cadastrada; não pode ir numa campanha nova agora." para
// todo caso, e o gestor não sabia o que mudar (beta 05/11, ge:MKT-25). O servidor só
// libera oferta em vigor, sem cupom e com produto ou coleção; cada falta tem a sua frase.
import type { Choice, MarketingOffer } from "~/types/campaign";

export function offerCampaignNote(
  offer: Pick<MarketingOffer, "available_for_campaign" | "status" | "skus" | "collections">,
): string {
  if (offer.available_for_campaign) return "Pode ir numa campanha.";
  if (offer.status === "scheduled") return "Só vai numa campanha quando entrar em vigor.";
  if (offer.status !== "live") return "Fora de vigor: campanha só leva oferta em vigor.";
  if (!offer.skus.length && !offer.collections.length) {
    return "Vale para o catálogo todo; campanha pede produto ou coleção.";
  }
  return "As coleções desta oferta estão sem produtos.";
}

/** Uma referência gravada fora das escolhas atuais não significa ausência de oferta. */
export function campaignOfferLabel(ref: string, offers: readonly Choice[]): string {
  if (!ref) return "Sem oferta";
  return offers.find((offer) => offer.value === ref)?.label ?? `Oferta indisponível (${ref})`;
}

export function campaignOfferWarning(ref: string, offers: readonly Choice[]): string {
  return ref && !offers.some((offer) => offer.value === ref)
    ? `A oferta ${ref} não está disponível para campanha. Revise em Ofertas ou escolha outra oferta.`
    : "";
}
