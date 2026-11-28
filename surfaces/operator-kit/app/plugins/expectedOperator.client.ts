// Toda GRAVAÇÃO no backstage leva o operador que a tela mostra, e a recusa por
// troca de pessoa relê quem opera. Plugin da layer: vale para os apps que fazem
// `extends` do kit, sem que nenhuma chamada precise lembrar. A regra (o que manda,
// quando, e o que é a recusa) é pura e mora em `presentation/operatorLock.ts`;
// aqui só o encaixe no `$fetch` global (o que `$fetch`, `useFetch` e os helpers
// de ação dos apps usam).
import type { OperatorSession } from "../types/operator";
import { expectedOperatorHeader, isOperatorChanged } from "../presentation/operatorLock";

export default defineNuxtPlugin((nuxtApp) => {
  const { data } = useNuxtData<OperatorSession>("operator-session");
  const base = globalThis.$fetch;
  globalThis.$fetch = base.create({
    onRequest({ request, options }) {
      const url = typeof request === "string" ? request : request.url;
      const expected = expectedOperatorHeader(url, options.method, data.value ?? null);
      if (!expected) return;
      const headers = new Headers(options.headers as HeadersInit | undefined);
      headers.set("x-shopman-operator", expected);
      options.headers = headers;
    },
    async onResponseError({ response }) {
      if (!isOperatorChanged(response.status, response._data)) return;
      // A tela segue a pessoa de verdade; a frase da recusa ("Nada foi gravado")
      // chega a quem chamou pelo `detail`, como toda recusa.
      await nuxtApp.runWithContext(() => refreshNuxtData("operator-session"));
    },
  }) as typeof globalThis.$fetch;
});
