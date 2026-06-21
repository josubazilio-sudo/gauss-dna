import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Confeitaria",
  description: "Bolos e doces artesanais",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="bg-amber-50 text-stone-800">{children}</body>
    </html>
  );
}
