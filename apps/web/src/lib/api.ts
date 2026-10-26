import type { components } from "../../../../packages/contracts/api";
export type Phase = Required<components["schemas"]["Phase"]>;
export type Character = Omit<
  Required<components["schemas"]["CharacterInput"]>,
  "phases"
> & { character_id: string; phases: Phase[]; published_hash?: string };
export type Conversation = {
  conversation_id: string;
  character_id: string;
  title: string;
  state: { phase_id: string | null };
  memory_note: string;
  revision: number;
  deleting?: boolean;
};
export type Message = {
  message_id: string;
  role: string;
  content: string;
  retrieval_status?: string;
};
export type Preferences = {
  endpoint: { base_url: string; model: string };
  api_key_configured: boolean;
  active_account: string | null;
  accounts: { id: string; email: string; connected: boolean }[];
};
export type Memory = {
  facts: { text: string }[];
  unavailable?: boolean;
  has_more?: boolean;
  jobs: { job_id: string; status: string; facts?: number }[];
};
export const empty = (): Character => ({
  character_id: "",
  name: "",
  system_prompt: "",
  opening_message: "",
  background: "",
  phases: [],
  memory_enabled: true,
  provider: "chatgpt",
  model: "",
});

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/backend" + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "操作失敗，請檢查設定後重試。",
    );
  return data as T;
}

export type Action = (work: () => Promise<void>) => Promise<void>;
export type ModelOption = { slug: string; display_name?: string };
export type Health = {
  mongo: boolean;
  rag: { ready: boolean; memory_configured?: boolean };
};
