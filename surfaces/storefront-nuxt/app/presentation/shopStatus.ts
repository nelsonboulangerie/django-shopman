// O estado da casa no cabeçalho.
//
// O servidor manda uma frase só ("Fechado agora. Abrimos amanhã às 9h"). Em 375 px
// a barra de status tem uns 213 px, e o corte no fim levava justamente a hora,
// que é a parte que a cliente precisa (excelência da loja, P2-04). A frase se
// divide na última fronteira de frase: o começo (o estado) pode sair da tela
// estreita, o fim (quando abre) nunca trunca. Frase de uma sentença só ("Aberto
// até 18h") não se divide.
export interface HeaderStatusParts {
  /** O estado ("Fechado agora."). Vazio quando a frase é uma sentença só. */
  lead: string
  /** O que importa agora e nunca corta ("Abrimos amanhã às 9h"). */
  tail: string
}

export function headerStatusParts (label: string | null | undefined): HeaderStatusParts {
  const text = (label || '').trim()
  const boundary = text.lastIndexOf('. ', text.endsWith('.') ? text.length - 2 : text.length)
  if (boundary <= 0) return { lead: '', tail: text }
  return { lead: text.slice(0, boundary + 1), tail: text.slice(boundary + 2).trim() }
}
