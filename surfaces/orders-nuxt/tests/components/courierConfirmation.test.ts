import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { fixtureActions } from "../support/orderActions";
import type { CourierBlock } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useNowTick", () => ref(0));
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");

describe("confirmação da corrida observada", () => {
  it("mudança de contexto exige conferir novamente antes de solicitar", async () => {
    const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-cancel", label: "Cancelar corrida" };
    const wrapper = mount(Panel, { props: {
      courier: { status: "D", status_label: "Procurando entregador", can_cancel: true, attempts_count: 0 } as CourierBlock,
      busy: false, cancelAction: action,
    }, global: { stubs: { Icon: true } } });
    // O primeiro toque só arma a confirmação.
    await wrapper.get("[data-courier-cancel]").trigger("click");
    expect(wrapper.find("[data-courier-cancel-confirm]").exists()).toBe(true);
    // A corrida mudou com a confirmação aberta: desarma, e o toque de antes não vale.
    await wrapper.setProps({ cancelAction: { ...action, payload_schema: { ...action.payload_schema, base_revision: "another-ride" } } });
    expect(wrapper.find("[data-courier-cancel-confirm]").exists()).toBe(false);
    expect(wrapper.get("[data-courier-cancel]").text()).toContain("Cancelar corrida");
    await wrapper.get("[data-courier-cancel]").trigger("click");
    expect(wrapper.emitted("cancel")).toBeUndefined();
    await wrapper.get("[data-courier-cancel-go]").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});

it.each([
  ['quote', 'Cotar entrega', 'quoteAction'],
  ['call', 'Chamar entregador', 'dispatchAction'],
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

// #2876: o painel não confirma mais em linha. O toque abre o MESMO sheet das Entregas
// (`CourierCallSheet`), onde a custódia (troco e maquininha), quem vai junto e a cotação
// se conferem; a confirmação e a custódia são cobradas em `courierCallSheet.test.ts` e
// em `tests/composables/useCourierCall.test.ts`.
describe('Chamar entregador abre o sheet de chamar, nunca chama num toque', () => {
  const dispatchAction = () => ({
    ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-dispatch', enabled: true,
    confirmation: { required: true, description: 'Chamar um entregador da TaOn para o pedido A47? A corrida é cobrada da casa.' },
  });
  const mountPanel = (props: Record<string, unknown> = {}) => mount(Panel, { props: {
    courier: { status: '', can_quote: false, can_dispatch: true, can_cancel: false, attempts_count: 0,
      custody: { change_out_suggested_q: 2600, needs_machine: true, recorded: false } } as CourierBlock,
    busy: false, dispatchAction: dispatchAction(), ...props,
  }, global: { stubs: { Icon: true } } });

  it('o toque pede o sheet uma vez; nada é chamado nem perguntado em linha', async () => {
    const wrapper = mountPanel();
    try {
      const button = wrapper.get('[data-courier-call]');
      expect(button.text()).toBe('Chamar entregador');
      await button.trigger('click');
      expect(wrapper.emitted('call')).toHaveLength(1);
      expect(wrapper.emitted('dispatch')).toBeUndefined();
      // A confirmação em linha (pergunta, troco, maquininha, "Vai junto?") saiu do painel.
      expect(wrapper.find('[data-testid="courier-dispatch-confirm"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="courier-custody-change"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="courier-custody-machine"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="courier-ride-offer"]').exists()).toBe(false);
      expect(button.text()).toBe('Chamar entregador');
    } finally { wrapper.unmount(); }
  });

  it('enquanto o sheet abre, o botão espera e um segundo toque não pede de novo', async () => {
    const wrapper = mountPanel({ calling: true });
    try {
      const button = wrapper.get('[data-courier-call]');
      expect(button.attributes('disabled')).toBeDefined();
      await button.trigger('click');
      expect(wrapper.emitted('call')).toBeUndefined();
    } finally { wrapper.unmount(); }
  });

  it('com o painel ocupado (outra ação gravando), não pede', async () => {
    const wrapper = mountPanel({ busy: true });
    try {
      await wrapper.get('[data-courier-call]').trigger('click');
      expect(wrapper.emitted('call')).toBeUndefined();
    } finally { wrapper.unmount(); }
  });
});

describe('chamada sem resposta da TaOn', () => {
  const courier = { status: '', status_label: 'Sem resposta da TaOn', can_quote: false, can_dispatch: false,
    can_dispatch_again: true, can_cancel: false, attempts_count: 0,
    error: { message: 'A TaOn não respondeu à última chamada. Veja na central se a corrida abriu.', at: '' } } as CourierBlock;

  it('o aviso traz o gesto curto "Chamar de novo", que emite uma vez', async () => {
    const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-dispatch-again', enabled: true };
    const wrapper = mount(Panel, { props: { courier, busy: false, dispatchAgainAction: action },
      global: { stubs: { Icon: true } } });
    try {
      const alert = wrapper.get('[data-courier-no-answer]');
      expect(alert.text()).toContain('A TaOn não respondeu à última chamada.');
      expect(alert.text()).not.toContain('conferi');
      const button = alert.findAll('button').find(item => item.text() === 'Chamar de novo')!;
      await button.trigger('click');
      expect(wrapper.emitted('dispatchAgain')).toHaveLength(1);
      expect(wrapper.findAll('button').some(item => item.text() === 'Chamar entregador')).toBe(false);
    } finally { wrapper.unmount(); }
  });

  it('é cautela, não erro: aviso e botão no tom de atenção, e o selo do cabeçalho sai', async () => {
    const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-dispatch-again', enabled: true };
    const wrapper = mount(Panel, { props: { courier, busy: false, dispatchAgainAction: action },
      global: { stubs: { Icon: true } } });
    try {
      const alert = wrapper.get('[data-courier-no-answer]');
      expect(alert.attributes('color')).toBe('warning');
      expect(alert.attributes('role')).toBe('status');
      const button = alert.findAll('button').find(item => item.text() === 'Chamar de novo')!;
      expect(button.attributes('color')).toBe('warning');
      // O selo repetia o assunto do aviso logo abaixo: com o aviso na tela, ele sai.
      expect(wrapper.text()).not.toContain('Sem resposta da TaOn');
    } finally { wrapper.unmount(); }
  });

  it('bloqueado pela Action, não emite', async () => {
    const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-dispatch-again', enabled: false, reason: 'Sem permissão para esta ação.' };
    const wrapper = mount(Panel, { props: { courier, busy: false, dispatchAgainAction: action },
      global: { stubs: { Icon: true } } });
    try {
      const button = wrapper.findAll('button').find(item => item.text() === 'Chamar de novo')!;
      expect(button.attributes('disabled')).toBeDefined();
      await button.trigger('click');
      expect(wrapper.emitted('dispatchAgain')).toBeUndefined();
    } finally { wrapper.unmount(); }
  });
});

describe('Cotar entrega mostra o resultado em destaque (dono, 13/10/2026)', () => {
  const quoteAction = () => ({ ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-quote', enabled: true });
  const dispatchAction = () => ({ ...fixtureActions({ can_confirm: true })[0]!, ref: 'courier-dispatch', enabled: true });
  const courier = (extra: Partial<CourierBlock> = {}) => ({
    status: '', can_quote: true, can_dispatch: true, can_cancel: false, attempts_count: 0, estimate_display: '', ...extra,
  }) as CourierBlock;
  const mountPanel = (props: Record<string, unknown>) => mount(Panel, { props: {
    busy: false, quoteAction: quoteAction(), dispatchAction: dispatchAction(), ...props,
  }, global: { stubs: { Icon: true } } });

  it('valor, tempo e distância numa linha forte, com Chamar entregador logo abaixo como ação primária', () => {
    const wrapper = mountPanel({ courier: courier({ estimate_display: 'R$ 7,00 · 3 min · 1,2 km' }) });
    try {
      expect(wrapper.get('[data-courier-quote-value]').text()).toBe('R$ 7,00 · 3 min · 1,2 km');
      const labels = wrapper.findAll('button').map(button => button.text());
      expect(labels.indexOf('Chamar entregador')).toBeLessThan(labels.indexOf('Cotar de novo'));
      expect(labels).not.toContain('Cotar entrega');
    } finally { wrapper.unmount(); }
  });

  it('enquanto cota, diz que está cotando e o botão espera', () => {
    const wrapper = mountPanel({ courier: courier(), quoting: true });
    try {
      expect(wrapper.get('[data-courier-quote-value]').text()).toBe('Cotando a entrega…');
      expect(wrapper.get('[data-courier-quote-button]').attributes('disabled')).toBeDefined();
    } finally { wrapper.unmount(); }
  });

  it('a falha vira aviso com Cotar de novo, e o aviso se dispensa', async () => {
    const wrapper = mountPanel({ courier: courier(), quoteError: 'Endereço sem coordenadas.' });
    try {
      const alert = wrapper.get('[data-courier-quote-error]');
      expect(alert.text()).toContain('Endereço sem coordenadas.');
      await wrapper.get('[data-courier-quote-retry]').trigger('click');
      expect(wrapper.emitted('quote')).toHaveLength(1);
    } finally { wrapper.unmount(); }
  });

  it('sem cotação, nada de bloco vazio', () => {
    const wrapper = mountPanel({ courier: courier() });
    try {
      expect(wrapper.find('[data-courier-quote]').exists()).toBe(false);
    } finally { wrapper.unmount(); }
  });
});
