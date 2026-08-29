// A trava da gaveta na tela.
//
// Dois silêncios deliberados, e os dois são desenho de segurança:
//
// 1. NÃO existe "Já fechei" — auto-declaração era a mentira que o sensor existe
//    para desmentir, e o bypass mais barato do sistema (com o diálogo na tela,
//    puxar o cabo e clicar nele liberava a venda calado).
// 2. NÃO existe botão de PIN — mostrar a saída de emergência ensina o bypass: a
//    exceção vira o caminho conhecido e a fraude aprende sozinha. Quem foi
//    treinado sabe que Esc abre o PIN.
//
// O que fica escondido é a SAÍDA. O ESTADO continua anunciado a leitor de tela.
import { describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosDrawerLockDialog from "~/components/PosDrawerLockDialog.vue";

async function render(props: Record<string, unknown> = {}) {
  document.body.innerHTML = "";
  const wrapper = await mountSuspended(PosDrawerLockDialog, { props: { open: true, ...props } });
  await new Promise((resolve) => setTimeout(resolve, 50));
  return { wrapper, texto: document.body.textContent || "" };
}

describe("PosDrawerLockDialog — o que a tela DIZ", () => {
  it("diz o estado e o que fazer, em uma linha só", async () => {
    const { texto } = await render();

    expect(texto).toContain("Gaveta aberta");
    expect(texto).toContain("Feche a gaveta para continuar");
  });

  it("não repete a mesma ideia duas vezes", async () => {
    // "O balcão volta sozinho" era redundante com "para continuar".
    expect((await render()).texto).not.toContain("volta sozinho");
  });

  it("mostra que está esperando o mundo físico", async () => {
    expect((await render()).texto).toContain("Aguardando a gaveta fechar");
  });
});

describe("PosDrawerLockDialog — o que a tela ESCONDE", () => {
  it("NÃO oferece 'Já fechei': auto-declaração foi removida de propósito", async () => {
    expect((await render()).texto).not.toContain("Já fechei");
  });

  it("NÃO insinua a saída de emergência: nem botão, nem texto sobre PIN", async () => {
    const { texto } = await render();

    expect(texto.toLowerCase()).not.toContain("pin");
    expect(texto.toLowerCase()).not.toContain("gerente");
    expect(texto.toLowerCase()).not.toContain("libera");
    expect(texto.toLowerCase()).not.toContain("sensor");
  });

  it("nenhum botão tem TEXTO: a saída existe, mas não se anuncia", async () => {
    const { wrapper } = await render();
    const rotulos = [...document.querySelectorAll('[role="alertdialog"] button')]
      .map((b) => (b.textContent || "").trim())
      .filter(Boolean)
      .filter((t) => t !== "Close");

    expect(rotulos).toEqual([]);
    wrapper.unmount();
  });
});

describe("PosDrawerLockDialog — o estado continua acessível", () => {
  it("é alertdialog e anuncia a espera a leitor de tela", async () => {
    await render();

    expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
    const status = document.querySelector('[role="status"]');
    expect(status?.getAttribute("aria-live")).toBe("polite");
    expect(status?.textContent).toContain("Aguardando a gaveta fechar");
  });
});

describe("PosDrawerLockDialog — Esc é o gesto treinado", () => {
  it("Esc pede o gerente em vez de fechar a trava", async () => {
    const { wrapper } = await render();

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(wrapper.emitted("manager")).toBeTruthy();
    // O MESMO Esc não pode desistir da venda por baixo do PIN.
    expect(wrapper.emitted("update:open")).toBeFalsy();
  });
});


// ── A porta para quem não tem teclado ─────────────────────────────────────
//
// O dono decidiu: três pontinhos discretos no canto. Esc continua valendo em
// paralelo (é o gesto rápido de quem tem teclado); os pontinhos são o mesmo
// caminho para o balcão de toque.

describe("PosDrawerLockDialog — os três pontinhos", () => {
  it("existem, e levam ao MESMO lugar que o Esc", async () => {
    const { wrapper } = await render();
    const dots = document.querySelector<HTMLButtonElement>("[data-drawer-lock-escape-hatch]");

    expect(dots).not.toBeNull();
    dots!.click();
    await new Promise((r) => setTimeout(r, 10));

    expect(wrapper.emitted("manager")).toBeTruthy();
    expect(wrapper.emitted("update:open")).toBeFalsy();
  });

  it("não dizem NADA sobre PIN, gerente ou destrave — nem no nome acessível", async () => {
    await render();
    const dots = document.querySelector("[data-drawer-lock-escape-hatch]")!;
    const nome = (dots.getAttribute("aria-label") || "").toLowerCase();

    expect(nome).toBeTruthy(); // leitor de tela precisa de nome
    for (const palavra of ["pin", "gerente", "destrav", "libera", "senha", "emerg"]) {
      expect(nome).not.toContain(palavra);
    }
    expect((dots.textContent || "").trim()).toBe("");
  });

  it("o alvo de toque é grande, mesmo o desenho sendo minúsculo", async () => {
    await render();
    const classe = document.querySelector("[data-drawer-lock-escape-hatch]")!.className;

    // size-11 = 44px, o mínimo de alvo de toque. Discrição é do desenho.
    expect(classe).toContain("size-11");
  });

  it("é alcançável por teclado (não sai da ordem de foco)", async () => {
    await render();
    const dots = document.querySelector("[data-drawer-lock-escape-hatch]")!;

    // Sem `tabindex=-1`: tirar do Tab esconderia a saída do gerente cego junto
    // com o operador curioso, e a proteção real é o PIN, não a obscuridade.
    expect(dots.getAttribute("tabindex")).toBeNull();
    expect(dots.getAttribute("aria-hidden")).toBeNull();
  });

  it("some quando o diálogo fecha: nada de porta sobrando na tela", async () => {
    const { wrapper } = await render();
    expect(document.querySelector("[data-drawer-lock-escape-hatch]")).not.toBeNull();

    await wrapper.setProps({ open: false });
    await new Promise((r) => setTimeout(r, 50));

    expect(document.querySelector("[data-drawer-lock-escape-hatch]")).toBeNull();
  });
});
