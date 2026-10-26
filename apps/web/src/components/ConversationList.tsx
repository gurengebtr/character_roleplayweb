import { useState } from "react";
import { MessageSquare, Plus, Search } from "lucide-react";
import type { Conversation } from "@/lib/api";
export default function ConversationList({
  conversations,
  active,
  busy,
  select,
  newChat,
}: {
  conversations: Conversation[];
  active: string;
  busy: boolean;
  select: (id: string) => void;
  newChat: () => void;
}) {
  const [query, setQuery] = useState("");
  const visible = conversations.filter((c) =>
    c.title.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <aside className="conversation-panel">
      <header>
        <strong>Messages</strong>
        <span className="badge">{conversations.length}</span>
        <button
          className="icon-button"
          aria-label="New chat"
          title="New chat"
          disabled={busy}
          onClick={newChat}
        >
          <Plus size={18} />
        </button>
      </header>
      <label className="search-field">
        <Search size={16} />
        <input
          placeholder="Search conversations…"
          aria-label="Search conversations"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <div className="conversation-items">
        {visible.map((c) => (
          <button
            key={c.conversation_id}
            aria-label={c.title || "New conversation"}
            className={active === c.conversation_id ? "selected" : ""}
            disabled={busy}
            onClick={() => select(c.conversation_id)}
          >
            <span className="avatar small">
              <MessageSquare size={18} />
            </span>
            <span>
              <strong>{c.title || "New conversation"}</strong>
              <small>
                {c.deleting ? "待刪除 · 請重試清理" : "Continue conversation"}
              </small>
            </span>
          </button>
        ))}
        {!visible.length && (
          <p className="list-empty">
            {query ? "No matching conversations" : "No conversations yet"}
          </p>
        )}
      </div>
    </aside>
  );
}
