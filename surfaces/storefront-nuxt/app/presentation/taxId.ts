/**
 * CPF/CNPJ da nota fiscal da ENTREGA, do lado da tela.
 *
 * Decisão do dono (24/09/2026): a nota da entrega a domicílio não sai sem o
 * CPF ou CNPJ de quem compra (a SEFAZ recusa, 787/788), então a loja pede o
 * documento no passo do endereço. Sem ele a entrega não fecha; a retirada
 * continua aberta. Quem decide SE a entrega pede CPF é o servidor
 * (`delivery_requires_tax_id` na projeção do checkout, perguntado ao mesmo
 * resolver que decide a emissão); aqui só se confere o que foi digitado, cedo
 * e no campo, com as MESMAS frases da recusa do servidor.
 *
 * Os nomes ficam em português porque `cpf` e `cnpj` são nome próprio de
 * documento brasileiro.
 */

export const TAX_ID_REQUIRED_MESSAGE = 'Para entregar, precisamos do CPF ou CNPJ para a nota fiscal.'
export const TAX_ID_INVALID_MESSAGE = 'Confira o CPF ou CNPJ: os números não conferem.'
export const TAX_ID_WHY = 'A nota fiscal vai junto com a entrega e precisa do CPF ou CNPJ de quem compra.'

export function taxIdDigits (value: string | null | undefined): string {
  return String(value || '').replace(/\D/g, '')
}

function mod11 (digits: string, weights: number[]): number {
  const sum = weights.reduce((acc, weight, i) => acc + Number(digits[i]) * weight, 0)
  const rest = sum % 11
  return rest < 2 ? 0 : 11 - rest
}

export function isValidCpf (value: string): boolean {
  const d = taxIdDigits(value)
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false
  return Number(d[9]) === mod11(d, [10, 9, 8, 7, 6, 5, 4, 3, 2]) &&
    Number(d[10]) === mod11(d, [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
}

export function isValidCnpj (value: string): boolean {
  const d = taxIdDigits(value)
  if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false
  return Number(d[12]) === mod11(d, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) &&
    Number(d[13]) === mod11(d, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
}

/** CPF (11) ou CNPJ (14), os dois conferidos pelo dígito verificador. */
export function isValidTaxId (value: string): boolean {
  const d = taxIdDigits(value)
  if (d.length === 11) return isValidCpf(d)
  if (d.length === 14) return isValidCnpj(d)
  return false
}

/** Máscara de leitura enquanto se digita: 000.000.000-00 ou 00.000.000/0000-00. */
export function formatTaxId (value: string | null | undefined): string {
  const d = taxIdDigits(value).slice(0, 14)
  if (d.length <= 11) {
    return d
      .replace(/^(\d{3})(\d)/, '$1.$2')
      .replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
      .replace(/\.(\d{3})(\d{1,2})$/, '.$1-$2')
  }
  return d
    .replace(/^(\d{2})(\d)/, '$1.$2')
    .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
    .replace(/^(\d{2})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3/$4')
    .replace(/\/(\d{4})(\d{1,2})$/, '/$1-$2')
}

/**
 * O erro do campo, ou `''` quando pode seguir.
 *
 * Vazio só é erro quando a entrega PEDE o documento. Digitado errado é erro
 * sempre: CPF informado já é pedido de nota, e o servidor recusa.
 */
export function deliveryTaxIdError (value: string | null | undefined, required: boolean): string {
  const digits = taxIdDigits(value)
  if (!digits) return required ? TAX_ID_REQUIRED_MESSAGE : ''
  return isValidTaxId(digits) ? '' : TAX_ID_INVALID_MESSAGE
}

/**
 * Enquanto a pessoa ainda está digitando, não se acusa erro: 10 dígitos de um
 * CPF não são "números que não conferem", são um CPF pela metade. O aviso de
 * dígito errado aparece quando o tamanho fecha (11 ou 14) ou ao tentar seguir.
 */
export function taxIdLooksComplete (value: string | null | undefined): boolean {
  const length = taxIdDigits(value).length
  return length === 11 || length >= 14
}
