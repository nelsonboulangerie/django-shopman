import { httpErrorMessage } from "../../../operator-kit/app/utils/httpError";

import type {
  SupportCapabilities,
  SupportDecisionKind,
  SupportListResponse,
  SupportPriority,
  SupportTicket,
  SupportTicketDetail,
  SupportType,
} from "~/types/support";

const EMPTY_CAPABILITIES: SupportCapabilities = {
  create: false,
  triage: false,
  view_all: false,
  approve: false,
  link_dev: false,
  audit: false,
};

const BASE = "/api/v1/backstage/support";

export interface NewTicketPayload {
  description: string;
  type: SupportType;
  context?: Record<string, unknown>;
}

export interface TriagePayload {
  type?: SupportType;
  priority?: SupportPriority;
  assignee_id?: number | null;
}

/**
 * Estado do Suporte na Central. O chamado é o registro; a solicitação é o
 * chamado que pede mudança; o compromisso (DEV-) é o trabalho. Nada aqui
 * aprova: a aprovação é do dono, no servidor.
 */
export function useSupport() {
  const apiPath = useApiPath();

  const tickets = ref<SupportTicket[]>([]);
  const ticket = ref<SupportTicketDetail | null>(null);
  const capabilities = ref<SupportCapabilities>({ ...EMPTY_CAPABILITIES });
  const pending = ref(false);
  const error = ref("");
  const loaded = ref(false);

  async function request<T>(path: string, options: Record<string, unknown> = {}): Promise<T> {
    return (await $fetch(apiPath(path), { credentials: "include", ...options })) as T;
  }

  function updateList(updated: SupportTicket): void {
    const index = tickets.value.findIndex((item) => item.ref === updated.ref);
    if (index >= 0) tickets.value[index] = updated;
    else tickets.value.unshift(updated);
  }

  async function refreshList(): Promise<void> {
    const list = await request<SupportListResponse>(`${BASE}/tickets/`);
    tickets.value = list.tickets;
  }

  async function load(): Promise<void> {
    pending.value = true;
    error.value = "";
    try {
      const [caps, list] = await Promise.all([
        request<SupportCapabilities>(`${BASE}/capabilities/`),
        request<SupportListResponse>(`${BASE}/tickets/`),
      ]);
      capabilities.value = caps;
      tickets.value = list.tickets;
      loaded.value = true;
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível carregar o Suporte.");
    } finally {
      pending.value = false;
    }
  }

  async function select(ref: string): Promise<void> {
    pending.value = true;
    error.value = "";
    try {
      ticket.value = await request<SupportTicketDetail>(`${BASE}/tickets/${ref}/`);
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível abrir o chamado.");
    } finally {
      pending.value = false;
    }
  }

  async function create(payload: NewTicketPayload): Promise<SupportTicketDetail | null> {
    pending.value = true;
    error.value = "";
    try {
      const created = await request<SupportTicketDetail>(`${BASE}/tickets/`, {
        method: "POST",
        body: payload,
      });
      ticket.value = created;
      updateList(created);
      return created;
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível abrir o chamado.");
      return null;
    } finally {
      pending.value = false;
    }
  }

  async function reply(ref: string, body: string, internalNote = false): Promise<boolean> {
    pending.value = true;
    error.value = "";
    try {
      await request(`${BASE}/tickets/${ref}/messages/`, {
        method: "POST",
        body: { body, internal_note: internalNote },
      });
      await select(ref);
      await refreshList();
      return true;
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível enviar a mensagem.");
      return false;
    } finally {
      pending.value = false;
    }
  }

  async function triage(ref: string, payload: TriagePayload): Promise<boolean> {
    pending.value = true;
    error.value = "";
    try {
      const updated = await request<SupportTicketDetail>(`${BASE}/tickets/${ref}/triage/`, {
        method: "POST",
        body: payload,
      });
      ticket.value = updated;
      updateList(updated);
      return true;
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível triar o chamado.");
      return false;
    } finally {
      pending.value = false;
    }
  }

  async function decide(
    ref: string,
    decision: SupportDecisionKind,
    reason = "",
    reviewAt?: string,
  ): Promise<boolean> {
    pending.value = true;
    error.value = "";
    try {
      const updated = await request<SupportTicketDetail>(`${BASE}/tickets/${ref}/decision/`, {
        method: "POST",
        body: { decision, reason, review_at: reviewAt },
      });
      ticket.value = updated;
      updateList(updated);
      return true;
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível registrar a decisão.");
      return false;
    } finally {
      pending.value = false;
    }
  }

  async function linkDev(ref: string, devRef: string): Promise<boolean> {
    pending.value = true;
    error.value = "";
    try {
      const updated = await request<SupportTicketDetail>(`${BASE}/tickets/${ref}/link-dev/`, {
        method: "POST",
        body: { dev_ref: devRef },
      });
      ticket.value = updated;
      updateList(updated);
      return true;
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível ligar o compromisso.");
      return false;
    } finally {
      pending.value = false;
    }
  }

  function clear(): void {
    ticket.value = null;
    error.value = "";
  }

  return {
    tickets,
    ticket,
    capabilities,
    pending,
    error,
    loaded,
    load,
    select,
    create,
    reply,
    triage,
    decide,
    linkDev,
    clear,
  };
}
