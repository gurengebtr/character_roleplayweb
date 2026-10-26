# AI Character · 達妮婭 / Denia

A local character chat workspace with a Next.js web UI, FastAPI services, MongoDB and Qdrant. One character can have several relationship phases without duplicated characters, persona records or playthrough IDs.

An unofficial **Denia (達妮婭) / Wuthering Waves (鳴潮)** fan theme, with newly generated fan artwork replacing all three original images. The UI includes dark/light themes, collapsible workspace navigation, split-panel chat, character search, grid/list views and a command palette.

![Unofficial AI-generated Denia fan artwork](apps/web/public/art/denia-twilight.png)

The application code is **MIT-licensed**. The character and fan artwork have separate rights; the complete themed distribution is not wholly MIT-licensed. See [asset provenance and licensing boundaries](THIRD_PARTY_ASSETS.md). This project is not affiliated with or endorsed by KURO GAMES.

This is the first local MVP. It rebuilds the basic flows from the legacy projects in a new monorepo; it does not import or modify legacy databases.

## Start

Install **Docker Desktop** (or Docker Engine with Compose), **Node.js 22+**, and **Python 3.12**. Start Docker, then run from this folder:

```sh
./start.sh
```

Open **http://127.0.0.1:3100**. Username is `admin`; the generated password is `BOOTSTRAP_PASSWORD` in the root `.env`. The setup creates this private file automatically. Keep `.env` and `.local/` private and backed up together; they contain the encryption key and encrypted model credentials.

Setup creates a fresh installation; it does not import users, credentials or conversations from another checkout. If another copy owns the Docker project or ports, setup stops with an ownership error. Stop/use the existing copy, or provision separate databases manually; do not delete its volumes or copy its installation manifest to bypass this check.

First setup downloads dependencies, database images and a local embedding model. The interface reports when embedding is ready. Use `127.0.0.1` consistently, including the ChatGPT callback.

For subsequent runs with dependencies and databases already ready:

```sh
npm run dev
```

To provision/check without launching the app:

```sh
./setup.sh          # start owned DB containers; add missing compatible indexes
./setup.sh --check  # read-only drift check; exit 2 if migration/additions needed
```

`Ctrl+C` stops the web/API/RAG processes. To stop the databases while retaining data:

```sh
docker compose -f deploy/local/compose.yaml stop
```

Ports: web **3100**, API **8100**, RAG **8101**, Mongo **27028**, Qdrant **6338**, all bound to loopback. DB data lives in this Compose project's named volumes. Existing unrelated local databases are not adopted.

## First conversation

1. Sign in to the local workspace and open **LLM Models**.
2. Choose **Continue with ChatGPT**, authorize your account, then return to the app. Alternatively, configure an OpenAI-compatible `/chat/completions` endpoint; the base URL includes `/v1` when required by your provider. Local endpoints may omit an API key.
3. Create a character: name, system instructions, optional opening message/background/phases. For ChatGPT, click **載入 ChatGPT 模型** and choose an available model ID. For an endpoint, a blank character model uses the configured default.
4. Save the character. Click **發佈背景** to index its background; saving an edit alone does not publish it.
5. Start a new conversation. **記憶與階段** lets you choose a phase, maintain fixed story notes, inspect extracted facts and retry failed memory jobs.

Automatic memory uses the character's model in an **additional background model request** after each completed turn. It can be disabled per character. Extraction failures never discard the chat response. A new conversation starts with independent memory, notes and the first configured phase. Phases are manually selected in this MVP; automatic intimacy scoring is deferred.

For a Traditional Chinese Denia character, copy the instructions, opening message, background and phases from [`examples/characters/denia.zh-Hant.json`](examples/characters/denia.zh-Hant.json) into the character editor, then choose a model your account can access and publish the background. The preset is a fan interpretation, not official game dialogue.

## ChatGPT connection

Implements the official [open-source token-sharing sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [models/inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference), and [session](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions) flows: PKCE, state/nonce, issued client registrations, signed ID-token validation, encrypted credentials, refresh, account switching and revoke-on-disconnect. Inference uses public `/v1/responses`, `store: false`, and waits for a completed streamed response before saving.

The local NextAuth session is separate from ChatGPT authorization. A ChatGPT connection neither creates a local user nor shares your browser session with the server. Availability and model access depend on the account and authorization granted.

**Validation boundary:** the OAuth/token/Responses protocol is covered by automated mocked-provider tests. A real personal ChatGPT login and paid/account inference have not been performed as part of this build. Complete that acceptance check with your account in the UI.

## Repository

- `apps/web` — Next.js App Router, NextAuth credentials, authenticated API proxy and UI components.
- `services/api/ai_character_api` — domain/auth routes, model adapters, encrypted OAuth store, conversation commit journal and memory worker.
- `services/rag/ai_character_rag` — local FastEmbed embeddings, versioned background search and scoped memory in Qdrant.
- `packages/contracts` — generated OpenAPI and TypeScript input contracts; Pydantic is the source.
- `scripts` / `deploy/local` — safe local provisioning, schema inspection and process launcher.
- `tests` — API, OAuth, recovery, isolation, schema and real-browser integration checks.

Mongo domain collections: **characters, conversations, messages**. Infrastructure collections: **users, settings, memory_jobs**. Two Qdrant collections: **ac_background, ac_memory**. See [implemented MVP design](docs/implemented-mvp.zh-HK.md) for fields and boundaries.

## Development checks

```sh
npm run lint
npm run typecheck
npm audit --omit=dev
npm test
npm run contracts
npm run build
npx playwright install chromium
npm run test:e2e
```

Python tests need the local Mongo service and use disposable `ac_test_*` databases. The browser test uses a temporary local user, a deterministic test model server, the real services, real local embeddings and Qdrant; it deletes its own data afterwards. It never calls a paid model. The browser test can start the app itself if it is not running.

`requirements.lock` and `package-lock.json` pin the installed dependency graph. Update them deliberately and rerun checks. Restart `npm run dev` after Python changes; the MVP deliberately runs one API process/worker. Frontend edits hot-reload.

## Current boundaries

- Local trusted-machine use, one API process. Public deployment, production auth, horizontal workers and Supabase support are deferred. NextAuth manages its own session; no separate legacy JWT auth stack was added.
- Memory is scoped fact extraction plus exact-text deduplication and semantic retrieval, not the full legacy mem0 entity/classifier pipeline. Conflicting facts are not automatically reconciled; a new conversation resets the story.
- Phase changes affect future prompts only. Background publish switches to a complete indexed version; old published versions are retained until character deletion. No destructive automatic migrations or database image upgrades.
- `--check` reports manifest, index/vector-schema and ownership differences. Missing compatible schema can be added by setup. Incompatible embedding dimensions/model, schema versions or changed Compose manifests require an explicit migration; setup stops instead of resetting data.
- Background supports pasted text; file ingestion, game-client integration, streaming tokens into the UI, branching/regeneration, group chat and legacy-data import are deferred.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and [SECURITY.md](SECURITY.md) for private security reports. The MIT license covers this repository's application code and documentation; third-party components, character rights and fan artwork retain their respective terms. No original legacy images, private environment files, local databases or model credentials are included.
