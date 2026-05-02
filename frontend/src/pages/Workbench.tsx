import { useCallback, useState } from "react";
import ChatPanel from "../components/ChatPanel";
import ToolTrace, { type ToolCall } from "../components/ToolTrace";
import type { ToolEndEvent, ToolStartEvent } from "../api/client";

type Agent = "incident-detector" | "rca";

const GREETING: Record<Agent, string> = {
  "incident-detector":
    "I scan the materialised KPI view for cells that violate ERAB success rate or retainability thresholds. Try: \"Check for new incidents\".",
  rca: "I orchestrate the full root-cause-analysis workflow. Try: \"Analyse incident <incident_id>\".",
};

export default function Workbench() {
  const [agent, setAgent] = useState<Agent>("incident-detector");
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);

  // `tool_start` appends a card; `tool_end` patches the matching card with
  // status, elapsed_ms, and the result payload. Calls are kept in arrival order.
  const handleToolEvent = useCallback((event: ToolStartEvent | ToolEndEvent) => {
    setToolCalls((prev) => {
      if (event.type === "tool_start") {
        if (prev.some((c) => c.id === event.id)) return prev; // idempotent
        const next: ToolCall = {
          id: event.id,
          name: event.name,
          args: event.args,
          status: "running",
          ts_ms: event.ts_ms,
        };
        return [...prev, next];
      }
      // tool_end
      return prev.map((c) =>
        c.id === event.id
          ? {
              ...c,
              status: event.status,
              elapsed_ms: event.elapsed_ms,
              result: event.result,
              error: event.error ?? null,
            }
          : c,
      );
    });
  }, []);

  // New user message → keep prior calls visible but prepare for fresh ones.
  // We don't clear history because the trace pane is meant to read like a log.
  const handleUserSend = useCallback(() => {
    // No-op for now; placeholder so we can wire in a "clear on new turn"
    // toggle later without changing the ChatPanel API.
  }, []);

  // Switching agents is a hard reset — different tool surface, different log.
  const switchAgent = (a: Agent) => {
    setAgent(a);
    setToolCalls([]);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Workbench</h1>
        <div className="flex gap-2 text-sm">
          {(["incident-detector", "rca"] as const).map((a) => (
            <button
              key={a}
              onClick={() => switchAgent(a)}
              className={
                agent === a
                  ? "bg-ink text-white px-3 py-1.5 rounded-md"
                  : "bg-slate-200 text-slate-700 px-3 py-1.5 rounded-md"
              }
            >
              {a}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-200px)]">
        <div className="lg:col-span-2">
          <ChatPanel
            agent={agent}
            greeting={GREETING[agent]}
            onToolEvent={handleToolEvent}
            onUserSend={handleUserSend}
          />
        </div>
        <div className="bg-white rounded-lg border border-slate-200 overflow-auto">
          <div className="flex items-center justify-between p-3 border-b border-slate-200">
            <h3 className="text-sm font-semibold">Tool trace</h3>
            {toolCalls.length > 0 && (
              <button
                type="button"
                onClick={() => setToolCalls([])}
                className="text-xs text-slate-500 hover:text-ink"
              >
                Clear
              </button>
            )}
          </div>
          <ToolTrace calls={toolCalls} />
        </div>
      </div>
    </div>
  );
}
