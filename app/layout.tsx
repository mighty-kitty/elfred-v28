import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./product.css";
import "./premium.css";
import "./v27.css";
import "./v27-refine.css";
import "./v27-7.css";
import "./v27-7-tasks-profile.css";
import "./v27-8.css";
import "./v27-8-artwork.css";
import "./v27-8-home-player.css";
import "./v27-8-final-pass.css";
import "./v27-8-daily-agent.css";
import "./v27-9.css";
import "./v28.css";

export const viewport:Viewport={width:"device-width",initialScale:1,viewportFit:"cover",interactiveWidget:"resizes-content",themeColor:"#f7f7f8"};

export const metadata: Metadata = {
  title: "Elfred V28 · 从目标到结果",
  description: "一个真正连通注册、目标、任务、Agent、知识与记忆的 Personal Agent 产品原型。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
