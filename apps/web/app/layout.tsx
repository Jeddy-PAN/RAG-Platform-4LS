import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Local Enterprise RAG Platform",
  description: "Local project-isolated RAG workbench"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
