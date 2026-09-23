import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrail do ESPELHO do guia de instalação.
//
// `installGuide.ts` responde a uma pergunta que as NOVE superfícies fazem igual: "o que
// este navegador, neste sistema, faz para colocar o app na tela inicial?". A resposta é
// fato de plataforma, não voz de marca — e por isso tem que ser a mesma na loja e no
// balcão.
//
// O storefront fica fora da layer de propósito (superfície de cliente, marca e harness
// próprios, `nuxt.config.ts` sem `extends`), então não existe import a compartilhar. A
// alternativa real era cópia, e cópia sem trava deriva: o próprio repositório já tem
// `MoreBelow`, `OfflineBanner`, `useConnectivity` e `tw-helper` duplicados entre kit e
// loja, e o `UiFilterChip` registra em comentário uma cópia que caiu para `h-9`.
//
// Então a cópia é declarada e travada: byte a byte. Se um dia precisar divergir,
// divirja de propósito — apague esta trava e escreva por quê.
const here = dirname(fileURLToPath(import.meta.url));
const KIT = resolve(here, "../app/utils/installGuide.ts");
const LOJA = resolve(here, "../../storefront-nuxt/app/utils/installGuide.ts");

describe("espelho do guia de instalação", () => {
  it("os dois lados existem", () => {
    expect(existsSync(KIT)).toBe(true);
    expect(existsSync(LOJA)).toBe(true);
  });

  it("kit e loja são byte a byte o mesmo arquivo", () => {
    // A mensagem do `expect` sobre string longa mostra a primeira linha divergente —
    // que é exatamente o que quem editou um lado só precisa ver.
    expect(readFileSync(LOJA, "utf8")).toBe(readFileSync(KIT, "utf8"));
  });
});
