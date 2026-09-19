// UM convite por visualização de página.
//
// A loja tem dois convites que sobem da base sem ninguém pedir: instalar o app
// (PwaInstallInvite) e avisos pelo WhatsApp (MarketingPromptSheet). Empilhados,
// um cobre o outro e a pessoa fecha os dois sem ler nenhum. A regra:
//
// - se um convite está aberto, ou abriu nesta página, o outro espera a próxima
//   navegação;
// - o de instalar abre na hora em que a página monta; o de novidades espera
//   ~600 ms. Então o de novidades só ganha quando o de instalar não vai abrir.
//
// O estado é mínimo e compartilhado (`useState`): qual convite está aberto e em
// que caminho um convite foi mostrado. Cada convite marca ao abrir, limpa ao
// fechar e avisa quando a página muda; todas as operações são idempotentes, então
// os dois componentes podem chamá-las na mesma navegação sem se atropelar.

export type ShopInviteKind = 'pwa-install' | 'marketing-prompt'

interface ShopInviteState {
  open: ShopInviteKind | null
  shownOnPath: string | null
}

export function useShopInvite () {
  const state = useState<ShopInviteState>('shop-invite-open', () => ({ open: null, shownOnPath: null }))

  // O próprio convite aberto continua "podendo"; outro só entra com a vez livre
  // e numa página em que nenhum convite apareceu.
  function canOpen (kind: ShopInviteKind, path: string): boolean {
    if (state.value.open === kind) return true
    return state.value.open === null && state.value.shownOnPath !== path
  }

  function claim (kind: ShopInviteKind, path: string) {
    state.value = { open: kind, shownOnPath: path }
  }

  // Fechar não devolve a vez nesta página: o convite "abriu nesta página".
  function release (kind: ShopInviteKind, path: string) {
    if (state.value.open !== kind) return
    state.value = { open: null, shownOnPath: path }
  }

  // Página nova = vez nova, a não ser que um convite ainda esteja aberto (ao
  // fechar, ele carimba a página em que fechou).
  function leavePage (path: string) {
    if (state.value.open !== null || state.value.shownOnPath === path) return
    state.value = { open: null, shownOnPath: null }
  }

  return {
    openInvite: computed(() => state.value.open),
    canOpen,
    claim,
    release,
    leavePage
  }
}
