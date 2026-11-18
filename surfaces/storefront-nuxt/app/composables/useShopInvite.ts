// UM convite por visita.
//
// A loja tem dois convites que sobem da base sem ninguém pedir: instalar o app
// (PwaInstallInvite) e avisos pelo WhatsApp (MarketingPromptSheet). Os dois só
// existem depois do pedido enviado (`~/utils/orderSecured`) e fora do caminho da
// compra (`~/presentation/invites`). E, entre eles, a regra é uma só: subiu um
// convite nesta visita, o outro fica para a próxima (decisão 3 do plano de
// excelência da loja, 16/11/2026). Antes a vez era por página, e a cliente via um
// convite atrás do outro a cada navegação.
//
// O de instalar abre na hora em que a página monta; o de novidades espera ~600 ms.
// Então o de novidades só ganha quando o de instalar não vai abrir.
//
// "Visita" é a sessão do navegador (sessionStorage): sobrevive à recarga e à
// navegação, e acaba quando a aba fecha. O estado em memória (`useState`) diz qual
// convite está aberto agora; todas as operações são idempotentes, então os dois
// componentes podem chamá-las sem se atropelar.

export type ShopInviteKind = 'pwa-install' | 'marketing-prompt'

const SHOWN_THIS_VISIT_KEY = 'shopman-invite-shown'

interface ShopInviteState {
  open: ShopInviteKind | null
  shownThisVisit: boolean
  /** Já leu a marca da visita no navegador (o servidor não sabe dela). */
  synced: boolean
}

function readShownThisVisit (): boolean {
  try {
    return window.sessionStorage.getItem(SHOWN_THIS_VISIT_KEY) === '1'
  } catch {
    return false
  }
}

function rememberShownThisVisit () {
  try {
    window.sessionStorage.setItem(SHOWN_THIS_VISIT_KEY, '1')
  } catch { /* storage negado: vale o estado em memória */ }
}

export function useShopInvite () {
  const state = useState<ShopInviteState>('shop-invite', () => ({ open: null, shownThisVisit: false, synced: false }))

  if (import.meta.client && !state.value.synced) {
    state.value = { ...state.value, shownThisVisit: state.value.shownThisVisit || readShownThisVisit(), synced: true }
  }

  // O próprio convite aberto continua "podendo"; outro só entra se nenhum convite
  // subiu nesta visita.
  function canOpen (kind: ShopInviteKind): boolean {
    if (state.value.open === kind) return true
    return state.value.open === null && !state.value.shownThisVisit
  }

  function claim (kind: ShopInviteKind) {
    if (import.meta.client) rememberShownThisVisit()
    state.value = { ...state.value, open: kind, shownThisVisit: true }
  }

  // Fechar não devolve a vez: nesta visita, um convite já subiu.
  function release (kind: ShopInviteKind) {
    if (state.value.open !== kind) return
    state.value = { ...state.value, open: null }
  }

  return {
    openInvite: computed(() => state.value.open),
    canOpen,
    claim,
    release
  }
}
