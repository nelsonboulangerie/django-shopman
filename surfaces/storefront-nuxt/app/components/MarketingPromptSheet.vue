<script setup lang="ts">
// O convite de novidades: um bottom sheet na página em que a pessoa cai depois
// de entrar. Não é passo do login (não bloqueia, não é pré-condição) e nunca
// interrompe o que ela veio fazer — fica fora de /entrar, /a, do checkout e do
// pedido (ver isMarketingPromptRouteExcluded). Sobe uma vez por sessão de
// navegador, com uma folga curta depois de a página montar.
//
// Três linhas + chave + fechar. Nada mais. A chave nasce DESLIGADA
// (consentimento é gesto afirmativo, LGPD art. 8 §4):
// - LIGAR salva na hora (`POST account/marketing-prompt/ {whatsapp: true}`),
//   fecha e agradece com um toast;
// - FECHAR sem ligar (X, arrastar, tocar fora, Esc) grava SÓ o carimbo
//   (`{whatsapp: false}`) — nunca um opt-out, porque "agora não" não é "não
//   quero" (um opt-out gravado cala até o recado do próprio pedido naquele canal).
// A pergunta não volta: nem na navegação (estado da sessão), nem na recarga
// (sessionStorage), mesmo que o carimbo tenha falhado — não se insiste.
//
// A pergunta chega pela home (`omotenashi.marketing_prompt_pending`, toda visita,
// inclusive de quem entra pelo aparelho reconhecido) e pelo login. E divide a
// vez com o convite de instalar o app: UM convite por página (useShopInvite).
//
// O rótulo da chave + a linha miúda são a evidência gravada pelo servidor
// (MARKETING_PROMPT_DISCLOSURE em shopman/storefront/api/account.py): mudou
// aqui, muda lá, e sobe a versão.
import { isMarketingPromptRouteExcluded } from '~/presentation/auth'

const props = withDefaults(defineProps<{
  /** Folga entre a página montar e o sheet subir (ms). */
  delayMs?: number
}>(), {
  delayMs: 600
})

const SHOWN_KEY = 'shopman-marketing-prompt-shown'

const route = useRoute()
const session = useShopSession()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const invite = useShopInvite()

const open = ref(false)
const whatsapp = ref(false)
const pending = ref(false)
// Já respondido (ligou) ou já dispensado: o fechamento seguinte não grava nada.
const answered = ref(false)
let openTimer: ReturnType<typeof setTimeout> | null = null

const excluded = computed(() => isMarketingPromptRouteExcluded(route.path))
const eligible = computed(() => session.isAuthenticated.value
  && session.welcomeAsksMarketing.value
  && !excluded.value
  && invite.canOpen('marketing-prompt', route.path))

// Marca a vez ao abrir e a devolve ao fechar (qualquer caminho de fechamento).
watch(open, value => {
  if (value) invite.claim('marketing-prompt', route.path)
  else invite.release('marketing-prompt', route.path)
}, { flush: 'sync' })
watch(() => route.path, path => invite.leavePage(path))

function alreadyShownThisBrowserSession (): boolean {
  if (!import.meta.client) return true
  try {
    return sessionStorage.getItem(SHOWN_KEY) === '1'
  } catch {
    return false
  }
}

function rememberShown () {
  if (!import.meta.client) return
  try {
    sessionStorage.setItem(SHOWN_KEY, '1')
  } catch { /* storage indisponível: vale o estado da sessão */ }
}

function cancelScheduledOpen () {
  if (openTimer) clearTimeout(openTimer)
  openTimer = null
}

function scheduleOpen () {
  cancelScheduledOpen()
  openTimer = setTimeout(() => {
    openTimer = null
    if (!eligible.value || open.value || alreadyShownThisBrowserSession()) return
    rememberShown()
    whatsapp.value = false
    answered.value = false
    open.value = true
  }, props.delayMs)
}

watch(eligible, value => {
  if (!import.meta.client) return
  if (!value) {
    cancelScheduledOpen()
    return
  }
  if (open.value || alreadyShownThisBrowserSession()) return
  scheduleOpen()
}, { immediate: true })

onBeforeUnmount(cancelScheduledOpen)

async function answer (optIn: boolean) {
  return $fetch<{ ok: boolean, whatsapp_opted_in: boolean }>(apiPath('/api/v1/account/marketing-prompt/'), {
    method: 'POST',
    headers: await csrfHeaders(),
    credentials: 'include',
    body: { whatsapp: optIn }
  })
}

// Ligar a chave É a resposta: salva na hora, fecha e agradece.
async function onToggle (value: boolean) {
  whatsapp.value = value
  if (!value || pending.value) return
  pending.value = true
  try {
    const result = await answer(true)
    answered.value = true
    session.markMarketingPromptAnswered()
    open.value = false
    // O servidor não concedeu (a data do perfil prova menor): dizer, em vez de
    // deixar a pessoa achar que vai receber.
    if (result && result.whatsapp_opted_in === false) {
      useSonner.info('Novidades só vão para maiores de idade. Sua resposta ficou guardada.')
    } else {
      useSonner.success('Combinado. Você vai saber primeiro.')
    }
  } catch {
    // A chave volta ao lugar e o sheet fica: a pessoa decide se tenta de novo ou fecha.
    whatsapp.value = false
    useSonner.error('Não foi possível salvar sua resposta.')
  } finally {
    pending.value = false
  }
}

// Fechar sem ligar (X, arrastar, tocar fora, Esc): só o carimbo, e a pergunta
// não volta — nem se o carimbo falhar.
function onOpenChange (value: boolean) {
  if (value) return
  open.value = false
  if (answered.value) return
  answered.value = true
  session.markMarketingPromptAnswered()
  void answer(false).catch(() => null)
}
</script>

<template>
  <BottomSheet
    :open="open"
    max-width="md"
    title="Saber das fornadas antes de todo mundo?"
    data-testid="marketing-prompt-sheet"
    @update:open="onOpenChange"
  >
    <div class="px-4 py-4" data-marketing-prompt>
      <UiFieldLabel for="marketing-prompt-whatsapp" class="w-full">
        <div class="flex w-full items-center gap-4">
          <div class="min-w-0 flex-1">
            <p class="shop-body font-normal">Avisos pelo WhatsApp</p>
            <p class="mt-0.5 shop-meta">Mude quando quiser em Preferências.</p>
          </div>
          <UiSwitch
            id="marketing-prompt-whatsapp"
            :model-value="whatsapp"
            :disabled="pending"
            @update:model-value="onToggle"
          />
        </div>
      </UiFieldLabel>
    </div>
  </BottomSheet>
</template>
