import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import UiButton from "../../app/components/UiButton.vue";
import UiDateField from "../../app/components/UiDateField.vue";
import UiDateRangeField from "../../app/components/UiDateRangeField.vue";
import UiDateTimeField from "../../app/components/UiDateTimeField.vue";
import UiModal from "../../app/components/UiModal.vue";
import UiTabs from "../../app/components/Ui/Tabs/Tabs.vue";
import UiTabsList from "../../app/components/Ui/Tabs/List.vue";
import UiTabsTrigger from "../../app/components/Ui/Tabs/Trigger.vue";
import UiStepper from "../../app/components/UiStepper.vue";
import UiTimeField from "../../app/components/UiTimeField.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("primitivas estruturais Nuxt UI com identidade Shopman", () => {
  it("mantém o contrato de botão, o alvo canônico e o estado de carregamento", async () => {
    mounted = await mountSuspended(UiButton, {
      attachTo: document.body,
      props: {
        loading: true,
        text: "Salvar campanha",
      },
    });

    const button = document.body.querySelector<HTMLButtonElement>("button")!;
    expect(button).not.toBeNull();
    expect(button.disabled).toBe(true);
    expect(button.className).toContain("h-11");
    expect(button.className).toContain("bg-primary");
    expect(button.className).toContain("disabled:opacity-75");
    expect(button.className).not.toContain("disabled:opacity-50");
    expect(button.textContent).toContain("Salvar campanha");
  });

  it("entrega as variantes ao Nuxt UI sem empilhar o sólido sobre o contorno", async () => {
    mounted = await mountSuspended(UiButton, {
      attachTo: document.body,
      props: { variant: "outline", text: "Cancelar" },
    });

    const button = document.body.querySelector<HTMLButtonElement>("button")!;
    expect(button.className).toContain("text-default");
    expect(button.className).toContain("ring-accented");
    expect(button.className).not.toContain("text-inverted");
    expect(button.className).not.toContain("bg-primary");
  });

  it("usa a anatomia de modal do Nuxt UI sem deixar texto ou tema padrão escapar", async () => {
    const Host = defineComponent({
      setup() {
        const open = ref(true);
        return () =>
          h(
            UiModal,
            {
              open: open.value,
              "onUpdate:open": (value: boolean) => (open.value = value),
              title: "Revisar disparo",
              description: "Confira o público antes de continuar.",
            },
            {
              body: () => h("p", "12 clientes receberão a mensagem."),
            },
          );
      },
    });

    mounted = await mountSuspended(Host, { attachTo: document.body });
    await nextTick();

    const dialog = document.body.querySelector<HTMLElement>("[role='dialog']")!;
    expect(dialog).not.toBeNull();
    expect(dialog.textContent).toContain("Revisar disparo");
    expect(dialog.textContent).toContain("12 clientes receberão a mensagem.");
    expect(dialog.className).toContain("bg-card");
    expect(dialog.className).not.toContain("bg-white");
    expect(document.body.querySelector("[aria-label='Fechar']")).not.toBeNull();
    expect(document.body.textContent).not.toContain("Close");
  });

  it("guia uma sequência com o tema canônico do Nuxt UI e os tokens Shopman", async () => {
    mounted = await mountSuspended(UiStepper, {
      attachTo: document.body,
      props: {
        modelValue: 1,
        label: "Etapas da campanha",
        items: [
          { title: "Objetivo", description: "Dê nome à campanha." },
          { title: "Destinos", description: "Escolha onde publicar." },
          { title: "Conteúdo", description: "Confira o modelo.", disabled: true },
        ],
      },
    });
    await nextTick();

    const root = document.body.querySelector("[data-slot='stepper-shell']")!;
    expect(root.textContent).toContain("2. Destinos. Escolha onde publicar.");
    const headerClass = root.querySelector("[data-slot='header']")?.className ?? "";
    expect(headerClass).toBe("flex");
    expect(headerClass).not.toContain("rounded-lg");
    expect(headerClass).not.toContain("bg-muted");
    expect(root.querySelectorAll("[data-slot='trigger']")).toHaveLength(3);
    const triggerClass = root.querySelector("[data-slot='trigger']")?.className ?? "";
    expect(triggerClass).toContain("size-8");
    expect(triggerClass).toContain("sm:size-14");
    expect(triggerClass).toContain("after:-inset-1.5");
    expect(triggerClass).toContain("sm:after:inset-0");
    expect(triggerClass).toContain("bg-elevated");
    expect(triggerClass).toContain("text-muted");
    expect(triggerClass).toContain("group-data-[state=active]:bg-primary");
    expect(triggerClass).toContain("group-data-[state=active]:text-inverted");
    expect(triggerClass).toContain("focus-visible:outline-3");
    expect(triggerClass).not.toContain("before:");
    expect(root.querySelector("[data-slot='indicator']")?.className).toContain("size-full");
    expect(root.querySelectorAll("[data-slot='indicator']")[0]?.textContent?.trim()).toBe("1");
    expect(root.querySelectorAll("[data-slot='separator']")).toHaveLength(2);
    for (const separator of root.querySelectorAll("[data-slot='separator']")) {
      expect(separator.className).toContain("h-0.5");
      expect(separator.className).toContain("start-[calc(50%+20px)]");
      expect(separator.className).toContain("end-[calc(-50%+20px)]");
      expect(separator.className).toContain("sm:start-[calc(50%+36px)]");
      expect(separator.className).toContain("sm:end-[calc(-50%+36px)]");
      expect(separator.className).not.toContain("left-1/2");
      expect(separator.className).not.toContain("w-full");
      expect(separator.className).not.toContain("hidden");
    }
    expect(root.querySelector("[data-slot='wrapper']")?.className).toContain("sm:block");
    expect(root.querySelector("[data-slot='description']")?.className).toContain("text-lg");
    expect(root.querySelectorAll("[data-slot='title']")[1]?.textContent?.trim()).toBe("2. Destinos");
    expect((root.querySelectorAll("[data-slot='trigger']")[2] as HTMLButtonElement).disabled).toBe(true);
    expect(root.querySelectorAll("[role='status']")[1]?.textContent?.trim()).toBe("Etapa 2 de 3");
  });

  it("entrega roving focus e seleção automática às abas canônicas", async () => {
    const Host = defineComponent({
      setup() {
        const value = ref("pending");
        return () => h(
          UiTabs,
          { modelValue: value.value, "onUpdate:modelValue": (next: string | number) => (value.value = String(next)) },
          () => h(UiTabsList, { "aria-label": "Lotes da Qualidade" }, () => [
            h(UiTabsTrigger, { value: "pending" }, () => "Para confirmar"),
            h(UiTabsTrigger, { value: "reviewed" }, () => "Confirmados"),
          ]),
        );
      },
    });

    mounted = await mountSuspended(Host, { attachTo: document.body });
    const triggers = Array.from(document.body.querySelectorAll<HTMLButtonElement>("[role='tab']"));
    expect(triggers).toHaveLength(2);
    expect(triggers[0]?.getAttribute("aria-selected")).toBe("true");
    triggers[0]?.focus();
    await mounted.findAll("[role='tab']")[0]!.trigger("keydown", { key: "ArrowRight" });
    expect(triggers[1]?.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(triggers[1]);
  });

  it("troca o seletor de data do sistema por segmentos e calendário em português", async () => {
    mounted = await mountSuspended(UiDateField, {
      attachTo: document.body,
      props: { modelValue: "2026-10-05", min: "2026-10-01", max: "2026-10-31", label: "Data da campanha" },
    });

    // Reka mantém um input de 1 px, `aria-hidden`, só para integração com `<form>`;
    // o seletor visível não é o controle do sistema operacional.
    expect(document.body.querySelector("input[type='date']:not([aria-hidden='true'])")).toBeNull();
    expect(document.body.querySelector("[data-segment='day']")?.textContent).toContain("5");
    expect(document.body.querySelector("[data-segment='day']")?.getAttribute("aria-label")).toBe("Dia");
    await mounted.get("[data-slot='date-calendar-trigger']").trigger("click");
    await nextTick();

    const calendar = document.body.querySelector<HTMLElement>("[data-slot='date-calendar-popover']")!;
    expect(calendar).not.toBeNull();
    expect(calendar.textContent?.toLocaleLowerCase("pt-BR")).toContain("outubro");
    const fourteenth = Array.from(calendar.querySelectorAll<HTMLButtonElement>("[data-slot='cellTrigger']"))
      .find((button) => button.textContent?.trim() === "14")!;
    fourteenth.click();
    await nextTick();
    expect(mounted.emitted("update:modelValue")?.at(-1)).toEqual(["2026-10-14"]);
  });

  it("oferece período em um campo único, com calendário de intervalo e limites opcionais", async () => {
    mounted = await mountSuspended(UiDateRangeField, {
      attachTo: document.body,
      props: {
        modelValue: { start: "2026-10-05", end: "2026-10-14" },
        min: "2026-10-01",
        max: "2026-10-31",
        label: "Período de veiculação",
      },
    });

    expect(document.body.querySelector("input[type='date']:not([aria-hidden='true'])")).toBeNull();
    expect(document.body.querySelector("[data-slot='date-range-field']")).not.toBeNull();
    expect(document.body.querySelector("[data-slot='date-range-mobile-trigger']")?.textContent).toContain(
      "05/10/2026 a 14/10/2026",
    );
    expect(document.body.querySelectorAll("[data-segment='day']").length).toBeGreaterThanOrEqual(2);
    expect(document.body.querySelector("[data-segment='day']")?.getAttribute("aria-label")).toBe("Dia");

    await mounted.get("[data-slot='date-range-calendar-trigger']").trigger("click");
    await nextTick();
    const calendar = document.body.querySelector<HTMLElement>("[data-slot='date-range-calendar-popover']")!;
    expect(calendar.textContent?.toLocaleLowerCase("pt-BR")).toContain("outubro");
    calendar.querySelector<HTMLButtonElement>("[data-date-range-clear-end]")?.click();
    await nextTick();
    expect(mounted.emitted("update:modelValue")?.at(-1)).toEqual([{ start: "2026-10-05", end: "" }]);
  });

  it("mantém hora e data+hora nos contratos string das APIs, sem input nativo", async () => {
    mounted = await mountSuspended(UiDateTimeField, {
      attachTo: document.body,
      props: { modelValue: "2026-10-05T17:30", label: "Disparo" },
    });

    expect(document.body.querySelector("input[type='datetime-local']")).toBeNull();
    expect(document.body.querySelector("[data-slot='date-time-field']")).not.toBeNull();
    const date = mounted.getComponent(UiDateField);
    const time = mounted.getComponent(UiTimeField);
    date.vm.$emit("update:modelValue", "2026-10-06");
    await nextTick();
    expect(mounted.emitted("update:modelValue")?.at(-1)).toEqual(["2026-10-06T17:30"]);
    await mounted.setProps({ modelValue: "2026-10-06T17:30" });
    time.vm.$emit("update:modelValue", "18:45");
    await nextTick();
    expect(mounted.emitted("update:modelValue")?.at(-1)).toEqual(["2026-10-06T18:45"]);
  });

  it("preserva o preenchimento parcial de data e hora em qualquer ordem", async () => {
    mounted = await mountSuspended(UiDateTimeField, {
      attachTo: document.body,
      props: { modelValue: "", label: "Disparo" },
    });

    const date = mounted.getComponent(UiDateField);
    const time = mounted.getComponent(UiTimeField);
    time.vm.$emit("update:modelValue", "08:15");
    await nextTick();
    expect(mounted.emitted("update:modelValue")).toBeUndefined();

    date.vm.$emit("update:modelValue", "2026-10-07");
    await nextTick();
    expect(mounted.emitted("update:modelValue")?.at(-1)).toEqual(["2026-10-07T08:15"]);
  });
});
