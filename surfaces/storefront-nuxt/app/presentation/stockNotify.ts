/** Confirmação posterior à identidade e ao opt-in explícito. */
export function notifyConfirmationMessage (): string {
  return 'Aviso recorrente ativo. Você pode gerenciá-lo nas preferências.'
}

/**
 * Favoritar um esgotado com opt-in de WhatsApp e maioridade provada anota o
 * aviso. Só se diz isto quando ESTE favorito criou a inscrição — nunca como
 * promessa de um favorito sozinho.
 */
export function favoriteNotedAlertMessage (): string {
  return 'Salvo nos favoritos, com aviso ativo: avisamos pelo WhatsApp quando voltar. Você pode gerenciá-lo nas preferências.'
}
