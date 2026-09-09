import type { OperatorSession } from "../types/operator";

export type OperatorSessionState =
  | "checking"
  | "authenticated"
  | "anonymous"
  | "expired"
  | "forbidden";

export type OperatorSessionRequestStatus =
  | "idle"
  | "pending"
  | "success"
  | "error";

export function operatorSessionState(input: {
  expired: boolean;
  requestStatus: OperatorSessionRequestStatus;
  session: OperatorSession | null;
}): OperatorSessionState {
  if (input.expired) return "expired";
  if (input.requestStatus === "idle" || input.requestStatus === "pending") {
    return "checking";
  }
  if (!input.session?.operator || input.session.locked || input.session.pin_must_change) {
    return "anonymous";
  }
  return input.session.authorized ? "authenticated" : "forbidden";
}
