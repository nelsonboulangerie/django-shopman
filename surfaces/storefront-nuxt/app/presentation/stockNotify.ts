// "Avise-me quando voltar": o número que a casa VAI usar, de volta na tela.
//
// O que a pessoa digita não é necessariamente o que fica gravado. O normalizador
// completa o DDD da loja, descarta o "55" do país e repara celular antigo de 10
// dígitos inserindo o nono (`repairLegacyBrazilianMobile`). Isso é bom quando o
// palpite acerta, e é grave quando erra: um número de 10 dígitos digitado às
// cegas virou 11 dígitos válidos de OUTRA pessoa, e o "voltou ao estoque" foi
// entregue a um desconhecido. A correção honesta é mostrar o resultado da conta
// ANTES do envio, para a pessoa conferir e corrigir.

import { displayE164Phone, normalizeAuthPhone } from '~/utils/authPhone'

// Menos que isso ainda é número pela metade; anunciar destino a cada tecla só
// faria a linha piscar com um número que nem existe.
const MIN_NATIONAL_DIGITS = 10

/**
 * Telefone formatado que a casa usará para o aviso, ou string vazia enquanto o
 * número ainda não está completo. Não valida nada: só revela a normalização.
 */
export function notifyPhoneTarget (raw: string, defaultDdd = ''): string {
  const normalized = normalizeAuthPhone(raw, 'BR', defaultDdd)
  if (!normalized) return ''
  const digits = normalized.replace(/\D/g, '')
  const national = normalized.startsWith('+55') ? digits.length - 2 : digits.length
  if (national < MIN_NATIONAL_DIGITS) return ''
  return displayE164Phone(normalized)
}

/** Confirmação do aviso, nomeando o número quando ele é conhecido. */
export function notifyConfirmationMessage (normalizedPhone: string): string {
  const display = normalizedPhone ? displayE164Phone(normalizedPhone) : ''
  return display
    ? `Pronto. Avisaremos você no ${display}.`
    : 'Pronto. Avisaremos você quando estiver disponível.'
}
