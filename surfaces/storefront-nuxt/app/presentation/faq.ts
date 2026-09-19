import type { FAQItemProjection, ShopProjection, SiteBusinessProjection } from '~/types/shopman'

// Lógica pura da página /faq: de onde vêm as perguntas e como falar com a casa
// quando a resposta não está lá. Sem Vue/Nuxt — testável em vitest.

export interface FaqContactLink {
  kind: 'whatsapp' | 'phone' | 'email'
  label: string
  value: string
  href: string
  icon: string
}

function clean (value: string | null | undefined): string {
  return (value || '').trim()
}

// As perguntas do cadastro do site vencem. Sem elas (endpoint ainda ausente ou
// lista vazia), as mesmas da home — a página nunca some por falta de um campo.
export function faqItems (
  siteFaq: FAQItemProjection[] | null | undefined,
  homeFaq: FAQItemProjection[] | null | undefined
): FAQItemProjection[] {
  const valid = (items: FAQItemProjection[] | null | undefined) =>
    (items || []).filter(item => clean(item?.question) && clean(item?.answer))
  const fromSite = valid(siteFaq)
  return fromSite.length ? fromSite : valid(homeFaq)
}

export function telHref (phone: string): string {
  const digits = phone.replace(/[^\d+]/g, '')
  return digits ? `tel:${digits}` : ''
}

// Canais de contato no fim da página: WhatsApp, telefone e e-mail, cada um só
// quando existe. O cadastro do site vence; a loja (shell) cobre o que faltar.
export function faqContactLinks (params: {
  business?: Pick<SiteBusinessProjection, 'telephone' | 'email'> | null
  shop?: Pick<ShopProjection, 'phone' | 'phone_display' | 'phone_url' | 'email' | 'whatsapp_url'> | null
  whatsappUrl?: string | null
}): FaqContactLink[] {
  const { business, shop } = params
  const links: FaqContactLink[] = []

  const whatsappUrl = clean(params.whatsappUrl) || clean(shop?.whatsapp_url)
  if (whatsappUrl) {
    links.push({ kind: 'whatsapp', label: 'WhatsApp', value: 'Falar no WhatsApp', href: whatsappUrl, icon: 'lucide:message-circle' })
  }

  const businessPhone = clean(business?.telephone)
  const phone = businessPhone
    ? { value: businessPhone, href: telHref(businessPhone) }
    : { value: clean(shop?.phone_display) || clean(shop?.phone), href: clean(shop?.phone_url) || telHref(clean(shop?.phone)) }
  if (phone.value && phone.href) {
    links.push({ kind: 'phone', label: 'Telefone', value: phone.value, href: phone.href, icon: 'lucide:phone' })
  }

  const email = clean(business?.email) || clean(shop?.email)
  if (email) {
    links.push({ kind: 'email', label: 'E-mail', value: email, href: `mailto:${email}`, icon: 'lucide:mail' })
  }
  return links
}
