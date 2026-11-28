import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import WhatsappVerifyPanel from '~/components/WhatsappVerifyPanel.vue'

// O envio manual: a instrução diz para ONDE mandar, e o número entra onde a
// copy (editável no Admin) marca `{phone}`. Sem o marcador, o número vai para o
// fim da frase — nunca some da instrução. Ele é o plano B da ESPERA: só aparece
// depois do toque, quando a pessoa pode ter visto o WhatsApp não abrir.

const base = { status: 'ready' as const, code: 'NB-HAKZKG', waNumber: '554333231997', deepLink: 'https://wa.me/x', waiting: true }

function intro (wrapper: Awaited<ReturnType<typeof mountSuspended>>) {
  return wrapper.find('[data-login-whatsapp-manual-intro]').text().replace(/\s+/g, ' ')
}

describe('WhatsappVerifyPanel — envio manual', () => {
  it('põe o número onde a copy marca {phone}', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, { props: base })
    expect(wrapper.find('[data-login-whatsapp-manual-title]').text()).toBe('O WhatsApp não abriu?')
    expect(intro(wrapper)).toBe('Mande a mensagem abaixo para (43) 3323-1997 no WhatsApp.')
    expect(wrapper.find('[data-login-whatsapp-manual]').text()).toContain('#menu NB-HAKZKG')
  })

  it('sem o marcador, o número fecha a frase', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, manualIntro: 'Envie esta mensagem para o nosso WhatsApp' },
    })
    expect(intro(wrapper)).toBe('Envie esta mensagem para o nosso WhatsApp (43) 3323-1997.')
  })

  it('antes do toque, a tela é o porquê, os passos e um botão — sem plano B', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, waiting: false, why: 'É por lá que avisamos.', steps: ['Um', 'Dois', 'Três'] },
    })
    expect(wrapper.find('[data-login-whatsapp-why]').text()).toBe('É por lá que avisamos.')
    expect(wrapper.findAll('[data-login-whatsapp-steps] li')).toHaveLength(3)
    expect(wrapper.find('[data-login-whatsapp-manual]').exists()).toBe(false)
    expect(wrapper.find('[data-login-whatsapp-waiting]').exists()).toBe(false)
  })

  it('depois do toque, a tela espera a mensagem', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, { props: base })
    expect(wrapper.find('[data-login-whatsapp-open]').exists()).toBe(false)
    expect(wrapper.find('[data-login-whatsapp-waiting]').text()).toContain('Mensagem enviada?')
    expect(wrapper.find('[data-login-whatsapp-reopen]').exists()).toBe(true)
  })

  it('conferiu e não chegou: a tela diz, em vez de só girar o botão (beta 05/11)', async () => {
    const quiet = await mountSuspended(WhatsappVerifyPanel, { props: base })
    expect(quiet.find('[data-login-whatsapp-not-arrived]').exists()).toBe(false)

    const wrapper = await mountSuspended(WhatsappVerifyPanel, { props: { ...base, notArrived: true } })
    expect(wrapper.find('[data-login-whatsapp-not-arrived]').text()).toContain('ainda não chegou')

    const busy = await mountSuspended(WhatsappVerifyPanel, { props: { ...base, notArrived: true, checking: true } })
    expect(busy.find('[data-login-whatsapp-not-arrived]').exists()).toBe(false)
  })

  it('a mensagem chegou e falta liberar: a tela diz o que é verdade e o que falta (#3271)', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: {
        ...base,
        returnState: 'slow',
        notArrived: true,
        awaitingRelease: true,
        arrivedMessage: 'Agora, na resposta do WhatsApp, toque em “Liberar o Chrome”. Esta tela entra logo depois.'
      }
    })
    const waiting = wrapper.find('[data-login-whatsapp-waiting]')
    expect(wrapper.find('[data-login-whatsapp-arrived]').exists()).toBe(true)
    expect(waiting.text()).toContain('Sua mensagem chegou')
    expect(waiting.text()).toContain('toque em “Liberar o Chrome”')
    // Nada de "ainda não chegou", nem de "demorando", nem do plano B de reenviar.
    expect(waiting.text()).not.toContain('ainda não chegou')
    expect(waiting.text()).not.toContain('Está demorando')
    expect(wrapper.find('[data-login-whatsapp-not-arrived]').exists()).toBe(false)
    expect(wrapper.find('[data-login-whatsapp-manual]').exists()).toBe(false)
    const check = wrapper.find('[data-login-whatsapp-check]')
    expect(check.text()).toBe('Já liberei. Conferir agora')
    await check.trigger('click')
    expect(wrapper.emitted('check')).toHaveLength(1)
    // O ícone não gira: não há mais o que esperar da mensagem.
    expect(waiting.find('.animate-spin').exists()).toBe(false)
  })

  it('a falha de rede fala mais alto que "a mensagem chegou": a última conferência não respondeu', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, returnState: 'offline-or-error', awaitingRelease: true }
    })
    expect(wrapper.find('[data-login-whatsapp-waiting]').text()).toContain('Não consegui conferir agora')
    expect(wrapper.find('[data-login-whatsapp-check]').text()).toBe('Já enviei. Conferir agora')
  })

  it('a mensagem do plano B é uma frase inteira: quebra a linha, nunca se corta (#3271)', async () => {
    const message = 'Olá! Quero entrar no site da Nelson Boulangerie (ref. NB-HAKZKG)'
    const wrapper = await mountSuspended(WhatsappVerifyPanel, { props: { ...base, message } })
    const shown = wrapper.find('[data-login-whatsapp-manual-message]')
    expect(shown.text()).toBe(message)
    expect(shown.classes()).not.toContain('truncate')
    expect(shown.classes()).toContain('break-words')
    // A referência não se parte no hífen.
    expect(shown.find('[data-login-whatsapp-manual-ref]').text()).toBe('NB-HAKZKG')
    expect(shown.find('[data-login-whatsapp-manual-ref]').classes()).toContain('whitespace-nowrap')
    // O botão de copiar continua ao lado.
    expect(wrapper.find('[data-login-whatsapp-manual] button[aria-label="Copiar mensagem"]').exists()).toBe(true)
  })

  it('na demora explica que não é para reenviar e permite conferir agora', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, returnState: 'slow' }
    })

    expect(wrapper.find('[data-login-whatsapp-waiting]').text()).toContain('Está demorando mais que o normal')
    expect(wrapper.find('[data-login-whatsapp-waiting]').text()).toContain('Não precisa enviar outra mensagem')
    await wrapper.find('[data-login-whatsapp-check]').trigger('click')
    expect(wrapper.emitted('check')).toHaveLength(1)
  })

  it('quando não consegue consultar preserva a mensagem e orienta sobre a rede', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, returnState: 'offline-or-error' }
    })

    expect(wrapper.find('[data-login-whatsapp-waiting]').text()).toContain('Não consegui conferir agora')
    expect(wrapper.find('[data-login-whatsapp-waiting]').text()).toContain('Sua mensagem e sua sacola continuam guardadas')
    expect(wrapper.find('[data-login-whatsapp-manual]').text()).toContain('NB-HAKZKG')
  })

  it('quando expira oferece nova mensagem e SMS sem beco sem saída', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, waiting: false, returnState: 'expired' }
    })

    const panel = wrapper.find('[data-login-whatsapp-expired]')
    expect(panel.text()).toContain('Essa tentativa expirou')
    expect(panel.text()).toContain('Gerar nova mensagem')
    expect(panel.text()).toContain('Receber código por SMS')
  })

  it('sem WhatsApp configurado promove SMS e mantém ajuda nomeada', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, waiting: false, status: 'unavailable' }
    })

    const panel = wrapper.find('[data-login-whatsapp-unavailable]')
    expect(panel.text()).toContain('O WhatsApp da loja não está disponível agora')
    expect(panel.text()).toContain('Receber código por SMS')
    expect(panel.text()).toContain('Preciso de ajuda')
    await panel.find('button').trigger('click')
    expect(wrapper.emitted('useSms')).toHaveLength(1)
  })
})
