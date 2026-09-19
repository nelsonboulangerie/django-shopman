import { useRegisterSW } from "virtual:pwa-register/vue";
import { bindPwaUpdateRegistration } from "../../app/composables/usePwaUpdate";

export default defineNuxtPlugin(() => {
  // `registerType: "prompt"` guarda o worker novo em "waiting" até todas as janelas
  // do host fecharem. Num app instalado que fica dias aberto isso nunca acontece, e
  // o aviso só aparece se o navegador chegar a buscar o `sw.js`. Guardar o registro
  // aqui é o que dá a `usePwaAutoUpdate` como PERGUNTAR (`registration.update()`).
  let swRegistration: ServiceWorkerRegistration | undefined;
  const registration = useRegisterSW({
    immediate: true,
    onRegisteredSW: (_url, active) => {
      swRegistration = active;
    },
  });
  bindPwaUpdateRegistration({
    needRefresh: registration.needRefresh,
    updateServiceWorker: registration.updateServiceWorker,
    checkForUpdate: async () => {
      if (!swRegistration) return false;
      await swRegistration.update();
      return true;
    },
  });
});
