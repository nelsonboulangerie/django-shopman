import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import WhatsappVerifyPanel from '~/components/WhatsappVerifyPanel.vue'

// O envio manual: a instrução diz para ONDE mandar, e o número entra onde a
// copy (editável no Admin) marca `{phone}`. Sem o marcador, o número vai para o
// fim da frase — nunca some da instrução.

const base = { status: 'ready' as const, code: 'NB-HAKZKG', waNumber: '554333231997', deepLink: 'https://wa.me/x' }

function intro (wrapper: Awaited<ReturnType<typeof mountSuspended>>) {
  return wrapper.find('[data-login-whatsapp-manual-intro]').text().replace(/\s+/g, ' ')
}

describe('WhatsappVerifyPanel — envio manual', () => {
  it('põe o número onde a copy marca {phone}', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, { props: base })
    expect(wrapper.find('[data-login-whatsapp-manual-title]').text()).toBe('Ou envie você mesmo')
    expect(intro(wrapper)).toBe('Mande a mensagem abaixo para (43) 3323-1997 no WhatsApp.')
    expect(wrapper.find('[data-login-whatsapp-manual]').text()).toContain('#menu NB-HAKZKG')
  })

  it('sem o marcador, o número fecha a frase', async () => {
    const wrapper = await mountSuspended(WhatsappVerifyPanel, {
      props: { ...base, manualIntro: 'Envie esta mensagem para o nosso WhatsApp' },
    })
    expect(intro(wrapper)).toBe('Envie esta mensagem para o nosso WhatsApp (43) 3323-1997.')
  })
})
