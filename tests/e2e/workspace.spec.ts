import { test, expect } from "@playwright/test";
import { createServer, Server } from "node:http";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";

const owner = "e2e-" + randomUUID();
const password = randomUUID();
const webOrigin = new URL(
  process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3100",
).origin;
let server: Server;
function python(source: string) {
  const result = spawnSync(".venv/bin/python", ["-c", source], {
    encoding: "utf8",
    input: JSON.stringify({ owner, password }),
    env: { ...process.env, PYTHONPATH: "services/api:services/rag:." },
  });
  if (result.status !== 0) throw new Error(result.stderr);
}
test.beforeAll(async () => {
  python(`import sys,json
from pymongo import MongoClient
from ai_character_api.config import settings
from ai_character_api.auth import hash_password
x=json.load(sys.stdin)
db=MongoClient(settings.mongo_uri)[settings.mongo_db]
db.users.insert_one({'user_id':x['owner'],'username':x['owner'],'password_hash':hash_password(x['password'])})`);
  server = createServer(async (req, res) => {
    let body = "";
    for await (const part of req) body += part;
    const data = JSON.parse(body);
    const extracting = data.messages[0].content.startsWith("Extract");
    res.writeHead(200, { "content-type": "application/json" });
    res.end(
      JSON.stringify({
        choices: [
          {
            message: {
              role: "assistant",
              content: extracting
                ? '["旅人喜歡熱茶"]'
                : "你好，旅人。我記得你喜歡熱茶，來喝一杯吧。",
            },
          },
        ],
      }),
    );
  });
  await new Promise<void>((resolve) =>
    server.listen(8199, "127.0.0.1", resolve),
  );
});
test.afterAll(async () => {
  await new Promise<void>((resolve) => server?.close(() => resolve()));
  python(`import sys,json
from hashlib import sha256
import os
from dotenv import load_dotenv
load_dotenv('.env')
from pymongo import MongoClient
from qdrant_client import QdrantClient,models
from ai_character_api.config import settings
x=json.load(sys.stdin);u=x['owner'];db=MongoClient(settings.mongo_uri)[settings.mongo_db]
ids=[d['conversation_id'] for d in db.conversations.find({'user_id':u})]
for collection in ['messages','memory_jobs']: db[collection].delete_many({'conversation_id':{'$in':ids}})
db.conversations.delete_many({'user_id':u});db.characters.delete_many({'owner_id':u});db.users.delete_many({'user_id':u})
(settings.credential_dir/(sha256(u.encode()).hexdigest()+'.enc')).unlink(missing_ok=True)
q=QdrantClient(url=os.environ.get('QDRANT_URL','http://127.0.0.1:6338'))
for kind in ['background','memory']: q.delete(os.environ.get('QDRANT_PREFIX','ac_')+kind,points_selector=models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key='user_id',match=models.MatchValue(value=u))])),wait=True)
q.close()`);
});

test("login, create character, publish, chat, remember, change phase and delete", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/login/);
  const artwork = await page.request.get("/art/denia-twilight.png");
  expect(artwork.status()).toBe(200);
  expect(artwork.headers()["content-type"]).toContain("image/png");
  await expect(page.locator(".auth-brand-panel")).toHaveCSS(
    "background-image",
    /denia-twilight\.png/,
  );
  expect((await page.request.get("/api/backend/characters")).status()).toBe(
    401,
  );
  await page.screenshot({
    path: ".local/denia-login.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByLabel("Username").fill(owner);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "進入工作室" }).click();
  await expect(
    page.getByRole("heading", { name: "Awaken the Fiction" }),
  ).toBeVisible();
  await expect(page.locator(".denia-hero")).toHaveCSS(
    "background-image",
    /denia-twilight\.png/,
  );
  const guideArt = page.getByAltText(
    "達妮婭（Denia）在星光窗邊與泡泡相伴的同人插畫",
  );
  await guideArt.scrollIntoViewIfNeeded();
  await expect
    .poll(() => guideArt.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBe(1536);
  await page.locator(".denia-hero").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: ".local/denia-home.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await expect(page.locator(".workspace")).toHaveClass(/sidebar-collapsed/);
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("button", { name: /Search workspace/ }).click();
  await page.getByLabel("Search pages, characters and chats").fill("LLM");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "LLM Models" })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();

  await expect(
    page.getByRole("button", { name: "LLM Models", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "LLM Models", exact: true }).click();
  await page.getByLabel("Base URL").fill("http://127.0.0.1:8199/v1");
  await page.getByLabel("預設模型").fill("integration-test");
  await page.getByRole("button", { name: "儲存 endpoint" }).click();
  await expect(page.getByRole("status")).toContainText("Endpoint 已儲存");
  // OAuth start is real application code; don't submit the user's external account.
  const connect = await page.request.post(
    "/api/backend/providers/chatgpt/connect",
    { headers: { origin: webOrigin } },
  );
  const authURL = new URL((await connect.json()).url);
  expect(authURL.origin).toBe("https://auth.openai.com");
  expect(authURL.searchParams.get("code_challenge_method")).toBe("S256");
  expect(
    (
      await page.request.post("/api/backend/characters", {
        headers: { origin: "http://evil.invalid" },
        data: {},
      })
    ).status(),
  ).toBe(403);
  await page.getByRole("button", { name: "Characters", exact: true }).click();
  await page.getByRole("button", { name: "＋ 新角色" }).click();
  await page.getByLabel("名字", { exact: true }).fill("莉亞");
  await page
    .getByLabel("角色指令")
    .fill("你是溫柔的鍊金術師莉亞，以繁體中文回應。");
  await page.getByLabel("開場白").fill("歡迎來到我的工作室。");
  await page
    .getByLabel("背景知識")
    .fill("莉亞住在海邊的小鎮，喜歡調配茶飲和製作藥水。");
  await page.getByLabel("模型來源").selectOption("endpoint");
  await page.getByRole("button", { name: "＋ 加入階段" }).click();
  await page.getByLabel("階段名稱").fill("朋友");
  await page.getByLabel("追加指令").fill("把旅人當成朋友，以親切方式回應。");
  await page.getByRole("button", { name: "儲存角色", exact: true }).click();
  await expect(page.getByRole("heading", { name: "莉亞" })).toBeVisible();
  await page.getByLabel("Search characters").fill("missing-character");
  await expect(
    page.getByText("No matching characters", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search characters").fill("莉亞");
  await page.getByRole("button", { name: "List view", exact: true }).click();
  await expect(page.locator(".character-collection")).toHaveClass(/list-view/);
  await page.getByRole("button", { name: "Grid view", exact: true }).click();
  await page.screenshot({
    path: ".local/denia-characters.png",
    fullPage: true,
    animations: "disabled",
  });

  await expect
    .poll(
      async () =>
        (await (await page.request.get("/api/backend/health")).json()).rag
          .ready,
      { timeout: 60000 },
    )
    .toBe(true);
  await page.getByRole("button", { name: "發佈背景", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("背景已發佈。", {
    timeout: 60000,
  });
  await page.getByRole("button", { name: "聊天", exact: true }).click();
  await expect(
    page.getByText("歡迎來到我的工作室。", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("訊息", { exact: true }).fill("我喜歡熱茶");
  await page.getByRole("button", { name: "傳送 ↑", exact: true }).click();
  await expect(
    page.getByText("你好，旅人。我記得你喜歡熱茶，來喝一杯吧。", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "記憶與階段" }).click();
  await expect(page.getByText("• 旅人喜歡熱茶", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await page.getByLabel("這段故事的固定筆記").fill("準備一起旅行");
  await page.getByRole("button", { name: "儲存筆記" }).click();
  await page.getByLabel("關係階段").selectOption("");
  await expect(page.getByRole("status")).toHaveText("對話狀態已更新。");
  await page.reload();
  await page
    .getByRole("button", { name: "Chat Sessions", exact: true })
    .click();
  await page.getByRole("button", { name: "莉亞", exact: true }).click();
  await expect(page.getByText("我喜歡熱茶", { exact: true })).toBeVisible();
  await expect(page.locator(".message > div")).toHaveText([
    "歡迎來到我的工作室。",
    "我喜歡熱茶",
    "你好，旅人。我記得你喜歡熱茶，來喝一杯吧。",
  ]);
  await page.screenshot({
    path: ".local/mvp-chat.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () => (await page.locator(".sidebar").boundingBox())!.x)
    .toBeLessThanOrEqual(-239);
  await expect(
    page.getByRole("button", { name: "莉亞", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: ".local/mvp-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "刪除", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Start a conversation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("button", { name: "Characters", exact: true }).click();
  await page.getByRole("button", { name: "刪除", exact: true }).click();
  await expect(page.getByRole("heading", { name: "莉亞" })).toHaveCount(0);
});
