// Onde um convite pode subir sozinho.
//
// A loja tem dois convites que ninguém pediu: instalar o app (PwaInstallInvite) e
// avisos pelo WhatsApp (MarketingPromptSheet). Decisão do dono de 16/11/2026
// (excelência da loja, decisão 3): convite só depois do pedido enviado. Nada no
// caminho da compra: nem no produto, nem na sacola, nem no checkout, e também não
// nas portas de entrada (/entrar, /a) nem no pedido (pagamento e acompanhamento).
// Antes, cada convite tinha a sua lista, e as duas deixavam o produto de fora: o
// de instalar subia sobre o produto e o de novidades cobria o botão de finalizar
// na sacola (P2-05). Agora a lista é uma só.
const INVITE_EXCLUDED_PATHS = ['/entrar', '/a', '/produto', '/sacola', '/finalizar', '/pedido']

export function isShopInviteRouteExcluded (path: string): boolean {
  return INVITE_EXCLUDED_PATHS.some(base => path === base || path.startsWith(`${base}/`))
}
