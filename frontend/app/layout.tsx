import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TruthLens AI — Sosyal Güven Analiz Sistemi",
  description:
    "Yapay zeka destekli bilgi güvenilirliği ve sosyal medya içerik analiz sistemi.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr" className="h-full antialiased">
      <body className="min-h-full bg-slate-950">
        {children}
      </body>
    </html>
  );
}