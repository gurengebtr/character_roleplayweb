# 已實作 MVP（以本文件為準）

本文件描述目前 repository 的實際架構與功能。此版本不匯入舊系統的資料或執行流程；舊版設計與 migration 評估文件已移出公開 source tree，以免與現行實作混淆。

## 最小 domain

**characters**：`character_id`, `owner_id`, `name`, `system_prompt`, `opening_message`, `background`, `phases[{id,name,prompt}]`, `memory_enabled`, `provider`, `model`, `revision`, `published_hash`, `published_background`, timestamps。

**conversations**：`conversation_id`, `user_id`, `character_id`, `title`, `state.phase_id`, `memory_note`, `revision`, timestamps。`pending_commit` 是短暫的訊息／outbox 提交 journal；`deleting` 是可重試清理的 tombstone。

**messages**：`message_id`, `conversation_id`, `role`, `content`, `position`, `created_at`；生成訊息另帶 `phase_id`, `character_revision`, `request_hash`，assistant 帶 `retrieval_status`。開場白標示 `origin=opening`。

角色自己包含背景和階段，不需要 persona collection。Conversation 同時就是故事／記憶隔離邊界，不需要第二個 playthrough ID，也沒有額外 relationship collection。MVP 手動選階段；不維護親密度計分引擎。

## 必要基礎設施

Mongo `users` 儲存本機帳號和 scrypt 密碼 hash；`settings` 只存 schema version。`memory_jobs` 是 API 唯一擁有的 outbox，含 scope、來源訊息 IDs、模型設定快照、抽取結果、重試狀態與時間。工作完成後移除重複的原始訊息內容。沒有 RAG 自己的一套 jobs collection。

Qdrant `ac_background` 儲存 user/character/version 範圍的片段；`ac_memory` 儲存 user/character/conversation 範圍的 facts，以及同一 collection 內不參與搜尋的 job receipts。相同文字的記憶在同一 conversation 去重，保留最近來源資訊。不同對話、角色與使用者不共享記憶。

OAuth 和 endpoint 憑證不是 domain collections，儲存於 `.local/credentials` 的加密檔案。`.env` 中的 `CREDENTIAL_KEY` 不可隨意重建，否則無法解密現有憑證。

## 一輪對話

1. NextAuth 確認本機 session；BFF 注入 server-only 的 service token 和可信 user ID。
2. API 檢查 ownership，讀取角色／階段／固定筆記，取得已發佈背景與該對話的相關記憶。
3. 模型完整成功後，先寫入 conversation 的單文件 journal，再以 deterministic IDs upsert 訊息與 memory job。程序中斷後可 replay；同 request ID 不會重複落庫。
4. 背景 worker 使用角色模型抽取最多五項 user 明確提及的事實，保存抽取結果後交給 RAG embedding/upsert。失敗 backoff，五次後顯示 dead，可手動重試。
5. 刪除對話先標示 tombstone，再刪 Qdrant scope 和 Mongo 訊息／jobs。RAG 中斷時保留 tombstone，讓使用者重試清理，避免誤報成功。

MVP 不搬入完整 mem0 entity/classifier。記憶抽取會多用一次模型，可能消耗 ChatGPT 額度或 endpoint token。未設定角色模型時會顯示錯誤，不會偷偷改用其他模型。

## 本機 setup

`./start.sh` 執行依賴安裝、產生私密設定、啟動兩個 DB、檢查／補上缺少 schema，再啟動三個應用程序。`./setup.sh --check` 只檢查，不啟動容器或修改資料。

Manifest 記錄本專案 root、Compose hash、embedding model/dimension、DB name、Qdrant prefix。遇到不相容變更會停下；對未知 ports、volumes、container ownership 不自動接管。Schema 檢查先收集全部差異，確認沒有衝突才新增索引／collections。這是安全、可重跑的 setup，並非自動進行破壞性 migration。

## 驗證與後續

測試包含真實 Mongo、實際 Qdrant／embedding 的瀏覽器流程，以及 OAuth 的模擬協定測試。真實 ChatGPT 帳戶登入和模型額度可用性仍待使用者驗收。公網 deploy、Supabase、額外 JWT 堆疊、自動關係引擎及 legacy 資料 migration 留待下一階段。
