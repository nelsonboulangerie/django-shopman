/**
 * CPF e CNPJ: o dígito verificador, do lado da tela.
 *
 * O checkout ecoava "Sai na nota: CPF 111.111.111-11" com um check verde para
 * ONZE DÍGITOS QUAISQUER. O operador lia de volta com confiança, o cliente
 * confirmava, a venda fechava — e a rejeição da NFC-e chegava com o cliente já
 * na rua. Contar dígitos não é conferir documento.
 *
 * Os nomes ficam em português porque `cpf` e `cnpj` são nome próprio de
 * documento brasileiro, como `IBAN`: traduzir produziria um nome que não existe.
 */

function digitsOf(value: string): string {
  return String(value || "").replace(/\D/g, "");
}

/** Dígito de módulo 11 sobre os `weights` dados. */
function mod11(digits: string, weights: number[]): number {
  const sum = weights.reduce((acc, weight, i) => acc + Number(digits[i]) * weight, 0);
  const rest = sum % 11;
  return rest < 2 ? 0 : 11 - rest;
}

export function isValidCpf(value: string): boolean {
  const d = digitsOf(value);
  if (d.length !== 11) return false;
  // Repetido passa na aritmética (111.111.111-11 fecha os dois dígitos) e é a
  // sequência que mais aparece quando alguém digita sem olhar.
  if (/^(\d)\1{10}$/.test(d)) return false;
  const first = mod11(d, [10, 9, 8, 7, 6, 5, 4, 3, 2]);
  const second = mod11(d, [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]);
  return Number(d[9]) === first && Number(d[10]) === second;
}

export function isValidCnpj(value: string): boolean {
  const d = digitsOf(value);
  if (d.length !== 14) return false;
  if (/^(\d)\1{13}$/.test(d)) return false;
  const first = mod11(d, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
  const second = mod11(d, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
  return Number(d[12]) === first && Number(d[13]) === second;
}

/** O documento que sai na nota: CPF (11) ou CNPJ (14), os dois conferidos. */
export function isValidTaxId(value: string): boolean {
  const d = digitsOf(value);
  if (d.length === 11) return isValidCpf(d);
  if (d.length === 14) return isValidCnpj(d);
  return false;
}
