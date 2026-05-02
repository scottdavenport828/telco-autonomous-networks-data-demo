import { useEffect, useRef, useState } from "react";
import {
  chatStream,
  type ChatMessage,
  type ToolEndEvent,
  type ToolStartEvent,
} from "../api/client";

type Props = {
  agent: "incident-detector" | "rca";
  greeting: string;
  /**
   * Forward tool lifecycle events to a parent (e.g. `Workbench` → `ToolTrace`).
   * `tool_start` / `tool_end` only — `assistant_message` is rendered inline.
   */
  onToolEvent?: (event: ToolStartEvent | ToolEndEvent) => void;
  /** Optional callback invoked whenever the user sends a new message. */
  onUserSend?: (text: string) => void;
};

export default function ChatPanel({ agent, greeting, onToolEvent, onUserSend }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "assistant", content: greeting }]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Reset the chat history when the active agent changes.
  useEffect(() => {
    setMessages([{ role: "assistant", content: greeting }]);
    setDraft("");
    setBusy(false);
    abortRef.current?.abort();
    abortRef.current = null;
  }, [agent, greeting]);

  // Auto-scroll the message list as new content arrives.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  async function send() {
    if (!draft.trim() || busy) return;
    const userMessage: ChatMessage = { role: "user", content: draft };
    const next = [...messages, userMessage];
    setMessages(next);
    onUserSend?.(draft);
    setDraft("");
    setBusy(true);

    // Strip the system-only greeting and any prior tool plumbing before
    // sending; the backend prepends its own system prompt and tool state.
    const wireMessages = next.filter((m) => m.role === "user" || m.role === "assistant");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let receivedAssistant = false;
      for await (const event of chatStream(agent, wireMessages, controller.signal)) {
        if (controller.signal.aborted) break;
        if (event.type === "tool_start" || event.type === "tool_end") {
          onToolEvent?.(event);
          continue;
        }
        if (event.type === "assistant_message") {
          receivedAssistant = true;
          const reply: ChatMessage = { role: "assistant", content: event.content || "(no response)" };
          setMessages((cur) => [...cur, reply]);
        }
        if (event.type === "done") {
          break;
        }
      }
      if (!receivedAssistant) {
        setMessages((cur) => [
          ...cur,
          { role: "assistant", content: "(stream ended without an assistant message)" },
        ]);
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setMessages((cur) => [
        ...cur,
        { role: "assistant", content: `Error: ${(err as Error).message}` },
      ]);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border border-slate-200">
      <div ref={scrollRef} className="flex-1 overflow-auto p-4 space-y-3">
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
        {busy && (
          <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 max-w-[80%] flex items-center gap-2">
            <span
              className="inline-block w-2 h-2 rounded-full bg-slate-400 animate-pulse"
              aria-hidden
            />
            <div className="text-xs text-slate-500">Thinking…</div>
          </div>
        )}
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
