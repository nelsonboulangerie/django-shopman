import { mount } from "@vue/test-utils";
import { defineComponent, ref } from "vue";
import { describe, expect, it } from "vitest";
import VerificationCodeInput from "~/components/Ui/VerificationCodeInput.vue";

const Host = defineComponent({
  components: { VerificationCodeInput },
  setup() {
    const code = ref("");
    return { code };
  },
  template: `
    <VerificationCodeInput id="test-code" v-model="code" :length="6" />
    <output>{{ code }}</output>
  `,
});

describe("VerificationCodeInput", () => {
  it("usa seis casas numéricas com semântica de código único", async () => {
    const wrapper = mount(Host);
    const inputs = wrapper.findAll('input[aria-label^="Dígito"]');

    expect(inputs).toHaveLength(6);
    expect(wrapper.text()).toContain("Código de 6 dígitos do autenticador");
    expect(wrapper.get('label[for="test-code"]')).toBeTruthy();
    expect(wrapper.get('[role="group"]').classes()).toContain("justify-center");
    expect(inputs[0]?.attributes("inputmode")).toBe("numeric");
    expect(inputs[0]?.attributes("autocomplete")).toBe("one-time-code");
    expect(inputs[0]?.attributes("aria-label")).toBe("Dígito 1 de 6");

    for (const [index, digit] of Array.from("123456").entries()) {
      await inputs[index]?.setValue(digit);
    }

    expect(wrapper.get("output").text()).toBe("123456");
  });

  it("adapta quantidade e rótulo sem fixar seis dígitos", () => {
    const wrapper = mount(VerificationCodeInput, {
      props: { id: "short-code", length: 4 },
    });

    expect(wrapper.findAll('input[aria-label^="Dígito"]')).toHaveLength(4);
    expect(wrapper.text()).toContain("Código de 4 dígitos do autenticador");
  });
});
