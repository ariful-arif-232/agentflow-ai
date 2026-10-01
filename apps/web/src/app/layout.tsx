import type { Metadata } from "next";
import "./globals.css";
import { AsOfProvider } from "@/lib/asof";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = {
  title: "AgentFlow AI — Predictive Liquidity Orchestration",
  description: "Explainable predictive liquidity orchestration for MFS agent networks. Predict. Explain. Rebalance.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <AsOfProvider>
          <Shell>{children}</Shell>
        </AsOfProvider>
      </body>
    </html>
  );
}
