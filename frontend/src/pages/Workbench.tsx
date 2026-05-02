import { useState } from "react";
import ChatPanel from "../components/ChatPanel";
import ToolTrace from "../components/ToolTrace";
import type { ChatMessage } from "../api/client";

type Agent = "incident-detector" | "rca";

const GREETING: Record<Agent, string> = {
  "incident-detector":
    "I scan the materialised KPI view for cells that violate ERAB success rate or retainability thresholds. Try: \"Check for new incidents\".",
  rca: "I orchestrate the full root-cause-analysis workflow. Try: \"Analyse incident <incident_id>\".",
};

export default function Workbench() {
  const [agent, setAgent] = useState<Agent>("incident-detector");
  const [trace] = useState<ChatMessage[]>([]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Workbench</h1>
        <div className="flex gap-2 text-sm">
          {(["incident-detector", "rca"] as const).map((a) => (
            <button
              key={a}
              onClick={() => setAgent(a)}
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
          <ChatPanel agent={agent} greeting={GREETING[agent]} />
        </div>
        <div className="bg-white rounded-lg border border-slate-200 overflow-auto">
          <h3 className="text-sm font-semibold p-3 border-b border-slate-200">Tool trace</h3>
          <ToolTrace messages={trace} />
        </div>
      </div>
    </div>
  );
}
