// "Confirmar pelo WhatsApp" — provar que é você sem digitar nada.
//
// ⚠️ A prova é a MENSAGEM ENVIADA, não o toque num link. Quem toca pode ter recebido a
// mensagem encaminhada; quem envia controla o número. É a mesma prova que o OTP dá — o
// código também chega naquele número — mas sem código para ler e digitar: um toque.
//
// Não há mecanismo novo aqui. `POST /api/v1/auth/whatsapp/start/` já existe e é o login por
// WhatsApp da loja: guarda a sacola e o destino sob um código `NB-XxXx` e devolve o `wa.me`
// pré-preenchido. O ManyChat casa `#menu`, envia a mensagem inteira ao backend, cria o
// access link, e o resgate confia no aparelho (`source=manychat`) — então a confirmação
// vale para sempre naquele celular.
//
// Por isso a sacola não se perde: ela viaja no código, e o resgate a adota.

export function useWhatsAppConfirm() {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const starting = ref(false)
  const failed = ref(false)

  /**
   * Abre o WhatsApp com a mensagem pronta.
   *
   * @param next Caminho para onde ela volta depois de confirmar (a tela onde estava).
   */
  async function confirm(next: string) {
    starting.value = true
    failed.value = false
    try {
      const response = await $fetch<{ deep_link: string }>(
        apiPath('/api/v1/auth/whatsapp/start/'),
        {
          method: 'POST',
          headers: await csrfHeaders(),
          credentials: 'include',
          body: { next }
        }
      )
      if (!response?.deep_link) {
        failed.value = true
        return
      }
      // `window.location` e não `<a target=_blank>`: dentro do navegador embutido do
      // WhatsApp, abrir aba nova costuma virar tela em branco — e aqui o destino é o próprio
      // WhatsApp, então trocar de tela é o comportamento certo.
      window.location.href = response.deep_link
    } catch {
      failed.value = true
    } finally {
      starting.value = false
    }
  }

  return { confirm, starting, failed }
}
