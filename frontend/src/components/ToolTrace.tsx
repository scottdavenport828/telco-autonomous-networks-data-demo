import { useState } from "react";
import clsx from "clsx";

/**
 * UI representation of a single tool call across its lifecycle.
 *
 * Built up in `Workbench` from the streaming `tool_start` / `tool_end` events
 * emitted by `tan/agents/stream.py::stream_predict`. While a call is running
 * we know the name + args; once the matching `tool_end` arrives we fill in
 * `result`, `elapsed_ms`, and `status`.
 */
export type ToolCall = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "ok" | "error";
  /** ms since epoch when the start event was received. */
  ts_ms: number;
  elapsed_ms?: number;
  result?: unknown;
  error?: string | null;
};

type Props = { calls: ToolCall[] };

export default function ToolTrace({ calls }: Props) {
  if (!calls.length) {
    return (
      <div className="text-slate-500 text-sm p-4">
        Tool calls will appear here as the agent runs.
      </div>
    );
  }

  // Most recent first — `calls` is appended chronologically by Workbench.
  const ordered = [...calls].reverse();

  return (
    <div className="p-3 space-y-3">
      {ordered.map((call) => (
        <ToolCard key={call.id} call={call} />
      ))}
    </div>
  );
}

function ToolCard({ call }: { call: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const hasResult = call.status !== "running";

  return (
    <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
        <div className="font-mono text-sm text-ink truncate" title={call.name}>
          {call.name}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {call.elapsed_ms !== undefined && (
            <span className="text-xs text-slate-500 tabular-nums">{call.elapsed_ms} ms</span>
          )}
          <StatusPill status={call.status} />
        </div>
      </div>
      <div className="px-3 py-2 space-y-2">
        <Section label="args">
          <pre className="text-xs bg-slate-50 border border-slate-200 rounded px-2 py-1 overflow-auto max-h-40">
            {prettyJson(call.args)}
          </pre>
        </Section>
        {call.error && (
          <Section label="error">
            <pre className="text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded px-2 py-1 overflow-auto whitespace-pre-wrap">
              {call.error}
            </pre>
          </Section>
        )}
        {hasResult && (
          <div>
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="text-xs text-slate-600 hover:text-ink underline-offset-2 hover:underline"
            >
              {expanded ? "Hide result" : "Show result"}
            </button>
            {expanded && (
              <pre className="mt-1 text-xs bg-slate-50 border border-slate-200 rounded px-2 py-1 overflow-auto max-h-72">
                {prettyJson(call.result)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-0.5">{label}</div>
      {children}
    </div>
  );
}

function StatusPill({ status }: { status: ToolCall["status"] }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5",
        status === "running" && "bg-amber-50 text-amber-800 border border-amber-200",
        status === "ok" && "bg-emerald-50 text-emerald-700 border border-emerald-200",
        status === "error" && "bg-rose-50 text-rose-700 border border-rose-200",
      )}
    >
      {status === "running" && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"
          aria-hidden
        />
      )}
      {status}
    </span>
  );
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
