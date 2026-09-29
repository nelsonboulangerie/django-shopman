/**
 * O que "Impressa?" e "Por e-mail?" prometem, dito na faixa de avisos do
 * pagamento.
 *
 * Não existe DANFE nem XML sem NFC-e autorizada: o papel é o espelho da nota e
 * o anexo do e-mail é o mesmo espelho mais o XML. Pedir qualquer um dos dois é
 * pedir a nota, tanto quanto "CPF na nota?". Quem confirma que a regra fiscal
 * deste deployment lê esses canais é o servidor
 * (`capabilities.receipt_requests_emission`); a tela só repete.
 *
 * O "assim que autorizar" fica: a emissão é assíncrona e quem autoriza é a
 * SEFAZ. Prometer o instante seria outra mentira.
 */
import type { POSCheckoutContractProjection } from "~/types/pos";

/** A regra fiscal deste deployment emite quando o balcão pede o comprovante? */
export function receiptRequestEmits(contract: POSCheckoutContractProjection | null | undefined): boolean {
  return contract?.capabilities?.receipt_requests_emission === true;
}

/** A frase da faixa de avisos para os canais pedidos; vazia quando nenhum foi. */
export function receiptRequestNote(input: { print: boolean; email: boolean; emits: boolean }): string {
  const { print, email, emits } = input;
  if (!print && !email) return "";
  if (emits) {
    if (print && email) return "Papel e e-mail já pedem a nota: ela imprime sozinha, e o e-mail sai assim que ela for autorizada.";
    if (print) return "Pedir papel já pede a nota: ela imprime sozinha assim que for autorizada.";
    return "Pedir por e-mail já pede a nota: o e-mail sai assim que ela for autorizada.";
  }
  // Sem a palavra do servidor, a nota só nasce por outra regra. Prometer que o
  // papel ou o e-mail saem num dinheiro sem CPF seria a promessa que não se cumpre.
  if (print && email) return "A nota impressa e a por e-mail saem quando houver NFC-e (CPF, cartão ou Pix).";
  if (print) return "A nota impressa sai quando houver NFC-e (CPF, cartão ou Pix).";
  return "A nota por e-mail sai quando houver NFC-e (CPF, cartão ou Pix).";
}
