import type { Dispatch, SetStateAction } from "react";
import { api, type Character, type ModelOption, type Action } from "@/lib/api";

type Props = {
  draft: Character;
  setDraft: Dispatch<SetStateAction<Character | null>>;
  busy: boolean;
  saveCharacter: () => Promise<void>;
  models: ModelOption[];
  setModels: Dispatch<SetStateAction<ModelOption[]>>;
  action: Action;
  setNotice: Dispatch<SetStateAction<string>>;
};
export default function CharacterEditor({
  draft,
  setDraft,
  busy,
  saveCharacter,
  models,
  setModels,
  action,
  setNotice,
}: Props) {
  return (
    <form
      className="editor"
      onSubmit={(e) => {
        e.preventDefault();
        void saveCharacter();
      }}
    >
      <h2>{draft.character_id ? "編輯角色" : "建立角色"}</h2>
      <label>
        名字
        <input
          required
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          maxLength={100}
        />
      </label>
      <label>
        角色指令
        <textarea
          required
          rows={5}
          value={draft.system_prompt}
          onChange={(e) =>
            setDraft({ ...draft, system_prompt: e.target.value })
          }
          placeholder="個性、說話方式、故事設定…"
        />
      </label>
      <label>
        開場白
        <textarea
          value={draft.opening_message}
          onChange={(e) =>
            setDraft({ ...draft, opening_message: e.target.value })
          }
        />
      </label>
      <label>
        背景知識（儲存後手動發佈到 RAG）
        <textarea
          rows={5}
          value={draft.background}
          onChange={(e) => setDraft({ ...draft, background: e.target.value })}
        />
      </label>
      <div className="two-col">
        <label>
          模型來源
          <select
            value={draft.provider}
            onChange={(e) =>
              setDraft({
                ...draft,
                provider: e.target.value as Character["provider"],
                model: "",
              })
            }
          >
            <option value="chatgpt">ChatGPT 登入</option>
            <option value="endpoint">自訂 endpoint</option>
          </select>
        </label>
        <label>
          模型 ID
          <input
            value={draft.model}
            list="model-list"
            onChange={(e) => setDraft({ ...draft, model: e.target.value })}
            placeholder={
              draft.provider === "endpoint"
                ? "留空使用 endpoint 預設模型"
                : "從帳戶取得可用模型"
            }
          />
          <datalist id="model-list">
            {models.map((m) => (
              <option key={m.slug} value={m.slug}>
                {m.display_name}
              </option>
            ))}
          </datalist>
        </label>
      </div>
      {draft.provider === "chatgpt" && (
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void action(async () => {
              setModels(await api("/providers/chatgpt/models"));
              setNotice("可用模型已載入，請在模型 ID 選取。");
            })
          }
        >
          載入 ChatGPT 模型
        </button>
      )}
      <label className="check">
        <input
          type="checkbox"
          checked={draft.memory_enabled}
          onChange={(e) =>
            setDraft({ ...draft, memory_enabled: e.target.checked })
          }
        />
        啟用本段對話的自動記憶
      </label>
      <p>
        <small>
          每輪對話會額外呼叫一次角色模型來抽取記憶，可能消耗模型額度。
        </small>
      </p>
      <h3>
        關係階段 <small>選填；一個角色就能有多種狀態</small>
      </h3>
      {draft.phases.map((p, i) => (
        <div className="phase" key={p.id}>
          <label>
            階段名稱
            <input
              required
              value={p.name}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  phases: draft.phases.map((v, j) =>
                    j === i ? { ...v, name: e.target.value } : v,
                  ),
                })
              }
            />
          </label>
          <label>
            追加指令
            <textarea
              value={p.prompt}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  phases: draft.phases.map((v, j) =>
                    j === i ? { ...v, prompt: e.target.value } : v,
                  ),
                })
              }
            />
          </label>
          <button
            type="button"
            onClick={() =>
              setDraft({
                ...draft,
                phases: draft.phases.filter((_, j) => j !== i),
              })
            }
          >
            移除此階段
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() =>
          setDraft({
            ...draft,
            phases: [
              ...draft.phases,
              { id: crypto.randomUUID(), name: "", prompt: "" },
            ],
          })
        }
      >
        ＋ 加入階段
      </button>
      <div className="actions">
        <button className="primary" disabled={busy}>
          儲存角色
        </button>
        <button type="button" onClick={() => setDraft(null)}>
          取消
        </button>
      </div>
    </form>
  );
}
