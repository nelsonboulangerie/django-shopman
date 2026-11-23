// Um relógio de minuto para a página inteira (#2807): os selos de urgência escrevem
// "há 12 min" e "acaba em 2h" a partir dele, e somem quando o fato vence.
//
// Nasce do instante do servidor (`useState` atravessa o payload), para a hidratação
// escrever o mesmo texto que o HTML; no navegador anda de minuto em minuto, um
// intervalo só por aba, por mais cards que leiam.
let ticker: ReturnType<typeof setInterval> | null = null

export function useMinuteClock () {
  const now = useState<number>('minute-clock', () => Date.now())
  if (import.meta.client) {
    onMounted(() => {
      now.value = Date.now()
      if (ticker === null) ticker = setInterval(() => { now.value = Date.now() }, 60_000)
    })
  }
  return now
}
