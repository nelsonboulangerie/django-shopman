import { describe, expect, it } from "vitest";

import {
  SEARCH_THRESHOLD,
  filterOptions,
  firstEnabledIndex,
  indexOfValue,
  isSearchable,
  lastEnabledIndex,
  normalizeText,
  resultsAnnouncement,
  selectedOption,
  stepIndex,
} from "../app/presentation/choice";
import type { ChoiceOption } from "../app/types/choice";

const modelos: ChoiceOption[] = [
  { value: "promo_pao", label: "Promoção de pão", hint: "utility · pt_BR" },
  { value: "promo_cafe", label: "Promoção de café", hint: "marketing · pt_BR" },
  { value: "aviso_padrao", label: "Aviso padrão", keywords: "WA_NOTICE_STD" },
  { value: "encerrado", label: "Encerrado", disabled: true },
];

describe("busca", () => {
  it("ignora acento e caixa — o operador digita com uma mão só", () => {
    expect(normalizeText("Promoção de CAFÉ")).toBe("promocao de cafe");
    expect(filterOptions(modelos, "promocao")).toHaveLength(2);
    expect(filterOptions(modelos, "PADRAO").map((o) => o.value)).toEqual(["aviso_padrao"]);
  });

  it("casa todos os termos em qualquer ordem", () => {
    expect(filterOptions(modelos, "cafe promo").map((o) => o.value)).toEqual(["promo_cafe"]);
    expect(filterOptions(modelos, "promo inexistente")).toEqual([]);
  });

  it("acha pelo detalhe e pela palavra-chave invisível", () => {
    expect(filterOptions(modelos, "utility").map((o) => o.value)).toEqual(["promo_pao"]);
    expect(filterOptions(modelos, "wa_notice").map((o) => o.value)).toEqual(["aviso_padrao"]);
  });

  it("busca vazia devolve a lista inteira, sem cópia filtrada por engano", () => {
    expect(filterOptions(modelos, "   ")).toHaveLength(modelos.length);
  });
});

describe("limiar da busca", () => {
  it("o maior vocabulário FIXO da casa não ganha campo; as listas reclamadas ganham", () => {
    expect(SEARCH_THRESHOLD).toBe(12);
    // 10 = ROLE_OPTIONS do Produção e o filtro de desfecho do Histórico.
    expect(isSearchable(10)).toBe(false);
    expect(isSearchable(12)).toBe(false);
    expect(isSearchable(13)).toBe(true);
    // 41 = exemplos do Explorar no B.I.; 56 = insumos que geraram o MaterialPicker.
    expect(isSearchable(41)).toBe(true);
    expect(isSearchable(56)).toBe(true);
  });

  it("o app pode apertar ou afrouxar o limiar", () => {
    expect(isSearchable(5, 3)).toBe(true);
    expect(isSearchable(30, 50)).toBe(false);
  });
});

describe("anúncio de resultados", () => {
  it("fala em português e concorda no singular", () => {
    expect(resultsAnnouncement(0)).toBe("Nenhum resultado");
    expect(resultsAnnouncement(1)).toBe("1 resultado");
    expect(resultsAnnouncement(12)).toBe("12 resultados");
  });
});

describe("navegação por seta", () => {
  it("anda, pula a desabilitada e dá a volta", () => {
    expect(stepIndex(modelos, 0, 1)).toBe(1);
    expect(stepIndex(modelos, 1, 1)).toBe(2);
    // índice 3 está desabilitado: a seta para baixo volta ao começo.
    expect(stepIndex(modelos, 2, 1)).toBe(0);
    expect(stepIndex(modelos, 0, -1)).toBe(2);
  });

  it("começa pelo primeiro quando nada está ativo", () => {
    expect(stepIndex(modelos, -1, 1)).toBe(0);
    expect(stepIndex(modelos, -1, -1)).toBe(2);
  });

  it("não trava quando não há para onde ir", () => {
    expect(stepIndex([], 0, 1)).toBe(-1);
    expect(stepIndex([{ value: "x", label: "X", disabled: true }], -1, 1)).toBe(-1);
  });

  it("aponta as pontas utilizáveis", () => {
    expect(firstEnabledIndex(modelos)).toBe(0);
    expect(lastEnabledIndex(modelos)).toBe(2);
    expect(firstEnabledIndex([])).toBe(-1);
    expect(lastEnabledIndex([])).toBe(-1);
  });
});

describe("escolha atual", () => {
  it("acha por identidade, inclusive quando o valor é booleano", () => {
    const publico: ChoiceOption[] = [
      { value: true, label: "O público da campanha" },
      { value: false, label: "Escolher agora" },
    ];
    expect(selectedOption(publico, false)?.label).toBe("Escolher agora");
    expect(indexOfValue(publico, true)).toBe(0);
  });

  it("devolve nulo quando o valor guardado não existe mais na lista", () => {
    expect(selectedOption(modelos, "apagado")).toBeNull();
    expect(indexOfValue(modelos, "apagado")).toBe(-1);
  });
});
