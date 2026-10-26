import "@fontsource/geist/latin-400.css";
import "@fontsource/geist/latin-500.css";
import "@fontsource/geist/latin-600.css";
import "./globals.css";
export const metadata = {
  title: "達妮婭 · AI Character",
  description:
    "A local character chat workspace with an unofficial Denia theme from Wuthering Waves.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className="dark" suppressHydrationWarning>
      <body>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{document.documentElement.classList.toggle('dark',localStorage.getItem('aiweb-theme')!=='light')}catch{}",
          }}
        />
        {children}
      </body>
    </html>
  );
}
