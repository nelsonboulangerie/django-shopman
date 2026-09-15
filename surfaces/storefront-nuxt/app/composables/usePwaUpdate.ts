import { useRegisterSW } from 'virtual:pwa-register/vue'

export function usePwaUpdate () {
  const { needRefresh, updateServiceWorker } = useRegisterSW({ immediate: true })

  return {
    needRefresh,
    update: () => updateServiceWorker(true)
  }
}
