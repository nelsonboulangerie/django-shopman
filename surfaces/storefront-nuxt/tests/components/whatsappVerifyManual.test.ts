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
    expect(wrapper.find('[data-login-whatsapp-waiting]').text()).toContain('Enviou a mensagem?')
    expect(wrapper.find('[data-login-whatsapp-reopen]').exists()).toBe(true)
  })
})
