interface NavigatorWithStandalone extends Navigator {
  standalone?: boolean
}

export default defineNuxtPlugin(() => {
  const standalone = window.matchMedia('(display-mode: standalone)').matches
    || Boolean((navigator as NavigatorWithStandalone).standalone)
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  document.documentElement.classList.toggle('shop-ios-standalone', standalone && ios)
})
