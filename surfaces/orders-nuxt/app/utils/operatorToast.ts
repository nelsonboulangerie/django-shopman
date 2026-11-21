// O toast do Gestor é o do Nuxt UI (`useToast` + o toaster que o `OperatorAppRoot`
// monta). Os componentes do kit e os composables do app chamam `useSonner.error(…)`:
// esse é o nome do contrato de aviso da suíte, e cada app decide onde ele cai. No
// Gestor, o auto-import `useSonner` aponta para este objeto (nuxt.config), e não
// existe um segundo toaster.
//
// `useToast()` precisa do contexto do Nuxt, que se perde depois de um `await`; por
// isso o plugin cliente o captura uma vez na inicialização (`bindOperatorToast`).

type ToastApi = ReturnType<typeof useToast>;
type ToastColor = "error" | "success" | "info" | "warning";

let api: ToastApi | null = null;

export function bindOperatorToast(next: ToastApi) {
  api = next;
}

const ICONS: Record<ToastColor, string> = {
  error: "i-lucide-circle-alert",
  success: "i-lucide-circle-check",
  info: "i-lucide-info",
  warning: "i-lucide-triangle-alert",
};

function show(color: ToastColor, title: string) {
  api?.add({ title, color, icon: ICONS[color] });
}

export interface OperatorToastAction {
  label: string;
  /** Link (abre fora, como todo link do Admin). */
  to?: string;
  onClick?: () => void;
}

/** O aviso com UM gesto ("Promover a pergunta frequente", "Abrir no Admin"). */
function showWithAction(
  color: ToastColor,
  title: string,
  options: { description?: string; action?: OperatorToastAction } = {},
) {
  const { action, description } = options;
  api?.add({
    title,
    color,
    icon: ICONS[color],
    ...(description ? { description } : {}),
    ...(action
      ? {
          // Aviso com gesto não some sozinho (coordenação, 20/11/2026): o gesto só existe
          // aqui, então fica até o X ou o clique, sem barra de tempo.
          duration: 0,
          progress: false,
          actions: [
            {
              label: action.label,
              color,
              variant: "outline" as const,
              // O tamanho da suíte para gesto dentro de aviso (`alertActions`), nunca o `xs`.
              size: "md" as const,
              ...(action.to ? { to: action.to, target: "_blank" } : {}),
              ...(action.onClick ? { onClick: action.onClick } : {}),
            },
          ],
        }
      : {}),
  });
}

export const operatorToast = {
  withAction: showWithAction,
  error: (title: string) => show("error", title),
  success: (title: string) => show("success", title),
  info: (title: string) => show("info", title),
  warning: (title: string) => show("warning", title),
};
