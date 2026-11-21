// O PRÓXIMO DIA ABERTO, para as jornadas que montam encomenda de outro dia (#2976).
//
// As jornadas tocavam no rádio "Amanhã" fixo. Na véspera de dia de loja fechada o
// rádio vem desabilitado ("Amanhã, Dom 22/11 · fechado") e a jornada parava no
// "Para quando?", antes de provar qualquer coisa. O calendário quem tem é a tela:
// os três dias de um toque do kit (`quickDayOptions`: hoje, amanhã e a próxima data
// em que a casa abre, cada um apagado com o motivo quando não se escolhe). A jornada
// lê esses botões e escolhe o primeiro aberto depois de hoje; ela não sabe nem
// adivinha o horário da loja.
//
// Puro (sem Playwright): o vitest do PDV prova a escolha contra o mesmo
// `quickDayOptions` que a tela desenha (`tests/nextOpenDay.test.ts`).

/** Um botão do "Dia" como a tela o desenha (`data-day-option`, `data-day-iso`, `disabled`). */
export interface DayChoice {
  key: string;
  iso: string;
  disabled: boolean;
}

/**
 * O primeiro dia aberto depois de hoje, na ordem da tela: "Amanhã", depois a próxima
 * data. "Hoje" e "Outra data" não contam. Nenhum aberto: `null` (quem chama diz por quê).
 */
export function nextOpenDay(options: readonly DayChoice[]): DayChoice | null {
  for (const key of ["tomorrow", "next"]) {
    const option = options.find((candidate) => candidate.key === key);
    if (option && !option.disabled && option.iso) return option;
  }
  return null;
}

/** `2026-11-23` → `23/11`, como a tela escreve a data na linha e no aviso. */
export function dayMonth(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

/**
 * Quanto o `seed` planeja de uma receita para a data: a base nos dias comuns e 25% a
 * mais na sexta e no sábado, arredondado como o `Decimal.quantize` do Python
 * (metade para o par). Espelho de `config/management/commands/seed.py` (o plano
 * futuro, `day_multiplier`); a Baguette de Tradition tem base 22, então são 22 de
 * segunda a quinta e 28 na sexta e no sábado.
 */
export function seedPlannedQty(baseQty: number, iso: string): number {
  const weekday = new Date(`${iso}T12:00:00Z`).getUTCDay(); // 5 = sexta, 6 = sábado
  const raw = weekday === 5 || weekday === 6 ? baseQty * 1.25 : baseQty;
  const floor = Math.floor(raw);
  const fraction = raw - floor;
  if (Math.abs(fraction - 0.5) < 1e-9) return floor % 2 === 0 ? floor : floor + 1;
  return Math.round(raw);
}
