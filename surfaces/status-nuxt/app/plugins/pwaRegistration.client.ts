import { useRegisterSW } from "virtual:pwa-register/vue";

export default defineNuxtPlugin(() => {
  // Registra sem forçar a troca do worker em abas abertas. O casco offline fica
  // disponível, mas uma versão nova só assume quando o navegador puder fazê-lo
  // com segurança — nunca interrompendo uma consulta de status em andamento.
  useRegisterSW({ immediate: true });
});
