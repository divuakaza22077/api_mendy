import { useEffect, useMemo, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, useEdgesState, useNodesState, type NodeProps } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { Check, CircleAlert, GitPullRequest, Mic, Play, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";

import { health, loadPlan, loadSimulation, offline, ship } from "./api";
import { useStore } from "./store";
import type { AppNode, Step } from "./types";

const steps: Array<{ id: Step; label: string }> = [
  { id: 1, label: "Graph" },
  { id: 2, label: "Blast radius" },
  { id: 3, label: "Verify diff" },
  { id: 4, label: "Approve" },
];

type SpeechEvent = { results: ArrayLike<ArrayLike<{ transcript: string }>> };
type SpeechRecognizer = {
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechConstructor = new () => SpeechRecognizer;

function StatusNode({ data }: NodeProps<AppNode>) {
  const status = data.status ?? "healthy";
  const border = status === "breaking" || status === "removed" ? "border-red-400" : status === "impacted" ? "border-amber-300" : "border-emerald-400";
  return <div className={`min-w-44 rounded-xl border ${border} bg-slate-950/90 px-3 py-2 text-xs shadow-xl`}><div className="font-semibold text-slate-100">{data.label}</div>{data.path && <div className="mt-1 truncate text-slate-500">{data.path}</div>}<div className="mt-1 uppercase tracking-wider text-slate-400">{status}</div></div>;
}

const nodeTypes = { repo: StatusNode, file: StatusNode, function: StatusNode, callsite: StatusNode, endpoint: StatusNode, vendor: StatusNode };

function layoutGraph(graph: NonNullable<ReturnType<typeof useStore.getState>["graph"]>) {
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 30, ranksep: 100 });
  graph.nodes.forEach((node) => g.setNode(node.id, { width: 180, height: 70 }));
  graph.edges.forEach((edge) => g.setEdge(edge.source, edge.target));
  dagre.layout(g);
  return graph.nodes.map((node) => {
    const position = g.node(node.id);
    return { ...node, position: { x: position.x - 90, y: position.y - 35 } };
  });
}

export default function App() {
  const store = useStore();
  const [healthy, setHealthy] = useState(true);
  const [busy, setBusy] = useState(false);
  const [heard, setHeard] = useState("");
  const [listening, setListening] = useState(false);

  useEffect(() => { health().then(() => setHealthy(true)).catch(() => setHealthy(false)); }, []);

  const runSimulation = async () => {
    setBusy(true);
    try { store.setSimulation({ scenarioId: store.scenarioId, ...(await loadSimulation(store.scenarioId)) }); }
    catch (error) { store.setError(error instanceof Error ? error.message : "Simulation failed"); }
    finally { setBusy(false); }
  };

  const runPlan = async () => {
    setBusy(true);
    try { store.setPlan(await loadPlan(store.scenarioId)); }
    catch (error) { store.setError(error instanceof Error ? error.message : "Plan failed"); }
    finally { setBusy(false); }
  };

  const approve = async () => {
    setBusy(true);
    try { store.setPr(await ship(store.scenarioId)); }
    catch (error) { store.setError(error instanceof Error ? error.message : "Ship failed"); }
    finally { setBusy(false); }
  };

  const startVoice = () => {
    const speechWindow = window as Window & {
      SpeechRecognition?: SpeechConstructor;
      webkitSpeechRecognition?: SpeechConstructor;
    };
    const Speech = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    if (!Speech) return;
    const recognition = new Speech();
    setListening(true);
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onresult = (event: SpeechEvent) => {
      const text = Array.from(event.results).map((result) => result[0].transcript).join(" ");
      setHeard(text);
      if (/\b(approve|ship it|go ahead)\b/i.test(text)) { recognition.stop(); void approve(); }
    };
    recognition.onend = () => setListening(false);
    recognition.start();
  };

  return <main className="min-h-screen px-4 py-5 text-slate-100 sm:px-8">
    <header className="mx-auto flex max-w-7xl items-center justify-between gap-4">
      <div><div className="flex items-center gap-3"><div className="rounded-xl bg-red-500/15 p-2 text-red-300"><ShieldCheck size={22} /></div><div><h1 className="text-xl font-black tracking-tight">API-Mend</h1><p className="text-xs text-slate-500">Verified migrations for APIs that move underneath you</p></div></div></div>
      <div className="flex items-center gap-3 text-xs"><span className={`h-2.5 w-2.5 rounded-full ${healthy ? "bg-emerald-400" : "bg-red-400"}`} />{offline ? "offline fixture" : healthy ? "backend warm" : "backend unavailable"}</div>
    </header>
    <section className="mx-auto mt-7 max-w-7xl">
      <div className="mb-6 flex flex-wrap items-center gap-2">{steps.map((item) => <button key={item.id} onClick={() => store.setStep(item.id)} className={`rounded-full px-4 py-2 text-xs font-bold transition ${store.step === item.id ? "bg-red-500 text-white" : "bg-slate-900 text-slate-500 hover:text-slate-200"}`}><span className="mr-2">0{item.id}</span>{item.label}</button>)}</div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs uppercase tracking-[0.26em] text-red-300">Python brain · Rust muscles</p><h2 className="mt-2 max-w-3xl text-3xl font-black tracking-tight sm:text-5xl">Dependabot bumps packages. API-Mend fixes the code that breaks.</h2></div><div className="flow-card rounded-2xl px-4 py-3 text-right text-xs"><div className="text-slate-500">Scenario</div><div className="mt-1 font-bold">Stripe Charges → PaymentIntents</div></div></div>
      {store.error && <div className="mb-5 flex items-center gap-2 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200"><CircleAlert size={16} />{store.error}</div>}
      {store.step === 1 && <GraphScreen graph={store.graph} onSimulate={runSimulation} busy={busy} />}
      {store.step === 2 && <BlastScreen changes={store.changes} sites={store.sites} impacts={store.impacts} onPlan={runPlan} busy={busy} />}
      {store.step === 3 && <DiffScreen diffs={store.diffs} verification={store.verification} onApprove={() => store.setStep(4)} />}
      {store.step === 4 && <ApproveScreen onApprove={approve} busy={busy} heard={heard} listening={listening} onVoice={startVoice} pr={store.pr} />}
    </section>
  </main>;
}

function GraphScreen({ graph, onSimulate, busy }: { graph: ReturnType<typeof useStore.getState>["graph"]; onSimulate: () => void; busy: boolean }) {
  const initialNodes = useMemo(() => graph ? layoutGraph(graph) : [], [graph]);
  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(graph?.edges ?? []);
  useEffect(() => { if (graph) { /* graph is already laid out in the memo */ } }, [graph]);
  return <div className="grid gap-5 lg:grid-cols-[1.5fr_.8fr]">
    <div className="flow-card min-h-[520px] overflow-hidden rounded-3xl"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} fitView colorMode="dark"><Background color="#1c2a40" /><Controls /><MiniMap pannable zoomable /></ReactFlow></div>
    <div className="flow-card rounded-3xl p-6"><div className="flex items-center gap-2 text-red-300"><Sparkles size={17} /><span className="text-xs font-bold uppercase tracking-[0.2em]">Live migration map</span></div><h3 className="mt-4 text-2xl font-black">See the blast radius before changing code.</h3><p className="mt-3 text-sm leading-6 text-slate-400">API-Mend reads GitHub through the REST Git Data API, then uses Rust-backed ast-grep to map vendor calls without cloning or installing target dependencies.</p><button onClick={onSimulate} disabled={busy} className="mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-red-500 px-4 py-3 font-bold transition hover:bg-red-400 disabled:opacity-50"><Play size={17} />{busy ? "Tracing calls…" : "Simulate Stripe drift"}</button></div>
  </div>;
}

function BlastScreen({ changes, sites, impacts, onPlan, busy }: { changes: ReturnType<typeof useStore.getState>["changes"]; sites: ReturnType<typeof useStore.getState>["sites"]; impacts: ReturnType<typeof useStore.getState>["impacts"]; onPlan: () => void; busy: boolean }) {
  return <div className="grid gap-5 lg:grid-cols-[1.1fr_.9fr]">
    <div className="flow-card pulse-red rounded-3xl border-red-500/50 p-6"><div className="flex items-center justify-between"><div className="flex items-center gap-2 text-red-300"><TriangleAlert size={18} /><span className="text-xs font-bold uppercase tracking-[0.2em]">Breaking change detected</span></div><span className="rounded-full bg-red-500/15 px-3 py-1 text-xs text-red-200">{sites.length} sites · {new Set(sites.map((site) => site.file)).size} files</span></div><h3 className="mt-5 text-3xl font-black">Stripe is changing the contract under your code.</h3><div className="mt-6 space-y-3">{changes.map((change) => <div key={change.id} className="rounded-2xl border border-red-500/20 bg-red-950/30 p-4"><div className="flex items-center justify-between gap-3"><span className="font-bold">{change.change_type.replaceAll("_", " ")}</span><span className="text-xs text-red-200">confidence {Math.round(change.confidence * 100)}%</span></div><p className="mt-2 text-sm text-slate-300">{change.migration_hint}</p><p className="mt-2 text-xs text-slate-500">{change.evidence_quote}</p></div>)}</div><button onClick={onPlan} disabled={busy} className="mt-6 w-full rounded-xl bg-amber-300 px-4 py-3 font-black text-slate-950 disabled:opacity-50">{busy ? "Generating surgical patch…" : "Generate verified patch"}</button></div>
    <div className="flow-card rounded-3xl p-6"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Impact edges</p><div className="mt-5 space-y-3">{sites.map((site) => <div key={site.id} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4"><div className="flex items-center justify-between"><span className="font-bold">{site.file}</span><span className="text-xs text-red-300">L{site.start_line}</span></div><div className="mt-2 mono line-clamp-3 text-xs text-slate-400">{site.snippet}</div><div className="mt-3 text-xs text-amber-200">{impacts.filter((impact) => impact.site_id === site.id).map((impact) => impact.reason).join(" · ")}</div></div>)}</div></div>
  </div>;
}

function DiffScreen({ diffs, verification, onApprove }: { diffs: ReturnType<typeof useStore.getState>["diffs"]; verification: ReturnType<typeof useStore.getState>["verification"]; onApprove: () => void }) {
  return <div className="space-y-5"><div className="grid gap-3 sm:grid-cols-6">{verification?.gates.map((gate) => <div key={gate.id} className={`rounded-2xl border p-3 ${gate.status === "pass" ? "border-emerald-500/40 bg-emerald-500/10" : gate.status === "pending" ? "border-slate-700 bg-slate-900" : "border-amber-400/40 bg-amber-400/10"}`}><div className="flex items-center gap-2 text-sm font-black"><Check size={15} />{gate.id}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-400">{gate.status}</div></div>)}</div>{diffs.map((diff) => <div key={diff.path} className="flow-card overflow-hidden rounded-3xl"><div className="flex items-center justify-between border-b border-slate-800 px-5 py-3"><span className="mono text-xs text-slate-300">{diff.path}</span><span className="text-xs text-emerald-300">surgical edit</span></div><div className="grid min-w-0 md:grid-cols-2"><CodePane title="main · before" value={diff.before} tone="red" /><CodePane title="api-mend · after" value={diff.after} tone="green" /></div></div>)}<div className="flex justify-end"><button onClick={onApprove} className="rounded-xl bg-emerald-400 px-5 py-3 font-black text-slate-950">Review and approve →</button></div></div>;
}

function CodePane({ title, value, tone }: { title: string; value: string; tone: "red" | "green" }) { return <div className={`min-w-0 border-slate-800 p-4 ${tone === "red" ? "md:border-r" : ""}`}><div className="mb-3 text-xs font-bold text-slate-500">{title}</div><pre className="mono max-h-80 overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-300">{value}</pre></div>; }

function ApproveScreen({ onApprove, busy, heard, listening, onVoice, pr }: { onApprove: () => void; busy: boolean; heard: string; listening: boolean; onVoice: () => void; pr: Record<string, unknown> | null }) {
  return <div className="mx-auto max-w-3xl"><div className="flow-card rounded-3xl p-8 text-center"><div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300"><GitPullRequest size={34} /></div><h3 className="mt-6 text-3xl font-black">Ready to ship a verified PR.</h3><p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-400">The edit passed exact matching, Rust-backed syntax validation, scope, contract shape, and residue checks. GitHub Actions becomes G6 after the PR exists.</p><div className="mt-8 flex flex-wrap justify-center gap-3"><button onClick={onVoice} className={`flex items-center gap-2 rounded-xl border px-5 py-3 font-bold ${listening ? "border-red-400 bg-red-500/20 text-red-200" : "border-slate-700 bg-slate-900 text-slate-200"}`}><Mic size={17} />{listening ? "Listening…" : "Say approve and ship"}</button><button onClick={onApprove} disabled={busy} className="rounded-xl bg-emerald-400 px-5 py-3 font-black text-slate-950 disabled:opacity-50">{busy ? "Creating preview…" : "Approve & open PR"}</button></div><div className="mt-5 min-h-6 text-sm text-slate-500">{heard || "Voice is optional. The button is always available."}</div>{pr && <div className="mt-7 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-5 text-left"><div className="flex items-center gap-2 font-black text-emerald-200"><Check size={17} />PR preview ready</div><div className="mt-2 text-sm text-slate-300">{pr.offline ? "Offline fixture mode — no network write performed." : "Dry-run ship complete. Enable explicit shipping when ready."}</div></div>}</div></div>;
}
