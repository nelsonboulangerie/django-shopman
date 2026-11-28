// Clique nunca inerte, na raiz (DEV-2026-094): todo `NuxtButton` da suíte nasce com o
// `loadingAuto` do Nuxt UI ligado.
//
// Com ele, o botão cujo `@click` devolve promessa fica girando (`line-md:loading-loop`,
// o ícone de carregando do tema) e DESABILITADO do toque até a promessa assentar, com
// sucesso ou erro: o operador vê que o toque chegou, e o toque repetido não dispara a
// ação de novo. É o contrato da `usePendingAction`, sem depender de cada tela lembrar.
// Clique síncrono (abrir painel, trocar aba) não muda nada: a promessa assenta na
// mesma volta e o botão nunca chega a desenhar o giro. Botão de envio dentro de
// `NuxtForm` ganha o mesmo estado enquanto o `@submit` assíncrono corre.
//
// O Nuxt UI não tem padrão global de prop, então o padrão é escrito na definição do
// componente, uma vez, antes da primeira montagem. Quem precisa do comportamento
// antigo escreve `:loading-auto="false"` no botão (ex.: um clique que abre um fluxo
// que espera o operador e não deve parecer ocupado).
//
// A trava `tests/components/ButtonPendingByDefault.test.ts` reprova se uma subida do
// Nuxt UI tirar ou renomear o `loadingAuto`.
import Button from "@nuxt/ui/components/Button.vue";

interface PropOption {
  type?: unknown;
  default?: unknown;
}

export function enableButtonPendingByDefault(component: unknown): boolean {
  const props = (component as { props?: Record<string, PropOption> } | null)?.props;
  const option = props?.loadingAuto;
  if (!option) return false;
  option.default = true;
  return true;
}

export default defineNuxtPlugin({
  name: "operator-kit:button-pending-by-default",
  enforce: "pre",
  setup() {
    enableButtonPendingByDefault(Button);
  },
});
