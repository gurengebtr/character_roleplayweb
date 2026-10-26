import {
  ArrowDown,
  ArrowRight,
  SlidersHorizontal,
  Sparkles,
  MessageSquare,
} from "lucide-react";
export default function HomePage({
  navigate,
}: {
  navigate: (tab: string) => void;
}) {
  return (
    <div className="home-page">
      <section className="denia-hero" aria-label="達妮婭 · Denia fan artwork">
        <div className="hero-inner">
          <p className="eyebrow">達妮婭 / DENIA · FAN ROLE-PLAY</p>
          <div className="hero-title">
            <p className="eyebrow">PROLOGUE</p>
            <h1>Awaken the Fiction</h1>
            <a className="hero-start" href="#setup-flow">
              <ArrowDown size={17} /> START
            </a>
          </div>
          <div className="hero-notes">
            <p>
              <span>01</span>A quiet moment at the academy
            </p>
            <p>
              <span>02</span>Stories beneath a starlit sky
            </p>
            <p>
              <span>03</span>Build characters and test conversations.
            </p>
          </div>
        </div>
      </section>
      <section className="setup-guide" id="setup-flow">
        <div className="eyebrow">SETUP GUIDE</div>
        <h2>Initialize the Core</h2>
        <p>config → character → chat</p>
        {[
          {
            id: "settings",
            title: "Config",
            description: "連接 ChatGPT 或設定模型 endpoint。",
            action: "Configure Models",
            icon: SlidersHorizontal,
          },
          {
            id: "characters",
            title: "Character",
            description: "定義角色、背景與不同關係階段，發佈背景知識。",
            action: "Create Character",
            icon: Sparkles,
          },
          {
            id: "chat",
            title: "Chat",
            description: "開始故事、保存記憶，再調整角色的回應方式。",
            action: "Start Chat",
            icon: MessageSquare,
          },
        ].map((step, i) => (
          <button
            className="setup-step"
            key={step.id}
            onClick={() => navigate(step.id)}
          >
            <span className="step-number">0{i + 1}</span>
            <div>
              <h3>
                <step.icon size={21} />
                {step.title}
              </h3>
              <p>{step.description}</p>
            </div>
            <span className="step-action">
              {step.action}
              <ArrowRight size={17} />
            </span>
          </button>
        ))}
      </section>
      <section className="user-guide">
        <div>
          <div className="eyebrow">USER GUIDE</div>
          <h2>Enter the Story</h2>
          <h3>01　Pick a character</h3>
          <p>挑選角色，開始一段獨立的對話。</p>
          <h3>02　Talk in scene</h3>
          <p>自然地聊天，角色會依背景和目前階段回應。</p>
          <h3>03　Continue the connection</h3>
          <p>查看記憶、補充故事筆記，讓下一輪對話延續。</p>
          <button className="primary" onClick={() => navigate("chat")}>
            Start Chat <ArrowRight size={17} />
          </button>
        </div>
        <img
          src="/art/denia-twilight.png"
          alt="達妮婭（Denia）在星光窗邊與泡泡相伴的同人插畫"
          width={1536}
          height={1024}
          loading="lazy"
        />
      </section>
      <p className="fan-notice">
        達妮婭 · 鳴潮非官方同人專案。角色與作品權利屬於 KURO GAMES。
      </p>
    </div>
  );
}
