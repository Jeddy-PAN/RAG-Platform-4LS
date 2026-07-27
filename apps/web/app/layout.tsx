import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./styles/base.css";
import "./styles/shared.css";
import "./styles/retrieval.css";
import "./styles/eval.css";
import "./styles/metrics.css";
import "./styles/workbench.css";
import "./styles/responsive.css";

export const metadata: Metadata = {
  title: "Local Enterprise RAG Platform",
  description: "Local project-isolated RAG workbench"
};

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
