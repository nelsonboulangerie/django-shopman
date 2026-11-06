import { expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosPreorderCancelDialog from "~/components/PosPreorderCancelDialog.vue";

// Beta test de 05/11/2026 (PDV2-20): "O que já foi pago volta no mesmo meio" numa
// encomenda que ninguém pagou.
async function description(requiresApproval: boolean) {
  const w = await mountSuspended(PosPreorderCancelDialog, {
    props: { open: true, customerName: "Ana", requiresApproval, cancelReasons: [] },
    global: { stubs: { OperatorReasonDialog: { props: ["description"], template: "<p data-desc>{{ description }}</p>" } } },
  });
  const text = w.find("[data-desc]").text();
  w.unmount();
  return text;
}

it("encomenda sem pagamento não fala de devolução", async () => {
  expect(await description(false)).toBe("Nada foi pago nesta encomenda: não há o que devolver.");
});

it("encomenda paga diz como volta o dinheiro e que o gerente autoriza", async () => {
  const text = await description(true);
  expect(text).toContain("O que já foi pago volta no mesmo meio.");
  expect(text).toContain("um gerente precisa autorizar");
});
