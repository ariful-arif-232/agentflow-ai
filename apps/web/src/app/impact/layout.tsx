import type { ReactNode } from "react";
import { ModelMonitoringCard } from "@/components/ModelMonitoring";

export default function ImpactLayout({ children }: { children: ReactNode }) {
  return <>{children}<ModelMonitoringCard /></>;
}
