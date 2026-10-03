import {
  AVAILABLE_ONLY_STORAGE_KEY,
  parseAvailableOnlyChoice,
  resolveAvailableOnly
} from '~/presentation/menu'

// A chave "Mostrar só disponíveis" do cardápio e das coleções. O padrão é da
// casa (Admin › Loja › Cardápio, projetado em `public_config`); a escolha do
// cliente fica no navegador dele e vence o padrão. O SSR sempre renderiza o
// padrão da casa (o servidor não lê o storage); a escolha guardada entra no
// mount. Storage bloqueado ou vazio não quebra nada: vale o padrão.
export function useAvailableOnly () {
  const session = useShopSession()
  const choice = useState<boolean | null>('storefront-available-only-choice', () => null)
  const houseDefault = computed(() => Boolean(session.publicConfig.value?.hide_unavailable_by_default))
  const availableOnly = computed(() => resolveAvailableOnly(choice.value, houseDefault.value))

  onMounted(() => {
    if (choice.value !== null) return
    try {
      choice.value = parseAvailableOnlyChoice(localStorage.getItem(AVAILABLE_ONLY_STORAGE_KEY))
    } catch {
      choice.value = null
    }
  })

  function setAvailableOnly (on: boolean) {
    choice.value = on
    try {
      localStorage.setItem(AVAILABLE_ONLY_STORAGE_KEY, on ? 'on' : 'off')
    } catch {
      // Sem storage, a escolha vale só nesta visita.
    }
  }

  return { availableOnly, houseDefault, setAvailableOnly }
}
