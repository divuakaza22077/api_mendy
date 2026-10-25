import { create } from "zustand";

import type { Change, CallSite, Diff, Graph, Impact, Plan, Step, Verification } from "./types";

type Store = {
  step: Step;
  scenarioId: string;
  changes: Change[];
  sites: CallSite[];
  impacts: Impact[];
  graph: Graph | null;
  plan: Plan | null;
  diffs: Diff[];
  verification: Verification | null;
  pr: Record<string, unknown> | null;
  error: string | null;
  setStep: (step: Step) => void;
  setSimulation: (payload: { scenarioId: string; changes: Change[]; sites: CallSite[]; impacts: Impact[]; graph: Graph }) => void;
  setPlan: (plan: Plan) => void;
  setPr: (pr: Record<string, unknown>) => void;
  setError: (error: string | null) => void;
};

export const useStore = create<Store>((set) => ({
  step: 1,
  scenarioId: "stripe-paymentintents",
  changes: [],
  sites: [],
  impacts: [],
  graph: null,
  plan: null,
  diffs: [],
  verification: null,
  pr: null,
  error: null,
  setStep: (step) => set({ step }),
  setSimulation: (payload) => set({ ...payload, step: 2, error: null }),
  setPlan: (plan) => set({ plan, diffs: plan.diffs, verification: plan.gates, step: 3, error: null }),
  setPr: (pr) => set({ pr, step: 4, error: null }),
  setError: (error) => set({ error }),
}));
