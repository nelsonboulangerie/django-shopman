export type ShopScrollTarget = Window | HTMLElement

export function shopScrollViewport (): HTMLElement | null {
  if (!import.meta.client) return null
  return document.querySelector<HTMLElement>('[data-shop-scroll-viewport]')
}

/**
 * Overlays lock the element that actually owns vertical scrolling. The internal
 * viewport only becomes that owner in the installed iOS shell; everywhere else
 * the document body remains the scroll-lock target.
 */
export function shopOverlayScrollTarget (): HTMLElement | null {
  if (!import.meta.client) return null
  const viewport = shopScrollViewport()
  if (document.documentElement.classList.contains('shop-ios-standalone') && viewport) return viewport
  return document.body
}

/**
 * O documento rola no navegador comum. No PWA mobile instalado, o casco tem
 * altura fixa e este viewport interno rola para manter a bottom-nav em fluxo
 * normal (sem depender do position:fixed instável do WebKit/iOS 26).
 */
export function shopScrollTarget (): ShopScrollTarget {
  const viewport = shopScrollViewport()
  if (viewport && getComputedStyle(viewport).overflowY === 'auto') return viewport
  return window
}

export function shopScrollTop (target: ShopScrollTarget = shopScrollTarget()): number {
  return target === window ? window.scrollY : (target as HTMLElement).scrollTop
}

export function shopScrollMetrics (target: ShopScrollTarget = shopScrollTarget()) {
  if (target === window) {
    return {
      top: window.scrollY,
      height: window.innerHeight,
      scrollHeight: document.documentElement.scrollHeight
    }
  }
  const element = target as HTMLElement
  return {
    top: element.scrollTop,
    height: element.clientHeight,
    scrollHeight: element.scrollHeight
  }
}

export function shopScrollToElement (
  element: HTMLElement,
  offset: number,
  behavior: ScrollBehavior,
  target: ShopScrollTarget = shopScrollTarget()
) {
  if (target === window) {
    window.scrollTo({
      top: Math.max(0, element.getBoundingClientRect().top + window.scrollY - offset),
      behavior
    })
    return
  }

  const viewport = target as HTMLElement
  viewport.scrollTo({
    top: Math.max(0, viewport.scrollTop + element.getBoundingClientRect().top - viewport.getBoundingClientRect().top - offset),
    behavior
  })
}
