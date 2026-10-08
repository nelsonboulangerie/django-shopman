// Liga o contrato de aviso da suíte (`useSonner`) ao toast do Nuxt UI, com o
// contexto do app ainda disponível. Ver `utils/operatorToast.ts`.
export default defineNuxtPlugin(() => {
  bindOperatorToast(useToast());
});
