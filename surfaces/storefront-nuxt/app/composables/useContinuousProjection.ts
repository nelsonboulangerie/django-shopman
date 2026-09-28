import type { ContinuousSnapshotCache, ContinuumSnapshot } from '~/types/continuum'

type DataState = 'absent' | 'fresh' | 'stale_usable' | 'stale_blocked' | 'invalid'

interface ContinuousProjectionOptions<TState> {
  key: string
  path: string
  enabled: boolean
  accepts: (value: unknown) => value is ContinuumSnapshot<TState>
  install: (
    current: ContinuousSnapshotCache<TState> | null,
    message: ContinuumSnapshot<TState>,
    metadata: { etag: string, validatedAtMs: number, ageMs: number }
  ) => ContinuousSnapshotCache<TState>
  pollMs?: number
}

/** Perfil público inicial do Continuum: snapshot condicional + reconciliação. */
export async function useContinuousProjection<TState> (
  options: ContinuousProjectionOptions<TState>
) {
  const apiPath = useShopmanApiPath()
  // O resultado do useAsyncData já é serializado no payload SSR. Um useState
  // paralelo duplicaria o snapshot inteiro no HTML.
  const cache = shallowRef<ContinuousSnapshotCache<TState> | null>(null)
  const clock = ref(Date.now())

  const request = await useAsyncData<ContinuousSnapshotCache<TState> | null>(
    options.key,
    async () => {
      if (!options.enabled) return null
      const response = await $fetch.raw<ContinuumSnapshot<TState>>(apiPath(options.path), {
        credentials: 'omit',
        headers: {
          accept: 'application/cloudevents+json; continuum=0.2; schema=1',
          ...(cache.value?.etag ? { 'if-none-match': cache.value.etag } : {})
        },
        ignoreResponseError: true
      })
      const validatedAtMs = Date.now()
      const ageMs = Number(response.headers.get('continuum-age-ms') || 0)
      if (response.status === 304 && cache.value) {
        cache.value = {
          ...cache.value,
          validated_at_ms: validatedAtMs,
          age_ms: Math.max(0, ageMs)
        }
        clock.value = validatedAtMs
        return cache.value
      }
      if (response.status !== 200 || !options.accepts(response._data)) {
        throw new Error(`continuum_snapshot_${response.status}`)
      }

      cache.value = options.install(
        cache.value,
        response._data,
        {
          etag: response.headers.get('etag') || '',
          validatedAtMs,
          ageMs
        }
      )
      clock.value = validatedAtMs
      return cache.value
    },
    {
      server: options.enabled,
      immediate: options.enabled,
      // SSR entrega o snapshot completo; numa troca de rota no cliente a página
      // monta primeiro e o snapshot chega nela, sem manter a tela anterior presa.
      lazy: true,
      dedupe: 'defer'
    }
  )

  watch(request.data, value => {
    if (value) cache.value = value
  }, { immediate: true })

  const dataState = computed<DataState>(() => {
    if (request.error.value && !cache.value) return 'invalid'
    if (!cache.value) return 'absent'
    const freshness = cache.value.message.data.freshness
    const elapsed = Math.max(0, clock.value - cache.value.validated_at_ms) + cache.value.age_ms
    if (elapsed <= freshness.fresh_for_ms) return 'fresh'
    if (elapsed <= freshness.fresh_for_ms + freshness.stale_if_error_ms) return 'stale_usable'
    return 'stale_blocked'
  })

  let timer: ReturnType<typeof setTimeout> | undefined
  const pollMs = Math.max(5_000, options.pollMs || 30_000)
  function schedule () {
    if (!import.meta.client || !options.enabled) return
    const jittered = Math.round(pollMs * (0.9 + Math.random() * 0.2))
    timer = setTimeout(async () => {
      clock.value = Date.now()
      if (document.visibilityState === 'visible') await request.refresh()
      schedule()
    }, jittered)
  }
  function onVisibilityChange () {
    clock.value = Date.now()
    if (document.visibilityState === 'visible') void request.refresh()
  }
  onMounted(() => {
    schedule()
    document.addEventListener('visibilitychange', onVisibilityChange)
  })
  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return {
    data: computed(() => cache.value?.message || null),
    dataState,
    pending: request.pending,
    error: request.error,
    refresh: request.refresh
  }
}
