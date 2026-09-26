<script setup lang="ts">
const nuxtApp = useNuxtApp()
const router = useRouter()
const active = ref(false)
const announce = ref(false)
let announceTimer: ReturnType<typeof setTimeout> | null = null

function begin () {
  active.value = true
  announce.value = false
  if (announceTimer) clearTimeout(announceTimer)
  announceTimer = setTimeout(() => {
    if (active.value) announce.value = true
  }, 300)
}

function finish () {
  active.value = false
  announce.value = false
  if (announceTimer) clearTimeout(announceTimer)
  announceTimer = null
}

function navigationIntent (event: MouseEvent) {
  if (
    event.defaultPrevented
    || event.button !== 0
    || event.metaKey
    || event.ctrlKey
    || event.shiftKey
    || event.altKey
  ) return

  const target = event.target instanceof Element ? event.target : null
  const link = target?.closest<HTMLAnchorElement>('a[href]')
  if (
    !link
    || link.hasAttribute('download')
    || link.getAttribute('target') === '_blank'
    || link.getAttribute('aria-disabled') === 'true'
  ) return

  let destination: URL
  try {
    destination = new URL(link.href, window.location.href)
  } catch {
    return
  }
  if (destination.origin !== window.location.origin) return

  const current = new URL(window.location.href)
  if (
    destination.pathname === current.pathname
    && destination.search === current.search
  ) return

  // Começa no gesto, antes do middleware que espera a sacola ficar durável.
  begin()
}

const removePageStart = nuxtApp.hook('page:start', begin)
const removePageFinish = nuxtApp.hook('page:finish', finish)
const removeAppError = nuxtApp.hook('app:error', finish)
const removeRouterError = router.onError(finish)

onMounted(() => {
  document.addEventListener('click', navigationIntent, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', navigationIntent, true)
  removePageStart()
  removePageFinish()
  removeAppError()
  removeRouterError()
  finish()
})
</script>

<template>
  <div
    v-show="active"
    class="pointer-events-none fixed inset-x-0 top-0 z-[100] h-1 bg-cta shadow-sm motion-safe:animate-pulse"
    data-navigation-feedback
    aria-hidden="true"
  />
  <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">
    {{ announce ? 'Abrindo…' : '' }}
  </p>
</template>
