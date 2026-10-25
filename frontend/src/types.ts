import type { Edge, Node } from "@xyflow/react";

export type Step = 1 | 2 | 3 | 4;

export type Change = {
  id: string;
  vendor: string;
  change_type: string;
  severity: "breaking" | "deprecation" | "additive";
  endpoint_from?: string | null;
  endpoint_to?: string | null;
  field_from?: string | null;
  field_to?: string | null;
  migration_hint: string;
  evidence_quote?: string | null;
  evidence_url?: string | null;
  confidence: number;
};

export type CallSite = {
  id: string;
  file: string;
  language: string;
  kind: string;
  vendor?: string | null;
  callee?: string | null;
  url?: string | null;
  function: string;
  start_line: number;
  end_line: number;
  snippet: string;
  payload_keys: string[];
};

export type Impact = { change_id: string; site_id: string; reason: string };

export type GraphNodeData = { label: string; status?: string; path?: string; [key: string]: unknown };
export type Graph = { nodes: Node<GraphNodeData>[]; edges: Edge[]; meta: Record<string, unknown> };
export type AppNode = Node<GraphNodeData>;

export type Gate = {
  id: "G1" | "G2" | "G3" | "G4" | "G5" | "G6";
  name: string;
  status: "pass" | "fail" | "warn" | "pending" | "skipped";
  details: string[];
};

export type Verification = {
  passed: boolean;
  gates: Gate[];
  lines_added: number;
  lines_removed: number;
  ci_run_url?: string | null;
};

export type Diff = { path: string; before: string; after: string };

export type Plan = {
  scenario: string;
  plan: { edits: Array<{ file: string; search: string; replace: string; change_ids: string[]; rationale: string }>; unresolved: string[] };
  diffs: Diff[];
  gates: Verification;
};

export type Simulated = { scenario: string; changes: Change[]; sites: CallSite[]; impacts: Impact[]; graph: Graph };
