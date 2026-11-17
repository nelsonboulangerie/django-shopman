export interface OperationChecklistTask {
  id: number;
  ref: string;
  title: string;
  description: string;
  area: string;
  area_label: string;
  status: "pending" | "done" | "skipped" | "blocked";
  status_label: string;
  required: boolean;
  evidence_required: "none" | "text" | "number" | "photo" | "double_check";
  evidence_required_label: string;
  evidence_text: string;
  evidence_number: string | null;
  evidence_data: Record<string, unknown>;
  notes: string;
  requires_supervision: boolean;
  supervised: boolean;
  executed_by: string;
  supervised_by: string;
}

export interface OperationChecklistRun {
  id: number;
  shift_ref: string;
  status: "open" | "completed" | "cancelled";
  status_label: string;
  started_by: string;
  completed_by: string;
  progress_percent: number;
  tasks: OperationChecklistTask[];
}

export interface OperationChecklistTemplate {
  id: number;
  ref: string;
  title: string;
  description: string;
  moment: "opening" | "routine" | "closing";
  moment_label: string;
  runs: OperationChecklistRun[];
}

export interface OperationChecklistBoard {
  business_date: string;
  can_supervise: boolean;
  templates: OperationChecklistTemplate[];
}

export interface OperationChecklistResponse {
  checklists: OperationChecklistBoard;
}
