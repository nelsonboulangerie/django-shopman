import { useRegisterSW } from "virtual:pwa-register/vue";
import { bindPwaUpdateRegistration } from "../../app/composables/usePwaUpdate";

export default defineNuxtPlugin(() => {
  const registration = useRegisterSW({ immediate: true });
  bindPwaUpdateRegistration({
    needRefresh: registration.needRefresh,
    updateServiceWorker: registration.updateServiceWorker,
  });
});
