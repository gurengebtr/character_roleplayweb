import { useState, type Dispatch, type SetStateAction } from "react";
import { api, type Action, type Preferences, type Health } from "@/lib/api";
type Props = {
  prefs: Preferences;
  busy: boolean;
  action: Action;
  refresh: () => Promise<void>;
  setNotice: Dispatch<SetStateAction<string>>;
  health: Health | null;
  setHealth: Dispatch<SetStateAction<Health | null>>;
};
export default function SettingsPanel({
  prefs,
  busy,
  action,
  refresh,
  setNotice,
  health,
  setHealth,
}: Props) {
  const [endpoint, setEndpoint] = useState({ ...prefs.endpoint, api_key: "" });
  return (
    <section className="page settings">
      <div className="eyebrow">CONFIG</div>
      <h1>LLM Models</h1>
      <p>管理 ChatGPT 帳戶、模型 endpoint 與本機服務狀態。</p>
      <article className="panel">
        <h2>ChatGPT</h2>
        <p>連接你的 ChatGPT 帳戶，然後在角色選擇帳戶可用的模型。</p>
        <button
          className="primary"
          disabled={busy}
          onClick={() =>
            void action(async () => {
              const result = await api<{ url: string }>(
                "/providers/chatgpt/connect",
                "POST",
              );
              window.location.assign(result.url);
            })
          }
        >
          Continue with ChatGPT
        </button>
        {prefs?.accounts.map((a) => (
          <div className="account" key={a.id}>
            <span>
              {a.email || a.id.slice(0, 10)}{" "}
              {prefs.active_account === a.id && <b>使用中</b>}
            </span>
            {a.connected ? (
              <>
                <button
                  onClick={() =>
                    void action(async () => {
                      await api(`/providers/chatgpt/select/${a.id}`, "POST");
                      await refresh();
                    })
                  }
                >
                  選用
                </button>
                <button
                  onClick={() =>
                    void action(async () => {
                      const r = await api<{ revocation_confirmed: boolean }>(
                        `/providers/chatgpt/disconnect/${a.id}`,
                        "POST",
                      );
                      await refresh();
                      setNotice(
                        r.revocation_confirmed
                          ? "已登出並撤銷連線。"
                          : "本機憑證已清除；遠端撤銷尚未確認，請在 ChatGPT 檢查授權。",
                      );
                    })
                  }
                >
                  登出帳戶
                </button>
              </>
            ) : (
              <button
                onClick={() =>
                  void action(async () => {
                    const r = await api<{ url: string }>(
                      `/providers/chatgpt/connect?account=${a.id}`,
                      "POST",
                    );
                    window.location.assign(r.url);
                  })
                }
              >
                重新連接
              </button>
            )}
          </div>
        ))}
      </article>
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          void action(async () => {
            await api("/settings/endpoint", "PUT", {
              ...endpoint,
              api_key: endpoint.api_key || null,
            });
            setEndpoint({ ...endpoint, api_key: "" });
            await refresh();
            setNotice("Endpoint 已儲存。");
          });
        }}
      >
        <h2>自訂模型 endpoint</h2>
        <p>相容 OpenAI Chat Completions 的服務；API key 會加密儲存在本機。</p>
        <label>
          Base URL
          <input
            type="url"
            required
            placeholder="http://127.0.0.1:11434/v1"
            value={endpoint.base_url}
            onChange={(e) =>
              setEndpoint({ ...endpoint, base_url: e.target.value })
            }
          />
        </label>
        <label>
          預設模型
          <input
            required
            value={endpoint.model}
            onChange={(e) =>
              setEndpoint({ ...endpoint, model: e.target.value })
            }
          />
        </label>
        <label>
          API key
          <input
            type="password"
            autoComplete="off"
            placeholder={
              prefs?.api_key_configured ? "已設定；留空保留" : "選填"
            }
            value={endpoint.api_key}
            onChange={(e) =>
              setEndpoint({ ...endpoint, api_key: e.target.value })
            }
          />
        </label>
        <button className="primary" disabled={busy}>
          儲存 endpoint
        </button>
      </form>
      <article className="panel">
        <h2>本機服務</h2>
        <p>MongoDB · {health?.mongo ? "已連接" : "未確認"}</p>
        <p>
          Qdrant / Embedding · {health?.rag.ready ? "就緒" : "載入中或未連接"}
        </p>
        <p>
          自動記憶抽取 ·{" "}
          {health?.rag.memory_configured ? "使用角色的模型" : "未就緒"}
        </p>
        <button
          onClick={() =>
            void action(async () => setHealth(await api("/health")))
          }
        >
          重新檢查
        </button>
        <small>
          本機登入與 ChatGPT 授權各自獨立。新對話不會繼承另一段對話的記憶。
        </small>
      </article>
    </section>
  );
}
