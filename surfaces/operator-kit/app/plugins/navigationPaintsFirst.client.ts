// Pinta antes de trabalhar (DEV-2026-094): a troca de página espera UM quadro pintado.
//
// Medido em 25/11/2026: no Compras, tocar "Lançar os custos" disparava a troca de seção
// e a thread principal ficava presa ~380 ms montando a tela nova. Tudo o que diz "o
// toque chegou" (o link esmaecido, a barra de rota, o giro do botão) já estava no DOM,
// mas nada podia pintar até a tarefa longa acabar: para quem tocou, a tela congelava.
//
// Este guarda roda depois do middleware (o plugin do roteador do Nuxt registra o dele
// antes) e só deixa a navegação seguir depois do próximo quadro. Custo: um quadro
// (~16 ms) por troca de página. Aba em segundo plano não pinta, por isso a espera tem
// teto curto e nunca segura a navegação.
export function nextPaint(ceilingMs = 50): Promise<void> {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve();
    };
    requestAnimationFrame(() => setTimeout(finish, 0));
    setTimeout(finish, ceilingMs);
  });
}

export default defineNuxtPlugin({
  name: "operator-kit:navigation-paints-first",
  setup(nuxtApp) {
    const router = useRouter();
    router.beforeEach(async (to, from) => {
      if (nuxtApp.isHydrating || to.path === from.path) return;
      await nextPaint();
    });
  },
});
