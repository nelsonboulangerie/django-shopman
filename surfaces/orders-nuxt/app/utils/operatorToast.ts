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

export const operatorToast = {
  error: (title: string) => show("error", title),
  success: (title: string) => show("success", title),
  info: (title: string) => show("info", title),
  warning: (title: string) => show("warning", title),
};
