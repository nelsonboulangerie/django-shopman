// A ação dentro de um aviso acompanha a cor do aviso (dono, 09/10/2026): a principal é
// `solid` na cor do aviso, a secundária é `outline` na mesma cor. Nunca um `primary` ou um
// `neutral` "normal" dentro de um aviso info/warning/error/success: o botão de outra cor
// lê como outra conversa, colada no aviso.
//
// Toda `NuxtAlert`/`UAlert` com `:actions` passa por aqui (trava em
// `tests/guardrails.alertActions.test.ts`): a cor e a variante saem do aviso, nunca da
// chamada. O tamanho é o da suíte (`md`), nunca o `xs` do default do aviso.
import type { ButtonProps } from "@nuxt/ui";

export type AlertActionColor = "info" | "success" | "warning" | "error" | "primary" | "neutral";

export type AlertActionInput = Omit<ButtonProps, "color" | "variant"> & {
  /** Secundária (`outline`). Sem dizer: a primeira é a principal, as outras secundárias. */
  secondary?: boolean;
};

export type AlertAction = Omit<AlertActionInput, "secondary"> & {
  color: AlertActionColor;
  variant: "solid" | "outline";
};

export function alertActions(
  color: AlertActionColor | undefined,
  actions: readonly (AlertActionInput | false | null | undefined)[],
): AlertAction[] {
  const tone = color ?? "primary";
  return actions
    .filter((action): action is AlertActionInput => Boolean(action))
    .map(({ secondary, ...action }, index) => ({
      size: "md",
      ...action,
      color: tone,
      variant: (secondary ?? index > 0) ? "outline" : "solid",
    }));
}
