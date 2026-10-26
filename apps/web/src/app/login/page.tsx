import { auth, signIn } from "@/auth";
import { redirect } from "next/navigation";
import { AuthError } from "next-auth";
import { Sparkles } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

export default async function Login({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  if ((await auth())?.user) redirect("/");
  const query = await searchParams;
  async function login(form: FormData) {
    "use server";
    try {
      await signIn("credentials", {
        username: form.get("username"),
        password: form.get("password"),
        redirectTo: "/",
      });
    } catch (error) {
      if (error instanceof AuthError) redirect("/login?error=1");
      throw error;
    }
  }
  return (
    <main className="login-page">
      <aside className="auth-brand-panel">
        <a className="auth-brand" href="/">
          <span className="brand-mark">
            <Sparkles size={21} />
          </span>
          AIWEB
        </a>
        <div>
          <h2>
            Weave your story. Live their fate
            <br />
            Tame the Tides of a Thousand Personalities
          </h2>
          <p>
            Characters. Stories. Echoes. And the quiet power to make them real.
          </p>
          <div className="auth-tags">
            <span>Characters</span>
            <span>Memory</span>
            <span>RAG</span>
            <span>Chat sessions</span>
          </div>
        </div>
        <small>
          達妮婭 / Denia · Unofficial Wuthering Waves fan project · KURO GAMES
        </small>
      </aside>
      <section className="auth-form-pane">
        <div className="auth-theme">
          <ThemeToggle />
        </div>
        <div className="login-card">
          <div className="eyebrow">AIWEB / LOCAL WORKSPACE</div>
          <h1>Welcome back</h1>
          <p>登入工作空間，繼續你的故事。</p>
          <form action={login}>
            <label>
              Username
              <input
                name="username"
                autoComplete="username"
                required
                defaultValue="admin"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                required
              />
            </label>
            {query.error && (
              <p role="alert" className="error">
                登入失敗。請確認帳號、密碼與 API 狀態。
              </p>
            )}
            <button className="primary" type="submit">
              進入工作室 →
            </button>
          </form>
          <small>
            首次登入資料在專案的 .env 檔案。ChatGPT 連線於登入後設定。
          </small>
        </div>
      </section>
    </main>
  );
}
