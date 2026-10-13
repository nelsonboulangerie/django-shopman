import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { fixtureActions } from "../support/orderActions";
import type { CourierBlock } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");

describe("confirmação da corrida observada", () => {
  it("mudança de contexto exige conferir novamente antes de solicitar", async () => {
    const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-cancel" };
    const wrapper = mount(Panel, { props: {
      courier: { status: "A", status_label: "Aceita", can_cancel: true, attempts_count: 0 } as CourierBlock,
      busy: false, cancelAction: action,
    }, global: { stubs: { Icon: true } } });
    const button = wrapper.get("button");
    await button.trigger("click");
    expect(button.text()).toContain("Confirmar solicitação?");
    await wrapper.setProps({ cancelAction: { ...action, payload_schema: { ...action.payload_schema, base_revision: "another-ride" } } });
    expect(button.text()).toContain("Solicitar cancelamento");
    await button.trigger("click");
    expect(wrapper.emitted("cancel")).toBeUndefined();
    await button.trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});

it.each([
  ['quote', 'Cotar entrega', 'quoteAction'],
  ['dispatch', 'Chamar entregador', 'dispatchAction'],
] as const)('não emite %s quando a Action da pessoa está bloqueada', async (event, label, property) => {
  const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: `courier-${event}`, enabled: false, reason: 'Sem permissão para esta ação.' };
  const wrapper = mount(Panel, { props: {
    courier: { status: '', can_quote: true, can_dispatch: true, can_cancel: false, attempts_count: 0 } as CourierBlock,
    busy: false, [property]: action,
  }, global: { stubs: { Icon: true } } });
  try {
    const button = wrapper.findAll('button').find(button => button.text() === label)!;
    expect(button.attributes('disabled')).toBeDefined();
    expect(button.attributes('title')).toBe(action.reason);
    await button.trigger('click');
    expect(wrapper.emitted(event)).toBeUndefined();
  } finally { wrapper.unmount(); }
});

it.each([
  ['quote', 'Cotar entrega', 'quoteAction'],
] as const)('uma Action habilitada emite %s uma vez', async (event, label, property) => {
  const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: `courier-${event}`, enabled: true };
  const wrapper = mount(Panel, { props: {
    courier: { status: '', can_quote: true, can_dispatch: true, can_cancel: false, attempts_count: 0 } as CourierBlock,
    busy: false, [property]: action,
  }, global: { stubs: { Icon: true } } });
  try {
    await wrapper.findAll('button').find(button => button.text() === label)!.trigger('click');
    expect(wrapper.emitted(event)).toHaveLength(1);
  } finally { wrapper.unmount(); }
});

describe('Chamar entregador pede um toque de confirmação', () => {
  const question = 'Chamar um entregador da TaOn para o pedido A47? A corrida é cobrada da casa.';
  const dispatchAction = () => ({
    ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-dispatch', enabled: true,
    confirmation: { required: true, description: question },
  });
  const mountPanel = (action = dispatchAction()) => mount(Panel, { props: {
    courier: { status: '', can_quote: false, can_dispatch: true, can_cancel: false, attempts_count: 0 } as CourierBlock,
    busy: false, dispatchAction: action,
  }, global: { stubs: { Icon: true } } });

  it('o primeiro toque só pergunta, em palavras; o segundo chama', async () => {
    const wrapper = mountPanel();
    try {
      const button = wrapper.get('button');
      expect(wrapper.find('[data-testid="courier-dispatch-question"]').exists()).toBe(false);
      await button.trigger('click');
      expect(wrapper.emitted('dispatch')).toBeUndefined();
      expect(button.text()).toBe('Confirmar chamada');
      expect(wrapper.get('[data-testid="courier-dispatch-question"]').text()).toBe(question);
      await button.trigger('click');
      expect(wrapper.emitted('dispatch')).toHaveLength(1);
      expect(button.text()).toBe('Chamar entregador');
    } finally { wrapper.unmount(); }
  });

  it('sair do botão ou o pedido mudar desarma a confirmação', async () => {
    const action = dispatchAction();
    const wrapper = mountPanel(action);
    try {
      const button = wrapper.get('button');
      await button.trigger('click');
      await button.trigger('blur');
      expect(button.text()).toBe('Chamar entregador');
      await button.trigger('click');
      await wrapper.setProps({ dispatchAction: { ...action, payload_schema: { ...action.payload_schema, base_revision: 'outro' } } });
      expect(button.text()).toBe('Chamar entregador');
      await button.trigger('click');
      expect(wrapper.emitted('dispatch')).toBeUndefined();
    } finally { wrapper.unmount(); }
  });
});

describe('Chamar entregador registra a custódia que sai com ele', () => {
  const dispatchAction = () => ({
    ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-dispatch', enabled: true,
    confirmation: { required: true, description: 'Chamar um entregador da TaOn para o pedido A47? A corrida é cobrada da casa.' },
  });
  const machine = (label: string, enabled = true) => ({
    ref: `card_machine:${label}`, label, enabled, order_ref: enabled ? '' : 'WEB-261013-B12',
  }) as never;
  const mountPanel = (custody: CourierBlock['custody'], equipmentOptions: never[] = []) => mount(Panel, { props: {
    courier: { status: '', can_quote: false, can_dispatch: true, can_cancel: false, attempts_count: 0, custody } as CourierBlock,
    busy: false, dispatchAction: dispatchAction(), equipmentOptions,
  }, global: { stubs: { Icon: true } } });
  const confirmButton = (wrapper: ReturnType<typeof mountPanel>) =>
    wrapper.findAll('button').find(b => ['Chamar entregador', 'Confirmar chamada'].includes(b.text()))!;

  it('troco pré-preenchido pelo pedido vai junto na chamada', async () => {
    const wrapper = mountPanel({ change_out_suggested_q: 2600, needs_machine: false, recorded: false });
    try {
      await confirmButton(wrapper).trigger('click');
      const input = wrapper.get('[data-testid="courier-custody-change"] input');
      expect((input.element as HTMLInputElement).value).toBe('26,00');
      await confirmButton(wrapper).trigger('blur');
      expect(confirmButton(wrapper).text()).toBe('Confirmar chamada');
      await confirmButton(wrapper).trigger('click');
      expect(wrapper.emitted('dispatch')).toEqual([[{ change_out: '26,00' }]]);
    } finally { wrapper.unmount(); }
  });

  it('uma maquininha livre: a frase diz qual, e ela vai na chamada', async () => {
    const wrapper = mountPanel({ change_out_suggested_q: 0, needs_machine: true, recorded: false },
      [machine('Azul'), machine('Preta', false)]);
    try {
      await confirmButton(wrapper).trigger('click');
      expect(wrapper.get('[data-testid="courier-custody-machine"]').text()).toBe('Leva a maquininha Azul.');
      await confirmButton(wrapper).trigger('click');
      expect(wrapper.emitted('dispatch')).toEqual([[{ equipment: ['card_machine:Azul'] }]]);
    } finally { wrapper.unmount(); }
  });

  it('nenhuma maquininha livre: não chama, e diz onde elas estão', async () => {
    const wrapper = mountPanel({ change_out_suggested_q: 0, needs_machine: true, recorded: false }, [machine('Azul', false)]);
    try {
      await confirmButton(wrapper).trigger('click');
      expect(wrapper.get('[data-testid="courier-custody-machine"]').text()).toContain('na rua');
      expect(confirmButton(wrapper).attributes('disabled')).toBeDefined();
      expect(wrapper.emitted('dispatch')).toBeUndefined();
    } finally { wrapper.unmount(); }
  });

  it('pedido pago ou custódia já registrada: só a pergunta', async () => {
    for (const custody of [
      { change_out_suggested_q: 0, needs_machine: false, recorded: false },
      { change_out_suggested_q: 0, needs_machine: false, recorded: true },
    ]) {
      const wrapper = mountPanel(custody);
      try {
        await confirmButton(wrapper).trigger('click');
        expect(wrapper.find('[data-testid="courier-custody-change"]').exists()).toBe(false);
        expect(wrapper.find('[data-testid="courier-custody-machine"]').exists()).toBe(false);
        await confirmButton(wrapper).trigger('click');
        expect(wrapper.emitted('dispatch')).toEqual([[{}]]);
      } finally { wrapper.unmount(); }
    }
  });
});
