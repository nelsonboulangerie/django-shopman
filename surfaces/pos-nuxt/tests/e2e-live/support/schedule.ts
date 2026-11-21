// O passo "Para quando?" das jornadas de encomenda, pelo calendário da tela (#2976).
import { expect, type Page } from "@playwright/test";

import { dayMonth, nextOpenDay, type DayChoice } from "./nextOpenDay";

export interface ChosenDay extends DayChoice {
  /** `23/11`, como a tela escreve na linha e no aviso. */
  dayMonth: string;
  /** O dia escolhido é amanhã (a tela diz "amanhã" em vez de "seg, 23/11"). */
  isTomorrow: boolean;
}

/**
 * Toca no PRÓXIMO DIA ABERTO do seletor da encomenda: "Amanhã" quando a casa abre
 * amanhã; senão a próxima data em que ela abre, que o próprio seletor oferece.
 * Devolve o dia escolhido para a jornada conferir os números daquela data.
 */
export async function picksNextOpenDay(page: Page): Promise<ChosenDay> {
  const buttons = page.locator('[data-order-step="schedule"] [data-day-option]').locator("visible=true");
  await expect(buttons.first()).toBeVisible({ timeout: 30_000 });
  const options: DayChoice[] = await buttons.evaluateAll((elements) =>
    elements.map((el) => ({
      key: el.getAttribute("data-day-option") || "",
      iso: el.getAttribute("data-day-iso") || "",
      disabled: (el as HTMLButtonElement).disabled,
    })),
  );
  const chosen = nextOpenDay(options);
  if (!chosen) {
    throw new Error(`Nenhum dia aberto nos dias de um toque da tela: ${JSON.stringify(options)}`);
  }
  console.log(`DIA DA ENCOMENDA: ${chosen.iso} (${chosen.key}), entre ${JSON.stringify(options)}`);
  const button = buttons.and(page.locator(`[data-day-iso="${chosen.iso}"]`)).first();
  await button.click();
  await expect(button).toHaveAttribute("aria-checked", "true", { timeout: 15_000 });
  return { ...chosen, dayMonth: dayMonth(chosen.iso), isTomorrow: chosen.key === "tomorrow" };
}

/** "livres para amanhã" ou "livres para seg, 23/11": o dia como a tela o diz. */
export function dayPhrase(day: ChosenDay): string {
  return day.isTomorrow ? "amanhã" : `[^,\\s]{2,4}, ${day.dayMonth}`;
}
