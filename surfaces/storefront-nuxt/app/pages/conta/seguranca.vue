<script setup lang="ts">
import type { AccountDeviceProjection, AccountDeviceResponse } from '~/types/shopman'
import { deviceIcon, profileActionIsExternal, profileIssueFrom, type ProfileIssue } from '~/presentation/account'
import { authPhonePayload, displayE164Phone, maskPhoneInput } from '~/utils/authPhone'
import { formatCount } from '~/utils/display'

definePageMeta({ middleware: 'account' })

type RevokeDeviceMode = 'one' | 'all'

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const exportPending = ref(false)
const privacyIssue = ref('')
// O título do alerta diz QUAL das duas ações falhou. "Privacidade" sozinho era rótulo de
// seção servindo de manchete de erro: quem lê não sabe se perdeu o download ou a exclusão.
const privacyIssueTitle = ref('')
const deleteAccountOpen = ref(false)
const deleteAccountAcknowledged = ref(false)
const deleteAccountPending = ref(false)
const deleteAccountIdempotencyKey = ref('')
const deleteIntentStorageKey = 'shopman.account-deletion-intent.v1'
const deviceIssue = ref('')
const revokeDeviceOpen = ref(false)
const revokeDeviceMode = ref<RevokeDeviceMode>('one')
const revokeDeviceCandidate = ref<AccountDeviceProjection | null>(null)
const revokeDevicePending = ref(false)

// Step-up: reconfirma identidade por OTP antes de excluir/exportar (mesmo logado).
const stepUpOpen = ref(false)
const stepUpCode = ref<number[]>([])
const stepUpPending = ref(false)
const stepUpSendPending = ref(false)
const stepUpSent = ref(false)
const stepUpIssue = ref('')
let pendingStepUpAction: null | (() => void | Promise<void>) = null
let pendingStepUpPurpose: 'export' | 'delete' = 'export'
// A marca do step-up vale 10 minutos, e quem volta depois disso encontra um 403. UMA
// retomada por gesto: se o servidor recusar a identidade logo após a pessoa confirmar o
// código, o problema é outro e a tela tem de DIZER, em vez de pedir código para sempre.
let stepUpResumed = false
const stepUpCodeStr = computed(() => stepUpCode.value.join('').slice(0, 6))

const { data: devicesResponse, pending: devicesPending, refresh: refreshDevices } = await useFetch<AccountDeviceResponse>(apiPath('/api/v1/account/devices/'), {
  credentials: 'include',
  headers: requestHeaders
})

const accountDevices = computed(() => devicesResponse.value?.devices || [])
// Campo opcional mantém compatibilidade com o backend anterior durante rolling
// deploy. Assim que o backend novo responde, falhamos fechados sem iniciar OTP.
const privacyRequestsAvailable = computed(() => devicesResponse.value?.privacy_requests_available !== false)

// ── Acesso rápido (passkey) ─────────────────────────────────────────
//
// Fica ACIMA dos aparelhos confiáveis porque é a credencial mais forte que a pessoa tem: o
// aparelho confiável dispensa o código, a passkey dispensa a espera. O cadastro é opt-in nesta
// página porque capacidade do aparelho é contexto, não promessa no checkout.
type PasskeyRow = {
  credential_id: string
  label: string
  created_at: string
  last_used_at: string
}

const { enroll: enrollPasskey, busy: passkeyBusy, error: passkeyError, needsConfirmation } = usePasskey()
const { confirm: confirmByWhatsApp, starting: confirmingIdentity } = useWhatsAppConfirm()
const passkeyReady = ref(false)
// ⚠️ O motivo de não dar, para a seção DIZER em vez de sumir. Some só a oferta; a seção fica.
const passkeyBlocked = ref('')
const passkeys = ref<PasskeyRow[]>([])
const passkeysPending = ref(true)

async function loadPasskeys () {
  try {
    const data = await $fetch<{ passkeys: PasskeyRow[] }>(apiPath('/api/v1/account/passkeys/'), {
      credentials: 'include'
    })
    passkeys.value = data.passkeys || []
  } catch {
    // 403 aqui significa identidade fraca (chegou por link): a seção some, e o convite de
    // confirmar aparece no lugar do erro — vermelho para quem não fez nada errado ensina a
    // ignorar vermelho.
    passkeys.value = []
  } finally {
    passkeysPending.value = false
  }
}

onMounted(async () => {
  const { passkeyIsQuick, passkeyBlockedReason } = usePasskey()
  passkeyBlocked.value = passkeyBlockedReason()
  passkeyReady.value = await passkeyIsQuick()
  if (!passkeyBlocked.value && !passkeyReady.value) {
    // Navegador e endereço servem, mas o aparelho não oferece um autenticador local rápido.
    // Dizer isso é melhor que sumir: a pessoa entende que o recurso existe e não é para ali.
    passkeyBlocked.value = 'Este aparelho não guarda chave de acesso rápido.'
  }
  await loadPasskeys()
})

async function addPasskey () {
  if (await enrollPasskey()) await loadPasskeys()
}

async function removePasskey (row: PasskeyRow) {
  try {
    await $fetch(apiPath(`/api/v1/account/passkeys/${encodeURIComponent(row.credential_id)}/`), {
      method: 'DELETE',
      headers: await csrfHeaders(),
      credentials: 'include'
    })
    await loadPasskeys()
  } catch (e) {
    deviceIssue.value = errorDetail(e, 'Não foi possível remover agora.')
  }
}
// Copy da tela vem do registro omotenashi (configurável no Admin). Fallback só cobre
// o intervalo de carregamento.
const devicesCopy = computed(() => devicesResponse.value?.copy || {
  page_message: 'Controle os aparelhos confiáveis e seus dados pessoais.',
  empty_title: 'Nenhum aparelho confiável',
  empty_message: 'Quando você optar por confiar neste aparelho no login, ele aparecerá aqui.',
  current_badge: 'Este aparelho',
  last_used_prefix: 'Último uso em',
  near_prefix: 'Próximo a',
  registered_prefix: 'Registrado em',
  revoke_cta: 'Remover',
  revoke_all_cta: 'Remover todos os aparelhos',
  revoke_confirm: 'Remover este aparelho?',
  revoke_all_confirm: 'Remover todos os aparelhos?',
  unknown_label: 'Aparelho desconhecido',
  delete_warning: 'Apagamos seu nome, telefone, e-mail e endereços, inclusive dos pedidos antigos, e você sai da loja neste aparelho.'
})

// ── Falhas de privacidade: a recusa do servidor tem de chegar DENTRO da tela ─────────
//
// As duas ações desta seção falham com o dialeto `{detail, field, errors}` da casa, mais
// um código: 403 `step_up_required` (identidade expirou), 503 `account_export_incomplete`
// / `privacy_receipt_unavailable`, 409 `account_deletion_blocked`. Cada uma dessas frases
// foi escrita para o titular ler — e só serve se ela couber num alerta da tela.
const EXPORT_FILENAME = 'shopman-dados-cliente.json'

/** Arquivo binário, reconhecido pelo que ele SABE FAZER e não por `instanceof`.
 *
 * ⚠️ O `Blob` que chega do fetch pode vir de outro realm (o do runtime, não o do
 * documento): `x instanceof Blob` devolve `false` para um blob perfeitamente válido,
 * e o caminho de erro some sem barulho.
 */
function isBlobLike (value: unknown): value is Blob {
  return !!value
    && typeof (value as Blob).text === 'function'
    && typeof (value as Blob).size === 'number'
}

/** O corpo do erro do ofetch, já decodificado — inclusive quando vem como Blob.
 *
 * ⚠️ Com `responseType: 'blob'`, o ofetch entrega o corpo do ERRO também como Blob: o
 * `{detail}` em português viraria binário e a tela cairia no texto genérico, perdendo
 * justamente a frase que diz o que aconteceu.
 */
async function privacyErrorBody (e: unknown): Promise<Record<string, unknown> | null> {
  const raw = (e as { data?: unknown } | null)?.data
  if (isBlobLike(raw)) {
    try {
      return JSON.parse(await raw.text()) as Record<string, unknown>
    } catch {
      return null
    }
  }
  return raw && typeof raw === 'object' ? raw as Record<string, unknown> : null
}

/** O código da recusa. O 403 do step-up manda `code` na raiz; os 5xx/409 mandam em `error.code`. */
function privacyErrorCode (body: Record<string, unknown> | null): string {
  if (!body) return ''
  if (typeof body.code === 'string') return body.code
  const nested = body.error
  if (nested && typeof nested === 'object' && typeof (nested as { code?: unknown }).code === 'string') {
    return (nested as { code: string }).code
  }
  return ''
}

function privacyErrorDetail (body: Record<string, unknown> | null, fallback: string): string {
  const detail = body?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

/** Falhou: ou a tela reabre o step-up e RETOMA a ação, ou ela diz o que houve.
 *
 * Nunca as duas, e nunca nenhuma — sair da tela sem resposta é o que esta função existe
 * para impedir.
 */
async function handlePrivacyFailure (
  e: unknown,
  purpose: 'export' | 'delete',
  resume: () => void | Promise<void>,
  title: string,
  fallback: string
): Promise<void> {
  const body = await privacyErrorBody(e)
  if (privacyErrorCode(body) === 'step_up_required' && !stepUpResumed) {
    stepUpResumed = true
    privacyIssue.value = ''
    privacyIssueTitle.value = ''
    await requireStepUp(purpose, resume)
    return
  }
  privacyIssueTitle.value = title
  privacyIssue.value = privacyErrorDetail(body, fallback)
}

function exportFilename (disposition: string | null): string {
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(disposition || '')
  const raw = match?.[1]?.trim()
  if (!raw) return EXPORT_FILENAME
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

function saveExportArtifact (artifact: Blob, filename: string) {
  const url = URL.createObjectURL(artifact)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revogar no mesmo tick cancelaria o salvamento antes de o navegador começar a gravar.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

// O download é um FETCH, e não uma navegação. `window.location.assign` trocava a página:
// quando o servidor recusava (503 com recibo, 403 de identidade), o titular saía da tela
// de Segurança e encarava o JSON cru do erro no navegador — com o alerta desta mesma tela,
// feito exatamente para isso, vazio atrás dele. Buscando o arquivo, a recusa volta como
// erro tratável e o "preparando" dura o que o pedido durar, em vez de um cronômetro fixo
// de 1 segundo que mentia sobre o estado.
async function exportData () {
  if (!import.meta.client || exportPending.value) return
  exportPending.value = true
  privacyIssue.value = ''
  privacyIssueTitle.value = ''
  try {
    const response = await $fetch.raw<Blob>(apiPath('/api/v1/account/export/'), {
      credentials: 'include',
      headers: { accept: 'application/json' },
      responseType: 'blob',
      // ⚠️ O ofetch repete GET sozinho em 503 (e o 503 daqui é justamente o de exportação
      // incompleta). Cada repetição abre um recibo de privacidade novo, sem ninguém pedir.
      retry: 0
    })
    const artifact = response._data
    if (!isBlobLike(artifact)) {
      privacyIssueTitle.value = 'Não foi possível exportar'
      privacyIssue.value = 'Seus dados não vieram completos, e nada foi baixado. Tente de novo em alguns minutos.'
      return
    }
    saveExportArtifact(artifact, exportFilename(response.headers.get('content-disposition')))
  } catch (e) {
    await handlePrivacyFailure(
      e,
      'export',
      exportData,
      'Não foi possível exportar',
      // Rede caída não tem `detail`: a frase diz o que aconteceu, que nada foi baixado, e
      // que repetir é seguro — exportar não altera nada na conta.
      'Não conseguimos preparar seus dados agora, e nada foi baixado. Tente de novo em alguns minutos.'
    )
  } finally {
    exportPending.value = false
  }
}

function askDeleteAccount () {
  privacyIssue.value = ''
  privacyIssueTitle.value = ''
  deleteAccountAcknowledged.value = false
  if (import.meta.client && !deleteAccountIdempotencyKey.value) {
    deleteAccountIdempotencyKey.value = sessionStorage.getItem(deleteIntentStorageKey) || crypto.randomUUID()
    sessionStorage.setItem(deleteIntentStorageKey, deleteAccountIdempotencyKey.value)
  }
  deleteAccountOpen.value = true
}

function cancelDeleteAccount () {
  deleteAccountOpen.value = false
  deleteAccountAcknowledged.value = false
  deleteAccountIdempotencyKey.value = ''
  if (import.meta.client) sessionStorage.removeItem(deleteIntentStorageKey)
}

async function deleteAccount () {
  if (!deleteAccountAcknowledged.value || deleteAccountPending.value) return
  deleteAccountPending.value = true
  privacyIssue.value = ''
  privacyIssueTitle.value = ''
  try {
    await $fetch(apiPath('/api/v1/account/delete/'), {
      method: 'POST',
      headers: {
        ...await csrfHeaders(),
        'Idempotency-Key': deleteAccountIdempotencyKey.value
      },
      credentials: 'include',
      body: { acknowledged: true }
    })
    if (import.meta.client) sessionStorage.removeItem(deleteIntentStorageKey)
    deleteAccountIdempotencyKey.value = ''
    session.reset()
    deleteAccountOpen.value = false
    await navigateTo('/')
  } catch (e) {
    // A chave de idempotência NÃO é descartada aqui: é ela que faz a retomada continuar a
    // mesma solicitação em vez de abrir uma segunda.
    await handlePrivacyFailure(
      e,
      'delete',
      deleteAccount,
      'Não foi possível excluir',
      // Sem `detail` (rede caída), a casa não sabe se o servidor chegou a concluir — então
      // NÃO afirma que a conta continua como estava. Diz o que tem: a confirmação não
      // voltou, e repetir é seguro porque a tentativa seguinte continua a MESMA
      // solicitação. "Tente de novo" só se escreve onde repetir não duplica efeito.
      'Não recebemos a confirmação da exclusão. Tente de novo em alguns minutos: a nova tentativa continua esta mesma solicitação e não exclui duas vezes.'
    )
    // Se a tela abriu o step-up, a vez é dele: dois diálogos empilhados escondem o campo
    // do código atrás do aviso.
    if (!stepUpOpen.value) deleteAccountOpen.value = true
  } finally {
    deleteAccountPending.value = false
  }
}

function askRevokeDevice (device: AccountDeviceProjection) {
  revokeDeviceMode.value = 'one'
  revokeDeviceCandidate.value = device
  deviceIssue.value = ''
  revokeDeviceOpen.value = true
}

function askRevokeAllDevices () {
  revokeDeviceMode.value = 'all'
  revokeDeviceCandidate.value = null
  deviceIssue.value = ''
  revokeDeviceOpen.value = true
}

async function confirmRevokeDevice () {
  if (revokeDevicePending.value) return
  revokeDevicePending.value = true
  deviceIssue.value = ''
  try {
    if (revokeDeviceMode.value === 'all') {
      await $fetch(apiPath('/api/v1/account/devices/'), {
        method: 'DELETE',
        headers: await csrfHeaders(),
        credentials: 'include'
      })
    } else if (revokeDeviceCandidate.value) {
      await $fetch(apiPath(`/api/v1/account/devices/${encodeURIComponent(revokeDeviceCandidate.value.id)}/`), {
        method: 'DELETE',
        headers: await csrfHeaders(),
        credentials: 'include'
      })
    }
    await refreshDevices()
    revokeDeviceOpen.value = false
    if (import.meta.client) {
      useSonner.success(revokeDeviceMode.value === 'all' ? 'Aparelhos removidos.' : 'Aparelho removido.')
    }
  } catch (e) {
    deviceIssue.value = errorDetail(e, 'Não foi possível remover o aparelho agora.')
    if (import.meta.client) useSonner.error(deviceIssue.value)
  } finally {
    revokeDevicePending.value = false
  }
}

async function requireStepUp (purpose: 'export' | 'delete', action: () => void | Promise<void>) {
  pendingStepUpAction = action
  pendingStepUpPurpose = purpose
  stepUpCode.value = []
  stepUpIssue.value = ''
  stepUpSent.value = false
  stepUpOpen.value = true
  await sendStepUpCode()
}

async function sendStepUpCode () {
  if (stepUpSendPending.value) return
  stepUpSendPending.value = true
  stepUpIssue.value = ''
  try {
    await $fetch(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: authPhonePayload(session.customerPhone.value || '', 'BR')
    })
    stepUpSent.value = true
  } catch (e) {
    stepUpIssue.value = errorDetail(e, 'Não foi possível enviar o código agora.')
  } finally {
    stepUpSendPending.value = false
  }
}

async function confirmStepUp () {
  if (stepUpPending.value || stepUpCodeStr.value.length !== 6) return
  stepUpPending.value = true
  stepUpIssue.value = ''
  try {
    await $fetch(apiPath('/api/v1/account/step-up/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { code: stepUpCodeStr.value, purpose: pendingStepUpPurpose }
    })
    stepUpOpen.value = false
    const action = pendingStepUpAction
    pendingStepUpAction = null
    if (action) await action()
  } catch (e) {
    stepUpIssue.value = errorDetail(e, 'Código inválido ou expirado.')
    stepUpCode.value = []
  } finally {
    stepUpPending.value = false
  }
}

// ── Mudar meu número ────────────────────────────────────────────────
//
// Duas coisas diferentes moravam no mesmo botão: "entrar com outro número" abre
// OUTRA conta e deixa o histórico para trás. Isto aqui é a que faltava — a conta
// continua a mesma, o número é que muda.
//
// O código vai para o número NOVO, e não para o atual: é a posse dele que falta
// provar. A sessão já responde pela conta.
type PhoneChangeStep = 'number' | 'code'

const phoneChangeOpen = ref(false)
const phoneChangeStep = ref<PhoneChangeStep>('number')
const phoneChangeInput = ref('')
const phoneChangeTarget = ref('')
const phoneChangeCode = ref<number[]>([])
const phoneChangePending = ref(false)
const phoneChangeIssue = ref<ProfileIssue | null>(null)
const phoneChangeCodeStr = computed(() => phoneChangeCode.value.join('').slice(0, 6))
const currentPhoneDisplay = computed(() => displayE164Phone(session.customerPhone.value || ''))

function openPhoneChange () {
  phoneChangeStep.value = 'number'
  phoneChangeInput.value = ''
  phoneChangeTarget.value = ''
  phoneChangeCode.value = []
  phoneChangeIssue.value = null
  phoneChangeOpen.value = true
}

function onPhoneChangeInput (event: Event) {
  const input = event.target as HTMLInputElement
  phoneChangeInput.value = maskPhoneInput(input.value, 'BR')
}

async function sendPhoneChangeCode () {
  if (phoneChangePending.value) return
  phoneChangePending.value = true
  phoneChangeIssue.value = null
  try {
    const body = await $fetch<{ phone: string }>(apiPath('/api/v1/account/phone/request/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: authPhonePayload(phoneChangeInput.value, 'BR')
    })
    phoneChangeTarget.value = body?.phone || phoneChangeInput.value
    phoneChangeCode.value = []
    phoneChangeStep.value = 'code'
  } catch (e) {
    // A recusa RICA (número de outra conta) vem com saídas — e nunca com o nome
    // de quem tem o número. Cair no genérico aqui apagaria o motivo.
    phoneChangeIssue.value = profileIssueFrom(
      httpError(e).data,
      'Não foi possível enviar o código agora. Tente novamente.'
    )
  } finally {
    phoneChangePending.value = false
  }
}

async function confirmPhoneChange () {
  if (phoneChangePending.value || phoneChangeCodeStr.value.length !== 6) return
  phoneChangePending.value = true
  phoneChangeIssue.value = null
  try {
    const body = await $fetch<{ phone: string }>(apiPath('/api/v1/account/phone/confirm/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { ...authPhonePayload(phoneChangeTarget.value, 'BR'), code: phoneChangeCodeStr.value }
    })
    phoneChangeOpen.value = false
    // A tela toda lê o telefone da sessão — inclusive o step-up logo abaixo, que
    // manda o código para "o seu telefone". Deixá-la com o número velho faria a
    // próxima confirmação sair para um número que não é mais dele.
    session.setIdentity({ phone: body?.phone || phoneChangeTarget.value })
    if (import.meta.client) useSonner.success('Pronto: sua conta agora atende neste número.')
  } catch (e) {
    phoneChangeIssue.value = profileIssueFrom(
      httpError(e).data,
      'Não foi possível confirmar o código. Tente novamente.'
    )
    phoneChangeCode.value = []
  } finally {
    phoneChangePending.value = false
  }
}

// Exportar dados exige step-up antes do download (GET passa pela marca de sessão).
function startExport () {
  privacyIssue.value = ''
  privacyIssueTitle.value = ''
  if (!privacyRequestsAvailable.value) return
  stepUpResumed = false
  void requireStepUp('export', exportData)
}

// Excluir conta: fecha o diálogo de ack e exige step-up antes de anonimizar.
function confirmDeleteAccount () {
  if (!privacyRequestsAvailable.value) return
  deleteAccountOpen.value = false
  stepUpResumed = false
  // Retomada de uma tentativa que falhou: a marca do step-up pode estar viva (vale 10
  // minutos), e pedir um código novo à toa é atrito. Tenta direto com a MESMA chave de
  // idempotência — e, se o servidor responder que a identidade expirou, `deleteAccount`
  // reabre o step-up e retoma daí. Antes, este ramo era um beco: o único caminho para
  // confirmar identidade era o que ele pulava, e todo clique repetia a mesma recusa.
  if (privacyIssue.value && deleteAccountIdempotencyKey.value) {
    void deleteAccount()
    return
  }
  void requireStepUp('delete', deleteAccount)
}

useSeoMeta({ title: 'Segurança e dados' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/conta' }, { label: 'Segurança e dados' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">

      <div>
        <h1 class="shop-title">Segurança e dados</h1>
        <p class="shop-muted">{{ devicesCopy.page_message }}</p>
      </div>

      <!-- Seu número: a identidade da conta, e agora também o que dá para mudar -->
      <section class="space-y-4" data-phone-section>
        <div>
          <h2 class="shop-heading">Seu número</h2>
          <p class="shop-muted">
            É por ele que você entra e recebe o aviso de que o pão saiu do forno.
          </p>
        </div>

        <UiItem variant="outline" class="bg-card">
          <UiItemMedia variant="icon" class="size-10 rounded-md">
            <Icon name="lucide:smartphone" />
          </UiItemMedia>
          <UiItemContent>
            <UiItemTitle>{{ currentPhoneDisplay || 'Número não informado' }}</UiItemTitle>
            <UiItemDescription>
              Mudou de número? A conta vem junto — seus pedidos, endereços e pontos ficam.
            </UiItemDescription>
          </UiItemContent>
          <UiItemActions>
            <UiButton variant="outline" size="sm" icon="lucide:arrow-right-left" @click="openPhoneChange">
              Mudar número
            </UiButton>
          </UiItemActions>
        </UiItem>
      </section>

      <!-- Acesso rápido: a credencial mais forte que ela tem -->
      <section class="space-y-4" data-passkey-section>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="shop-heading">Acesso rápido</h2>
            <!-- ⚠️ A entrada pela chave ainda NÃO existe: `usePasskey().signIn()` está
                 escrito e exportado, e não é chamado em lugar nenhum — `/entrar` só
                 oferece WhatsApp e SMS. Enquanto a porta não nascer, esta seção guarda a
                 chave e não promete entrada com ela. Ligar a entrada é outra frente; no
                 dia em que ela existir, a promessa volta junto com o botão. -->
            <p class="shop-muted">
              Guardar uma chave deste aparelho para entrar sem código.
            </p>
          </div>
          <UiButton
            v-if="!passkeysPending && passkeyReady"
            variant="outline"
            size="sm"
            icon="lucide:key-round"
            :loading="passkeyBusy"
            @click="addPasskey"
          >
            Ativar neste aparelho
          </UiButton>
        </div>

        <!-- Identidade fraca (chegou por link de campanha): cadastrar credencial vale para
             sempre, então pedimos uma confirmação antes. Um toque, sem código. -->
        <UiAlert v-if="needsConfirmation" variant="info" icon="lucide:message-circle">
          <UiAlertTitle>Confirme que é você para ativar</UiAlertTitle>
          <UiAlertDescription>
            <p>O acesso rápido vale para sempre neste aparelho, então pedimos uma confirmação.</p>
            <UiButton
              size="sm"
              class="mt-2"
              icon="lucide:message-circle"
              :disabled="confirmingIdentity"
              @click="confirmByWhatsApp('/conta/seguranca')"
            >
              {{ confirmingIdentity ? 'Abrindo o WhatsApp…' : 'Confirmar pelo WhatsApp' }}
            </UiButton>
          </UiAlertDescription>
        </UiAlert>

        <!-- Não dá neste aparelho/endereço: dizer o motivo, em vez de sumir. Some a OFERTA,
             não a seção — quem vem ver o recurso precisa saber que ele existe e por que não
             está disponível aqui. -->
        <UiAlert v-if="passkeyBlocked" variant="info" icon="lucide:info">
          <UiAlertTitle>Não disponível neste aparelho</UiAlertTitle>
          <UiAlertDescription>
            <p>{{ passkeyBlocked }}</p>
            <p class="shop-caption mt-1 text-muted-foreground">
              Você continua entrando pelo WhatsApp, num toque.
            </p>
          </UiAlertDescription>
        </UiAlert>

        <p v-if="passkeyError" class="shop-muted">{{ passkeyError }}</p>

        <UiSkeleton v-if="passkeysPending" class="h-20 rounded-lg" />

        <UiEmpty v-else-if="!passkeys.length" class="border">
          <UiEmptyMedia variant="icon">
            <Icon name="lucide:key-round" />
          </UiEmptyMedia>
          <UiEmptyHeader>
            <UiEmptyTitle>Você ainda não ativou</UiEmptyTitle>
            <UiEmptyDescription>
              Ativando, esta loja passa a reconhecer a chave deste aparelho. Você continua
              entrando pelo WhatsApp quando quiser.
            </UiEmptyDescription>
          </UiEmptyHeader>
        </UiEmpty>

        <UiItemGroup v-else class="gap-3">
          <UiItem v-for="row in passkeys" :key="row.credential_id" variant="outline" class="bg-card">
            <UiItemMedia variant="icon" class="size-10 rounded-md">
              <Icon name="lucide:key-round" />
            </UiItemMedia>
            <UiItemContent>
              <UiItemTitle>{{ row.label }}</UiItemTitle>
              <UiItemDescription>
                <span v-if="row.last_used_at">Usado em {{ row.last_used_at }}</span>
                <span v-else>Ainda não usado</span>
                <span> · Ativado em {{ row.created_at }}</span>
              </UiItemDescription>
            </UiItemContent>
            <UiItemActions>
              <UiButton variant="ghost" size="sm" icon="lucide:trash-2" @click="removePasskey(row)">
                Remover
              </UiButton>
            </UiItemActions>
          </UiItem>
        </UiItemGroup>
      </section>

      <!-- Aparelhos confiáveis -->
      <section class="space-y-4">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="shop-heading">Aparelhos confiáveis</h2>
            <p class="shop-muted">
              {{ devicesPending ? 'Carregando…' : formatCount(accountDevices.length, 'aparelho autorizado', 'aparelhos autorizados') }}
            </p>
          </div>
          <UiButton v-if="accountDevices.length > 1" variant="outline" size="sm" icon="lucide:shield-x" @click="askRevokeAllDevices">
            {{ devicesCopy.revoke_all_cta }}
          </UiButton>
        </div>

        <UiAlert v-if="deviceIssue" variant="destructive">
          <UiAlertTitle>Não foi possível atualizar</UiAlertTitle>
          <UiAlertDescription>{{ deviceIssue }}</UiAlertDescription>
        </UiAlert>

        <UiSkeleton v-if="devicesPending" class="h-32 rounded-lg" />

        <UiEmpty v-else-if="!accountDevices.length" class="border">
          <UiEmptyMedia variant="icon">
            <Icon name="lucide:monitor" />
          </UiEmptyMedia>
          <UiEmptyHeader>
            <UiEmptyTitle>{{ devicesCopy.empty_title }}</UiEmptyTitle>
            <UiEmptyDescription>{{ devicesCopy.empty_message }}</UiEmptyDescription>
          </UiEmptyHeader>
        </UiEmpty>

        <UiItemGroup v-else class="gap-3">
          <UiItem v-for="device in accountDevices" :key="device.id" variant="outline" class="bg-card">
            <UiItemMedia variant="icon" class="size-10 rounded-md">
              <Icon :name="deviceIcon(device.label)" />
            </UiItemMedia>
            <UiItemContent>
              <UiItemTitle>
                {{ device.label || devicesCopy.unknown_label }}
                <UiBadge v-if="device.is_current" variant="secondary">{{ devicesCopy.current_badge }}</UiBadge>
              </UiItemTitle>
              <UiItemDescription>
                <!--
                  A cidade fica em LINHA PRÓPRIA, e não no meio das datas, porque a frase
                  escolhida pelo dono já tem um "·" dentro ("Londrina, PR · Brasil"): em
                  linha única o leitor veria quatro separadores iguais e teria de adivinhar
                  quais agrupam o quê. Linha separada lê "o quê · onde · quando".
                  Vazio é caso comum e legítimo — a leitura de IP só vira rótulo quando o
                  raio de precisão é pequeno o bastante (ver services/ip_location.py), e em
                  celular normalmente não é. Aí a linha some, e não vira "Local desconhecido".
                -->
                <span v-if="device.approximate_city" class="block">{{ devicesCopy.near_prefix }} {{ device.approximate_city }}</span>
                <span class="block">
                  <span v-if="device.last_used_at">{{ devicesCopy.last_used_prefix }} {{ device.last_used_at_display }}</span>
                  <span v-else>{{ device.last_used_at_display }}</span>
                  <span> · {{ devicesCopy.registered_prefix }} {{ device.created_at_display }}</span>
                </span>
              </UiItemDescription>
            </UiItemContent>
            <UiItemActions>
              <UiButton variant="ghost" size="sm" icon="lucide:shield-x" @click="askRevokeDevice(device)">{{ devicesCopy.revoke_cta }}</UiButton>
            </UiItemActions>
          </UiItem>
        </UiItemGroup>
      </section>

      <!-- Dados e privacidade -->
      <section class="shop-stack-block rounded-lg border bg-card p-4">
        <div>
          <h2 class="shop-heading">Dados e privacidade</h2>
          <p class="mt-1 shop-muted">Baixe uma cópia dos seus dados ou encerre sua conta.</p>
        </div>
        <UiAlert v-if="privacyIssue" variant="destructive">
          <UiAlertTitle>{{ privacyIssueTitle || 'Não foi possível concluir' }}</UiAlertTitle>
          <UiAlertDescription>{{ privacyIssue }}</UiAlertDescription>
        </UiAlert>
        <UiAlert v-if="!privacyRequestsAvailable">
          <UiAlertTitle>Solicitações temporariamente indisponíveis</UiAlertTitle>
          <UiAlertDescription>Não é possível exportar seus dados ou excluir sua conta agora. Tente novamente mais tarde.</UiAlertDescription>
        </UiAlert>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <UiButton variant="outline" class="justify-start" icon="lucide:download" :loading="exportPending" :disabled="!privacyRequestsAvailable" @click="startExport">
            Exportar meus dados
          </UiButton>
          <UiButton variant="destructive" class="justify-start" icon="lucide:user-x" :disabled="!privacyRequestsAvailable" @click="askDeleteAccount">
            Excluir minha conta
          </UiButton>
        </div>
      </section>

      <UiAlertDialog v-model:open="deleteAccountOpen">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>Excluir sua conta?</UiAlertDialogTitle>
            <UiAlertDialogDescription>
              {{ devicesCopy.delete_warning }}
            </UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlert v-if="privacyIssue" variant="destructive">
            <UiAlertTitle>Não foi possível excluir</UiAlertTitle>
            <UiAlertDescription>{{ privacyIssue }}</UiAlertDescription>
          </UiAlert>
          <UiField orientation="horizontal">
            <UiFieldContent>
              <UiFieldLabel for="delete-account-ack">Entendi o efeito desta ação</UiFieldLabel>
              <UiFieldDescription>O histórico da compra continua sem nada que identifique você: itens, valores e datas, por obrigação fiscal.</UiFieldDescription>
            </UiFieldContent>
            <UiCheckbox id="delete-account-ack" v-model="deleteAccountAcknowledged" />
          </UiField>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel :disabled="deleteAccountPending" @click="cancelDeleteAccount">Voltar</UiAlertDialogCancel>
            <UiAlertDialogAction variant="destructive" :disabled="!deleteAccountAcknowledged || deleteAccountPending" @click="confirmDeleteAccount">
              Continuar
            </UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>

      <UiAlertDialog v-model:open="revokeDeviceOpen">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>
              {{ revokeDeviceMode === 'all' ? devicesCopy.revoke_all_confirm : devicesCopy.revoke_confirm }}
            </UiAlertDialogTitle>
            <UiAlertDialogDescription>
              {{ revokeDeviceMode === 'all'
                ? 'Você precisará confirmar o telefone novamente nos próximos acessos.'
                : `Você precisará confirmar o telefone novamente neste aparelho: ${revokeDeviceCandidate?.label || devicesCopy.unknown_label}.` }}
            </UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel :disabled="revokeDevicePending">Cancelar</UiAlertDialogCancel>
            <UiAlertDialogAction variant="destructive" :disabled="revokeDevicePending" @click="confirmRevokeDevice">Remover</UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>

      <!-- Mudar o número: informar o novo → confirmar o código que chega NELE -->
      <UiDialog v-model:open="phoneChangeOpen">
        <UiDialogContent>
          <UiDialogHeader>
            <UiDialogTitle>Mudar meu número</UiDialogTitle>
            <UiDialogDescription>
              <template v-if="phoneChangeStep === 'number'">
                Digite o número novo. Vamos mandar um código para ele, para confirmar que é seu.
              </template>
              <template v-else>
                Mandamos um código para {{ displayE164Phone(phoneChangeTarget) }}. Digite-o para
                concluir a mudança.
              </template>
            </UiDialogDescription>
          </UiDialogHeader>

          <UiAlert v-if="phoneChangeIssue" variant="destructive">
            <UiAlertTitle>Não deu para mudar</UiAlertTitle>
            <UiAlertDescription>
              <p>{{ phoneChangeIssue.message }}</p>
              <div v-if="phoneChangeIssue.actions.length" class="mt-2 flex flex-wrap gap-2">
                <UiButton
                  v-for="action in phoneChangeIssue.actions"
                  :key="action.ref"
                  size="sm"
                  :variant="action.priority === 'primary' ? 'default' : 'outline'"
                  :to="profileActionIsExternal(action) ? undefined : action.href"
                  :href="profileActionIsExternal(action) ? action.href : undefined"
                  :target="profileActionIsExternal(action) ? '_blank' : undefined"
                  :rel="profileActionIsExternal(action) ? 'noopener noreferrer' : undefined"
                >
                  {{ action.label }}
                </UiButton>
              </div>
            </UiAlertDescription>
          </UiAlert>

          <div v-if="phoneChangeStep === 'number'" class="space-y-2">
            <UiLabel for="phone-change-input">Número novo</UiLabel>
            <UiInputGroup class="bg-background">
              <UiInputGroupAddon align="inline-start">
                <span class="font-semibold">+55</span>
              </UiInputGroupAddon>
              <UiInputGroupInput
                id="phone-change-input"
                :value="phoneChangeInput"
                type="tel"
                inputmode="numeric"
                autocomplete="tel-national"
                placeholder="(43) 98123-4567"
                :maxlength="16"
                @input="onPhoneChangeInput"
              />
            </UiInputGroup>
            <p class="shop-caption text-muted-foreground">
              O número antigo deixa de abrir esta conta assim que você confirmar.
            </p>
          </div>

          <div v-else class="space-y-2">
            <UiPinInput
              v-model="phoneChangeCode"
              :input-count="6"
              type="number"
              otp
              :aria-invalid="!!phoneChangeIssue"
              class="justify-between sm:justify-start"
            />
            <UiButton
              variant="link"
              size="sm"
              class="px-0"
              :loading="phoneChangePending"
              :disabled="phoneChangePending"
              @click="sendPhoneChangeCode"
            >
              Reenviar código
            </UiButton>
          </div>

          <UiDialogFooter>
            <UiButton variant="ghost" :disabled="phoneChangePending" @click="phoneChangeOpen = false">
              Cancelar
            </UiButton>
            <UiButton
              v-if="phoneChangeStep === 'number'"
              :loading="phoneChangePending"
              :disabled="phoneChangePending || !phoneChangeInput"
              @click="sendPhoneChangeCode"
            >
              Enviar código
            </UiButton>
            <UiButton
              v-else
              :loading="phoneChangePending"
              :disabled="phoneChangePending || phoneChangeCodeStr.length !== 6"
              @click="confirmPhoneChange"
            >
              Confirmar mudança
            </UiButton>
          </UiDialogFooter>
        </UiDialogContent>
      </UiDialog>

      <!-- Step-up: reconfirmar identidade por OTP antes de excluir/exportar -->
      <UiDialog v-model:open="stepUpOpen">
        <UiDialogContent>
          <UiDialogHeader>
            <UiDialogTitle>Confirme sua identidade</UiDialogTitle>
            <UiDialogDescription>
              Enviamos um código para o seu telefone. Digite-o para continuar com esta ação.
            </UiDialogDescription>
          </UiDialogHeader>
          <UiAlert v-if="stepUpIssue" variant="destructive">
            <UiAlertTitle>Não foi possível confirmar</UiAlertTitle>
            <UiAlertDescription>{{ stepUpIssue }}</UiAlertDescription>
          </UiAlert>
          <div class="space-y-2">
            <UiPinInput
              v-model="stepUpCode"
              :input-count="6"
              type="number"
              otp
              :aria-invalid="!!stepUpIssue"
              class="justify-between sm:justify-start"
            />
            <UiButton
              variant="link"
              size="sm"
              class="px-0"
              :loading="stepUpSendPending"
              :disabled="stepUpSendPending"
              @click="sendStepUpCode"
            >
              {{ stepUpSent ? 'Reenviar código' : 'Enviar código' }}
            </UiButton>
          </div>
          <UiDialogFooter>
            <UiButton variant="ghost" :disabled="stepUpPending" @click="stepUpOpen = false">Cancelar</UiButton>
            <UiButton :loading="stepUpPending" :disabled="stepUpPending || stepUpCodeStr.length !== 6" @click="confirmStepUp">
              Confirmar
            </UiButton>
          </UiDialogFooter>
        </UiDialogContent>
      </UiDialog>
    </div>
  </main>
</template>
