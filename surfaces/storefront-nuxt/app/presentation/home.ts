// Loja fechada: o topo do hero diz o estado E o que dá para fazer. A finalização
// aceita pedido (e pagamento) com a loja fechada, e a casa confere na abertura;
// a frase usa o mesmo vocabulário do pagamento fora do horário ("conferimos seu
// pedido quando abrirmos"). Prometer "finaliza quando abrirmos" mentia (beta 06/11).
export const CLOSED_HERO_HINT = 'Você já pode finalizar o pedido, e conferimos quando abrirmos.'

export function closedHeroEyebrow (statusLabel?: string | null): string {
  const label = statusLabel?.trim().replace(/\.+$/, '')
  return label ? `${label}. ${CLOSED_HERO_HINT}` : CLOSED_HERO_HINT
}
