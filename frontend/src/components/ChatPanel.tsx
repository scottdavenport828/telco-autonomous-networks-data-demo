import { useState } from "react";
import { api, type ChatMessage } from "../api/client";

type Props = {
  agent: "incident-detector" | "rca";
  greeting: string;
};

export default function ChatPanel({ agent, greeting }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "assistant", content: greeting }]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!draft.trim()) return;
    const next: ChatMessage[] = [...messages, { role: "user", content: draft }];
    setMessages(next);
    setDraft("");
    setBusy(true);
    try {
      const response = (await api.chat(agent, next)) as {
        choices?: { message: ChatMessage }[];
        messages?: ChatMessage[];
      };

      const reply =
        response.messages?.[response.messages.length - 1] ??
        response.choices?.[0]?.message ?? { role: "assistant", content: "(no response)" };

      setMessages((cur) => [...cur, reply]);
    } catch (err) {
      setMessages((cur) => [...cur, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border border-slate-200">
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {messages
          .filter((m) => m.role !== "tool")
          .map((m, i) => (
            <div
              key={i}
              className={
                m.role === "user"
                  ? "self-end bg-ink text-white rounded-lg px-3 py-2 max-w-[80%] ml-auto"
                  : "bg-slate-100 rounded-lg px-3 py-2 max-w-[80%]"
              }
            >
              <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">{m.role}</div>
              <div className="text-sm whitespace-pre-wrap">{m.content}</div>
            </div>
          ))}
      </div>
      <div className="border-t border-slate-200 p-3 flex gap-2">
        <input
          className="flex-1 px-3 py-2 border border-slate-300 rounded-md text-sm"
          value={draft}
          disabled={busy}
          placeholder={agent === "incident-detector" ? "Check if there are any new incidents" : "Analyse incident <id>"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button
          className="bg-ink text-white px-4 py-2 rounded-md text-sm disabled:opacity-50"
          onClick={send}
          disabled={busy || !draft.trim()}
        >
          {busy ? "Thinking…" : "Send"}
        </button>
      </div>
    </div>
  );
}
