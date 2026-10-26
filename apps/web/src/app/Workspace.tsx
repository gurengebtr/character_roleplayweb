"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  empty,
  type Character,
  type Conversation,
  type Message,
  type Preferences,
  type Memory,
} from "@/lib/api";
import CharacterEditor from "@/components/CharacterEditor";
import SettingsPanel from "@/components/SettingsPanel";
import WorkspaceShell from "@/components/WorkspaceShell";
import HomePage from "@/components/HomePage";
import ConversationList from "@/components/ConversationList";
import { Search, LayoutGrid, List, RefreshCw, Sparkles } from "lucide-react";

export default function Workspace({
  username,
  logout,
}: {
  username: string;
  logout: () => Promise<void>;
}) {
  const [tab, setTab] = useState("home");
  const [characterQuery, setCharacterQuery] = useState("");
  const [characterView, setCharacterView] = useState<"grid" | "list">("grid");
  const [characters, setCharacters] = useState<Character[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [draft, setDraft] = useState<Character | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [models, setModels] = useState<
    { slug: string; display_name?: string }[]
  >([]);
  const [input, setInput] = useState("");
  const [note, setNote] = useState("");
  const [memory, setMemory] = useState<Memory | null>(null);
  const [showMemory, setShowMemory] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [health, setHealth] = useState<{
    mongo: boolean;
    rag: { ready: boolean; memory_configured?: boolean };
  } | null>(null);
  const messageList = useRef<HTMLDivElement>(null);
  const retry = useRef<{ text: string; id: string } | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const conv = conversations.find((c) => c.conversation_id === active);
  const character = characters.find(
    (c) => c.character_id === conv?.character_id,
  );
  const refresh = useCallback(async () => {
    const [cs, chats, settings] = await Promise.all([
      api<Character[]>("/characters"),
      api<Conversation[]>("/conversations"),
      api<Preferences>("/settings"),
    ]);
    setCharacters(cs);
    setConversations(chats);
    setPrefs(settings);
  }, []);
  const action = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗");
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
    void api<typeof health>("/health")
      .then(setHealth)
      .catch(() => {});
  }, [refresh]);
  const loadChat = useCallback(async (id: string) => {
    const [page, mem] = await Promise.all([
      api<{ items: Message[]; next_cursor: string | null }>(
        `/conversations/${id}/messages`,
      ),
      api<Memory>(`/conversations/${id}/memory`),
    ]);
    if (activeRef.current !== id) return;
    setMessages(page.items);
    setCursor(page.next_cursor);
    setMemory(mem);
  }, []);
  useEffect(() => {
    setMessages([]);
    setMemory(null);
    setInput("");
    retry.current = null;
    if (active) void loadChat(active).catch((e) => setError(e.message));
  }, [active, loadChat]);
  useEffect(() => {
    setNote(conv?.memory_note || "");
  }, [conv?.conversation_id, conv?.memory_note]);
  useEffect(() => {
    if (
      !active ||
      !memory?.jobs.some((j) => ["pending", "failed"].includes(j.status))
    )
      return;
    const timer = setTimeout(() => {
      void api<Memory>(`/conversations/${active}/memory`)
        .then((m) => {
          if (activeRef.current === active) setMemory(m);
        })
        .catch(() => {});
    }, 3500);
    return () => clearTimeout(timer);
  }, [active, memory]);
  useEffect(() => {
    const list = messageList.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.at(-1)?.message_id]);
  const startChat = (c: Character) =>
    action(async () => {
      const created = await api<Conversation>("/conversations", "POST", {
        character_id: c.character_id,
        title: c.name,
      });
      await refresh();
      setActive(created.conversation_id);
      setTab("chat");
    });
  const saveCharacter = () =>
    action(async () => {
      if (!draft) return;
      const { character_id, published_hash: _hash, ...body } = draft;
      const allowed = {
        name: body.name,
        system_prompt: body.system_prompt,
        opening_message: body.opening_message,
        background: body.background,
        phases: body.phases,
        memory_enabled: body.memory_enabled,
        provider: body.provider,
        model: body.model,
      };
      await api(
        character_id ? `/characters/${character_id}` : "/characters",
        character_id ? "PUT" : "POST",
        allowed,
      );
      await refresh();
      setDraft(null);
      setNotice("角色已儲存。背景修改後，請按「發佈背景」使 RAG 生效。");
    });
  const send = () =>
    action(async () => {
      const text = input.trim();
      if (!text || !active) return;
      if (retry.current?.text !== text)
        retry.current = { text, id: crypto.randomUUID() };
      const id = active;
      await api(`/conversations/${id}/messages`, "POST", {
        content: text,
        request_id: retry.current!.id,
      });
      if (activeRef.current === id) {
        setInput("");
        retry.current = null;
        await loadChat(id);
      }
      await refresh();
    });
  const updateState = (phase: string | null) =>
    action(async () => {
      if (!conv) return;
      await api(`/conversations/${active}`, "PATCH", {
        phase_id: phase,
        memory_note: note,
        revision: conv.revision,
      });
      await refresh();
      setNotice("對話狀態已更新。");
    });

  return (
    <WorkspaceShell
      tab={tab}
      navigate={setTab}
      username={username}
      logout={logout}
      characters={characters}
      conversations={conversations}
      selectConversation={setActive}
      editCharacter={setDraft}
    >
      {error && (
        <div role="alert" className="banner error">
          {error}
          <button onClick={() => setError("")}>×</button>
        </div>
      )}
      {notice && (
        <div role="status" className="banner">
          {notice}
        </div>
      )}
      {tab === "home" && <HomePage navigate={setTab} />}
      {tab === "chat" && (
        <div className="chat-layout">
          <ConversationList
            conversations={conversations}
            active={active}
            busy={busy}
            select={setActive}
            newChat={() => setActive("")}
          />
          {!conv ? (
            <section className="welcome">
              <div className="empty-icon">
                <Sparkles size={28} />
              </div>
              <h1>Start a conversation</h1>
              <p>選一個角色開始對話。每段新對話都有自己的記憶與關係階段。</p>
              <div className="cards">
                {characters.map((c) => (
                  <article className="card" key={c.character_id}>
                    <div className="avatar">{c.name.slice(0, 1)}</div>
                    <h2>{c.name}</h2>
                    <p>{c.opening_message || c.system_prompt.slice(0, 90)}</p>
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => void startChat(c)}
                    >
                      開始新對話 ↗
                    </button>
                  </article>
                ))}
                <button
                  className="card add-card"
                  onClick={() => {
                    setDraft(empty());
                    setTab("characters");
                  }}
                >
                  ＋ 建立你的角色
                </button>
              </div>
            </section>
          ) : (
            <section className="chat-view">
              <div className="chat-heading">
                <div className="avatar small">
                  {character?.name.slice(0, 1)}
                </div>
                <div>
                  <h2>{character?.name}</h2>
                  <small>
                    {character?.provider === "chatgpt"
                      ? "ChatGPT"
                      : "自訂 endpoint"}{" "}
                    ·{" "}
                    {character?.model ||
                      (character?.provider === "endpoint"
                        ? prefs?.endpoint.model
                        : "尚未選擇模型")}
                  </small>
                </div>
                <div className="spacer" />
                <button onClick={() => setShowMemory(!showMemory)}>
                  記憶與階段
                </button>
                <button
                  disabled={busy}
                  className="quiet"
                  onClick={() => {
                    if (confirm("刪除此對話、訊息及其記憶？"))
                      void action(async () => {
                        await api(`/conversations/${active}`, "DELETE");
                        setActive("");
                        await refresh();
                      });
                  }}
                >
                  刪除
                </button>
              </div>
              {showMemory && (
                <div className="memory-panel">
                  <label>
                    關係階段
                    <select
                      value={conv.state.phase_id || ""}
                      disabled={busy}
                      onChange={(e) => void updateState(e.target.value || null)}
                    >
                      <option value="">預設</option>
                      {character?.phases.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    這段故事的固定筆記
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={4000}
                    />
                  </label>
                  <button
                    disabled={busy}
                    onClick={() => void updateState(conv.state.phase_id)}
                  >
                    儲存筆記
                  </button>
                  <h3>記憶</h3>
                  {memory?.unavailable && <p>記憶服務暫時無法連線。</p>}
                  {!health?.rag.memory_configured && (
                    <p>記憶服務尚未就緒；固定筆記仍可使用。</p>
                  )}
                  {memory?.facts.map((f, i) => (
                    <p key={i}>• {f.text}</p>
                  ))}
                  {memory?.has_more && (
                    <small>顯示前 100 項；檢索仍涵蓋所有記憶。</small>
                  )}
                  <small>
                    {memory?.jobs
                      .slice(0, 5)
                      .map((j) => j.status)
                      .join(" · ") || "尚無記憶工作"}
                  </small>
                  {memory?.jobs.some((j) =>
                    ["failed", "dead"].includes(j.status),
                  ) && (
                    <button
                      onClick={() =>
                        void action(async () => {
                          await api(
                            `/conversations/${active}/memory/retry`,
                            "POST",
                          );
                          await loadChat(active);
                        })
                      }
                    >
                      重試記憶工作
                    </button>
                  )}
                </div>
              )}
              <div className="messages" aria-live="polite" ref={messageList}>
                {cursor && (
                  <button
                    onClick={() =>
                      void action(async () => {
                        const page = await api<{
                          items: Message[];
                          next_cursor: string | null;
                        }>(
                          `/conversations/${active}/messages?before=${cursor}`,
                        );
                        setMessages((m) => [...page.items, ...m]);
                        setCursor(page.next_cursor);
                      })
                    }
                  >
                    載入較早訊息
                  </button>
                )}
                {messages.map((m) => (
                  <article key={m.message_id} className={"message " + m.role}>
                    <small>{m.role === "user" ? "YOU" : character?.name}</small>
                    <div>{m.content}</div>
                    {m.retrieval_status === "unavailable" && (
                      <small>此回覆未能取得 RAG 背景／記憶</small>
                    )}
                  </article>
                ))}
                {busy && <p className="thinking">正在處理…</p>}
              </div>
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send();
                }}
              >
                <textarea
                  aria-label="訊息"
                  placeholder={`跟 ${character?.name || "角色"} 說點甚麼…`}
                  value={input}
                  disabled={busy || conv.deleting}
                  onChange={(e) => setInput(e.target.value)}
                  maxLength={12000}
                />
                <button
                  className="primary"
                  disabled={busy || !input.trim() || conv.deleting}
                >
                  傳送 ↑
                </button>
                <small>模型完成回覆後才保存本輪訊息；失敗可直接重試。</small>
              </form>
            </section>
          )}
        </div>
      )}
      {tab === "characters" && (
        <section className="page">
          <div className="page-title">
            <div>
              <div className="eyebrow">WORKSPACE</div>
              <h1>Characters</h1>
              <p>管理角色、背景與不同關係階段。</p>
            </div>
            <button className="primary" onClick={() => setDraft(empty())}>
              ＋ 新角色
            </button>
          </div>
          {draft ? (
            <CharacterEditor
              {...{
                draft,
                setDraft,
                busy,
                saveCharacter,
                models,
                setModels,
                action,
                setNotice,
              }}
            />
          ) : (
            <>
              <div className="resource-toolbar">
                <label className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search characters"
                    placeholder="Search by name or character id…"
                    value={characterQuery}
                    onChange={(e) => setCharacterQuery(e.target.value)}
                  />
                </label>
                <button
                  aria-label="Refresh characters"
                  className="icon-button"
                  disabled={busy}
                  onClick={() => void action(refresh)}
                >
                  <RefreshCw size={16} />
                </button>
                <div className="view-toggle">
                  <button
                    aria-label="Grid view"
                    aria-pressed={characterView === "grid"}
                    onClick={() => setCharacterView("grid")}
                  >
                    <LayoutGrid size={16} />
                    Grid
                  </button>
                  <button
                    aria-label="List view"
                    aria-pressed={characterView === "list"}
                    onClick={() => setCharacterView("list")}
                  >
                    <List size={16} />
                    List
                  </button>
                </div>
              </div>
              <div
                className={
                  "cards character-collection " +
                  (characterView === "list" ? "list-view" : "")
                }
              >
                {characters
                  .filter((c) =>
                    (c.name + " " + c.character_id)
                      .toLowerCase()
                      .includes(characterQuery.toLowerCase()),
                  )
                  .map((c) => (
                    <article className="card" key={c.character_id}>
                      <div className="avatar">{c.name.slice(0, 1)}</div>
                      <h2>{c.name}</h2>
                      <p>{c.system_prompt.slice(0, 130)}</p>
                      <small>
                        {c.phases.length} 個階段 ·{" "}
                        {c.published_hash ? "已有發佈背景" : "背景未發佈"}
                      </small>
                      <div className="actions">
                        <button onClick={() => setDraft(c)}>編輯</button>
                        <button
                          disabled={busy}
                          onClick={() => void startChat(c)}
                        >
                          聊天
                        </button>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void action(async () => {
                              await api(
                                `/characters/${c.character_id}/publish`,
                                "POST",
                              );
                              await refresh();
                              setNotice("背景已發佈。");
                            })
                          }
                        >
                          發佈背景
                        </button>
                        <button
                          className="quiet"
                          disabled={busy}
                          onClick={() => {
                            if (confirm("刪除此角色？必須先刪除其對話。"))
                              void action(async () => {
                                await api(
                                  `/characters/${c.character_id}`,
                                  "DELETE",
                                );
                                await refresh();
                              });
                          }}
                        >
                          刪除
                        </button>
                      </div>
                    </article>
                  ))}
                {!characters.length && (
                  <div className="empty-state">
                    <Sparkles size={32} />
                    <h2>No characters yet</h2>
                    <p>建立第一個角色，開始新的故事。</p>
                    <button
                      className="primary"
                      onClick={() => setDraft(empty())}
                    >
                      ＋ 建立角色
                    </button>
                  </div>
                )}
                {characters.length > 0 &&
                  !characters.some((c) =>
                    (c.name + " " + c.character_id)
                      .toLowerCase()
                      .includes(characterQuery.toLowerCase()),
                  ) && <p className="empty-state">No matching characters</p>}
              </div>
            </>
          )}
        </section>
      )}
      {tab === "settings" && prefs && (
        <SettingsPanel
          {...{
            prefs,
            busy,
            action,
            refresh,
            setNotice,
            health,
            setHealth,
          }}
        />
      )}
    </WorkspaceShell>
  );
}
