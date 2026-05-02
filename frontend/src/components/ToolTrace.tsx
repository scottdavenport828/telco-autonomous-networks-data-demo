import type { ChatMessage } from "../api/client";

type Props = { messages: ChatMessage[] };

export default function ToolTrace({ messages }: Props) {
  const calls = messages.flatMap((m) => m.tool_calls ?? []);

  if (!calls.length) {
    return <div className="text-slate-500 text-sm p-4">Tool calls will appear here.</div>;
  }

  return (
    <div className="p-4 space-y-2">
      {calls.map((c) => (
        <div key={c.id} className="bg-slate-50 border border-slate-200 rounded-md p-3">
          <div className="text-xs uppercase tracking-wide text-slate-500">tool</div>
          <div className="font-mono text-sm">{c.function.name}</div>
          <pre className="text-xs text-slate-600 mt-1 overflow-auto">{c.function.arguments}</pre>
        </div>
      ))}
    </div>
  );
}
