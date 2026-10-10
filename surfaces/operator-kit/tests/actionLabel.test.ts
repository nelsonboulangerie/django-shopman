import { describe, expect, it } from "vitest";

import {
  actionFitAttrs,
  actionFitVars,
  adaptiveTitle,
  isAdaptive,
  labelWidthEm,
  shortOf,
} from "../app/presentation/actionLabel";

// Larguras reais da Instrument Sans, peso 500, medidas no Chromium a 14 px (o `md`):
// a conta nunca pode dar MENOS que o texto (o rótulo vazaria), e não deve passar de
// ~15% (o botão encolheria cedo demais).
const MEASURED_PX_AT_14 = [
  { text: "Enviar à cozinha", px: 104 },
  { text: "Salvar comanda", px: 104 },
  { text: "Cozinha", px: 53 },
  { text: "Salvar", px: 40 },
];

describe("rótulo que cabe: a conta da largura", () => {
  it("estima o texto com folga pequena e nunca abaixo do real", () => {
    for (const { text, px } of MEASURED_PX_AT_14) {
      const estimated = labelWidthEm(text) * 14;
      expect(estimated, text).toBeGreaterThanOrEqual(px);
      expect(estimated, text).toBeLessThan(px * 1.15);
    }
  });

  it("glifo desconhecido conta largo", () => {
    expect(labelWidthEm("€")).toBeGreaterThan(labelWidthEm("a"));
  });

  it("o curto só vale se for outro texto", () => {
    expect(shortOf({ label: "Enviar à cozinha", shortLabel: "Cozinha" })).toBe("Cozinha");
    expect(shortOf({ label: "Salvar", shortLabel: " Salvar " })).toBe("");
    expect(shortOf({ label: "Salvar", shortLabel: "  " })).toBe("");
  });

  it("só encolhe quem tem curto ou ícone", () => {
    expect(isAdaptive({ label: "Registrar sangria" })).toBe(false);
    expect(isAdaptive({ label: "Registrar sangria", shortLabel: "Sangria" })).toBe(true);
    expect(isAdaptive({ label: "Imprimir", icon: "i-lucide-printer" })).toBe(true);
  });
});

describe("rótulo que cabe: as variáveis do contêiner", () => {
  it("o grupo soma as ações e os espaços entre elas", () => {
    const one = actionFitVars([{ label: "Salvar", icon: "i-lucide-save" }]);
    const two = actionFitVars([
      { label: "Salvar", icon: "i-lucide-save" },
      { label: "Salvar", icon: "i-lucide-save" },
    ]);
    const em = (value: string) => Number(/([\d.]+)em/.exec(value)?.[1] ?? 0);
    const rem = (value: string) => Number(/([\d.]+)rem/.exec(value)?.[1] ?? 0);
    expect(em(two["--op-fit-full"])).toBeCloseTo(em(one["--op-fit-full"]) * 2, 2);
    // padding 2×0,625 + ícone 1,25 + gap 0,375 + borda 2×0,0625 = 3; dois e o gap-2.
    expect(rem(one["--op-fit-full"])).toBeCloseTo(3, 3);
    expect(rem(two["--op-fit-full"])).toBeCloseTo(6.5, 3);
  });

  it("o limite do curto usa o curto declarado e, sem curto, o completo", () => {
    const vars = actionFitVars([
      { label: "Enviar à cozinha", shortLabel: "Cozinha", icon: "i-lucide-chef-hat" },
      { label: "Fechar", icon: "i-lucide-x" },
    ]);
    const expectedEm = labelWidthEm("Cozinha") + labelWidthEm("Fechar");
    expect(vars["--op-fit-short"]).toContain(`${Math.round(expectedEm * 1000) / 1000}em`);
  });

  it("o mínimo do grupo é o último degrau: ícone quadrado, ou o curto sem ícone", () => {
    const icons = actionFitVars([
      { label: "Pausar", icon: "i-lucide-pause" },
      { label: "Ativar", icon: "i-lucide-play" },
    ]);
    // md: ícone 1.25 + respiro 0.375 × 2 + borda 0.0625 × 2 = 2.125 rem cada, + gap 0.5.
    expect(icons["--op-fit-min"]).toBe("4.75rem");
    const text = actionFitVars([{ label: "Registrar sangria", shortLabel: "Sangria" }]);
    expect(text["--op-fit-min"]).toContain(`${Math.round(labelWidthEm("Sangria") * 1000) / 1000}em`);
  });

  it("sem nenhum ícone no grupo não há degrau só ícone: o curto vale até zero", () => {
    const vars = actionFitVars([{ label: "Registrar sangria", shortLabel: "Sangria" }]);
    expect(vars["--op-fit-short"]).toBe("0px");
  });

  it("o tamanho muda a anatomia (xl tem respiro e ícone maiores)", () => {
    const md = actionFitVars([{ label: "Pronto", icon: "i-lucide-check" }], { size: "md" });
    const xl = actionFitVars([{ label: "Pronto", icon: "i-lucide-check" }], { size: "xl" });
    expect(md["--op-fit-full"]).not.toBe(xl["--op-fit-full"]);
  });

  it("reserva soma o que o contêiner gasta com o que não é ação", () => {
    const plain = actionFitVars([{ label: "Pausar", icon: "i-lucide-pause" }]);
    const reserved = actionFitVars([{ label: "Pausar", icon: "i-lucide-pause" }], { reserve: 2 });
    expect(plain["--op-fit-full"]).not.toBe(reserved["--op-fit-full"]);
  });
});

describe("rótulo que cabe: atributos do botão", () => {
  it("o nome acessível e a dica são o completo; fora de grupo leva a própria conta", () => {
    const attrs = actionFitAttrs({ label: "Enviar à cozinha", shortLabel: "Cozinha", icon: "i-lucide-chef-hat" });
    expect(attrs["aria-label"]).toBe("Enviar à cozinha");
    expect(attrs.title).toBe("Enviar à cozinha");
    expect(attrs["data-op-fit"]).toBe("md");
    expect(attrs["data-op-fit-icon"]).toBe("");
    expect(attrs.style).toHaveProperty("--op-fit-full");
  });

  it("dentro de grupo não escreve a própria conta (usa a do grupo)", () => {
    const attrs = actionFitAttrs({ label: "Salvar", icon: "i-lucide-save" }, { grouped: true });
    expect(attrs.style).toBeUndefined();
  });

  it("o ariaLabel mais longo da ação vence", () => {
    expect(adaptiveTitle({ label: "Desfazer 0131", ariaLabel: "Desfazer o Pronto do 0131", icon: "i-lucide-undo" })).toBe(
      "Desfazer o Pronto do 0131",
    );
  });

  it("botão que não encolhe não ganha dica repetindo o texto", () => {
    expect(actionFitAttrs({ label: "Registrar sangria" })).toEqual({});
    expect(adaptiveTitle({ label: "Registrar sangria" })).toBeUndefined();
  });
});
