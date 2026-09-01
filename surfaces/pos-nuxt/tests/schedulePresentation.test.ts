import { describe, expect, it } from "vitest";

import {
  dateLabel,
  isScheduled,
  parseLocalDate,
  readinessNote,
  scheduleLabel,
  selectedWindowConflict,
  shortDate,
  windowLabel,
  type ScheduleWindow,
} from "~/presentation/schedule";

const HOJE = "2026-09-08"; // uma terça
const AMANHA = "2026-09-09";
const QUINTA = "2026-09-10";

describe("parseLocalDate — a data do servidor é a data da tela", () => {
  it("lê a ISO no fuso local", () => {
    const date = parseLocalDate(QUINTA)!;
    expect(date.getFullYear()).toBe(2026);
    expect(date.getMonth()).toBe(8); // setembro
    expect(date.getDate()).toBe(10);
  });

  it("NÃO recua um dia a oeste de Greenwich", () => {
    // `new Date("2026-09-10")` lê como UTC e devolveria o dia 9 no Brasil — a
    // quinta viraria quarta na etiqueta do botão.
    expect(parseLocalDate(QUINTA)!.getDate()).toBe(10);
  });

  it("lixo devolve null em vez de uma data inventada", () => {
    expect(parseLocalDate("amanhã")).toBeNull();
    expect(parseLocalDate("")).toBeNull();
    expect(parseLocalDate("2026-9-10")).toBeNull();
  });
});

describe("shortDate", () => {
  it("dd/mm com zero à esquerda", () => {
    expect(shortDate("2026-09-08")).toBe("08/09");
  });

  it("data ilegível não vira texto torto", () => {
    expect(shortDate("nada")).toBe("");
  });
});

describe("dateLabel — como o operador fala com o cliente", () => {
  it("hoje é 'Hoje'", () => {
    expect(dateLabel(HOJE, HOJE)).toBe("Hoje");
  });

  it("amanhã é 'Amanhã'", () => {
    expect(dateLabel(AMANHA, HOJE)).toBe("Amanhã");
  });

  it("de depois de amanhã em diante, o dia da semana vem junto", () => {
    // "que dia da semana?" é a pergunta que o cliente faz de verdade.
    expect(dateLabel(QUINTA, HOJE)).toBe("qui, 10/09");
  });

  it("vazio é vazio", () => {
    expect(dateLabel("", HOJE)).toBe("");
  });
});

describe("scheduleLabel — o botão da barra de contexto", () => {
  it("sem combinado, afirma 'Para hoje'", () => {
    // Afirmação, não campo vazio: a maioria das vendas é para agora, e a barra
    // não pode parecer que falta preencher alguma coisa.
    expect(scheduleLabel("", "", HOJE)).toBe("Para hoje");
    expect(scheduleLabel(HOJE, "", HOJE)).toBe("Para hoje");
  });

  it("hoje com hora marcada carrega a hora", () => {
    expect(scheduleLabel(HOJE, "14:00 às 14:30", HOJE)).toBe("Hoje, 14:00 às 14:30");
  });

  it("outro dia sem hora carrega o dia", () => {
    expect(scheduleLabel(QUINTA, "", HOJE)).toBe("qui, 10/09");
  });

  it("outro dia com hora carrega os dois", () => {
    expect(scheduleLabel(QUINTA, "10:00 às 10:30", HOJE)).toBe("qui, 10/09, 10:00 às 10:30");
  });
});

describe("isScheduled", () => {
  it("hoje (ou em branco) não é agendamento", () => {
    expect(isScheduled("", HOJE)).toBe(false);
    expect(isScheduled(HOJE, HOJE)).toBe(false);
  });

  it("outro dia é", () => {
    expect(isScheduled(QUINTA, HOJE)).toBe(true);
  });
});

const JANELAS: ScheduleWindow[] = [
  { ref: "09:00-09:30", label: "09:00 às 09:30", enabled: false, reason: "Baguette de Tradition sai às 12:00." },
  { ref: "12:00-12:30", label: "12:00 às 12:30", enabled: true, reason: "" },
];

describe("windowLabel", () => {
  it("resolve pelo ref", () => {
    expect(windowLabel(JANELAS, "12:00-12:30")).toBe("12:00 às 12:30");
  });

  it("ref fora da grade não deixa a tela em branco", () => {
    // O expediente do dia pode ter mudado depois; o ref se lê sozinho.
    expect(windowLabel(JANELAS, "23:00-23:30")).toBe("23:00-23:30");
  });

  it("sem ref, sem rótulo", () => {
    expect(windowLabel(JANELAS, "")).toBe("");
  });
});

describe("selectedWindowConflict — a escolha que virou impossível sozinha", () => {
  it("janela compatível não acusa nada", () => {
    expect(selectedWindowConflict(JANELAS, "12:00-12:30")).toBe("");
  });

  it("janela incompatível devolve o motivo do servidor", () => {
    // O operador escolheu 09:00 e SÓ DEPOIS lançou a baguete. Descobrir isso na
    // tela de pagamento é tarde: o cliente já ouviu o horário.
    expect(selectedWindowConflict(JANELAS, "09:00-09:30")).toBe(
      "Baguette de Tradition sai às 12:00.",
    );
  });

  it("janela fora da grade NÃO é tratada como conflito", () => {
    // Mesma calibração do servidor: a grade diz o que se oferece, não o que se
    // aceita. Só a prontidão é promessa quebrada.
    expect(selectedWindowConflict(JANELAS, "23:00-23:30")).toBe("");
  });

  it("sem escolha, nada a acusar", () => {
    expect(selectedWindowConflict(JANELAS, "")).toBe("");
  });
});

describe("readinessNote", () => {
  it("diz o motivo uma vez, em vez de dez vezes nas janelas apagadas", () => {
    expect(readinessNote("Baguette de Tradition", "12:00")).toBe(
      "Baguette de Tradition sai às 12:00. Antes disso não dá para prometer.",
    );
  });

  it("sem gargalo, sem frase", () => {
    expect(readinessNote("", "")).toBe("");
    expect(readinessNote("Croissant", "")).toBe("");
  });
});
