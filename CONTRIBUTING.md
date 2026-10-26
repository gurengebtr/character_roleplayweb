# Contributing

Install Docker with Compose, Node.js 22+ and Python 3.12, then run `./setup.sh`. Use `npm run dev` to start the local services. Setup manages only its own databases and refuses to adopt another installation's resources.

Before opening a pull request, run:

```sh
./setup.sh --check
npm run lint
npm run typecheck
npm test
npm run contracts
npm run build
npx playwright install chromium
npm run test:e2e
npm audit --omit=dev
```

Python tests use temporary MongoDB databases. The browser test uses a temporary user and a deterministic local model endpoint, and exercises real database, embedding, chat and memory flows without calling a paid model. Never commit `.env`, `.local/`, database exports, credentials, logs or screenshots containing personal conversations.

Keep `tests/` and its synthetic fixtures in Git: contributors and CI need them to verify changes. Generated test reports, traces, screenshots under `.local/`, coverage output and tool caches are ignored by `.gitignore`. Current architecture is documented in [the implemented-MVP guide](docs/implemented-mvp.zh-HK.md).

The launcher reads app ports from `WEB_URL`, `API_URL` and `RAG_URL`. Keep `AUTH_URL` equal to `WEB_URL` and update `CHATGPT_CALLBACK` for the API port. These URLs must use `http://127.0.0.1:PORT`. For an already running isolated installation, point the browser tests at it with `PLAYWRIGHT_BASE_URL=http://127.0.0.1:PORT npm run test:e2e`. Alternate database installations require manual provisioning; setup manages the default Compose project only.

Keep generated OpenAPI/TypeScript contracts synchronized with Pydantic schemas. Include provenance and suitable permissions for any new media. Code contributions use the MIT license; character/artwork rights follow [THIRD_PARTY_ASSETS.md](THIRD_PARTY_ASSETS.md).
