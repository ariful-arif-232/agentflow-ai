import type { Metadata } from "next";
import "./globals.css";
import { AsOfProvider } from "@/lib/asof";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = {
  title: "AgentFlow AI — Same liquidity. Placed ahead of demand.",
  description:
    "Explainable liquidity operations for MFS agent networks: plan physical cash and e-float before demand arrives, monitor intraday cash pressure, and keep a human in charge. Synthetic data; no money moves.",
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
