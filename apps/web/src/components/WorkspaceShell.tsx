"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  LayoutDashboard,
  Sparkles,
  MessageSquare,
  SlidersHorizontal,
  PanelLeft,
  Search,
  LogOut,
  ArrowRight,
} from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import type { Character, Conversation } from "@/lib/api";

const navigation = [
  { id: "home", label: "Homepage", icon: LayoutDashboard },
  { id: "characters", label: "Characters", icon: Sparkles },
  { id: "chat", label: "Chat Sessions", icon: MessageSquare },
  { id: "settings", label: "LLM Models", icon: SlidersHorizontal },
];
export default function WorkspaceShell({
  tab,
  navigate,
  username,
  logout,
  children,
  characters,
  conversations,
  selectConversation,
  editCharacter,
}: {
  tab: string;
  navigate: (tab: string) => void;
  username: string;
  logout: () => Promise<void>;
  children: ReactNode;
  characters: Character[];
  conversations: Conversation[];
  selectConversation: (id: string) => void;
  editCharacter: (c: Character) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [query, setQuery] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const openSearch = () => {
    setQuery("");
    dialog.current?.showModal();
    search.current?.focus();
  };
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (dialog.current?.open) dialog.current.close();
        else openSearch();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const go = (id: string) => {
    navigate(id);
    setMobileOpen(false);
    dialog.current?.close();
  };
  const matches = (value: string) =>
    value.toLowerCase().includes(query.toLowerCase());
  return (
    <div
      className={`workspace ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "mobile-nav-open" : ""}`}
    >
      {mobileOpen && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className="sidebar" aria-label="Main navigation">
        <button
          className="brand"
          aria-label="AIWEB home"
          onClick={() => go("home")}
        >
          <span className="brand-mark">
            <Sparkles size={19} />
          </span>
          <span className="nav-label">
            AIWEB<small>Role-Play Workspace</small>
          </span>
        </button>
        <nav>
          {navigation.map(({ id, label, icon: Icon }, i) => (
            <div key={id}>
              {(i === 0 || i === 3) && (
                <div className="side-heading nav-label">
                  {i === 0 ? "Workspace" : "Config"}
                </div>
              )}
              <button
                title={label}
                aria-label={label}
                aria-current={tab === id ? "page" : undefined}
                className={tab === id ? "selected" : ""}
                onClick={() => go(id)}
              >
                <Icon size={18} />
                <span className="nav-label">{label}</span>
              </button>
            </div>
          ))}
        </nav>
        <footer>
          <span className="avatar account-avatar">
            {username.slice(0, 1).toUpperCase()}
          </span>
          <span className="account-name nav-label">
            {username}
            <small>Local workspace</small>
          </span>
          <form action={logout}>
            <button className="icon-button" aria-label="登出" title="登出">
              <LogOut size={17} />
            </button>
          </form>
        </footer>
      </aside>
      <main
        className={"workspace-main " + (tab === "chat" ? "viewport-page" : "")}
      >
        <header className="topbar">
          <button
            className="icon-button"
            aria-label="Toggle navigation"
            onClick={() => {
              if (window.matchMedia("(max-width: 760px)").matches)
                setMobileOpen(!mobileOpen);
              else setCollapsed(!collapsed);
            }}
          >
            <PanelLeft size={19} />
          </button>
          <button className="command-trigger" onClick={openSearch}>
            <Search size={16} />
            <span>Search workspace…</span>
            <kbd>⌘ K</kbd>
          </button>
          <div className="spacer" />
          <span className="badge">LOCAL</span>
          <ThemeToggle />
        </header>
        {children}
      </main>
      <dialog
        ref={dialog}
        className="command-dialog"
        aria-label="Search workspace"
        onClick={(e) => {
          if (e.target === dialog.current) dialog.current.close();
        }}
      >
        <div className="command-input">
          <Search size={19} />
          <input
            ref={search}
            aria-label="Search pages, characters and chats"
            placeholder="Search pages, characters and chats…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="quiet" onClick={() => dialog.current?.close()}>
            Esc
          </button>
        </div>
        <div className="command-results">
          <small>Pages</small>
          {navigation
            .filter((n) => matches(n.label))
            .map((n) => (
              <button key={n.id} onClick={() => go(n.id)}>
                <n.icon size={17} />
                {n.label}
                <ArrowRight size={15} />
              </button>
            ))}
          {characters
            .filter((c) => matches(c.name))
            .slice(0, 8)
            .map((c) => (
              <button
                key={c.character_id}
                onClick={() => {
                  editCharacter(c);
                  go("characters");
                }}
              >
                <Sparkles size={17} />
                {c.name}
                <small>Character</small>
              </button>
            ))}
          {conversations
            .filter((c) => matches(c.title))
            .slice(0, 8)
            .map((c) => (
              <button
                key={c.conversation_id}
                onClick={() => {
                  selectConversation(c.conversation_id);
                  go("chat");
                }}
              >
                <MessageSquare size={17} />
                {c.title}
                <small>Chat</small>
              </button>
            ))}
        </div>
      </dialog>
    </div>
  );
}
