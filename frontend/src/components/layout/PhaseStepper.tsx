import { useTranslation } from "react-i18next";
import { PHASE_ORDER } from "@/types";

interface PhaseStepperProps {
  currentPhase: string | undefined;
}

/**
 * 顶栏阶段步进器 v2：
 * - 更大的步骤圆圈，更宽的连接线
 * - 当前阶段高亮青蓝霓虹 accent + 发光
 * - 已完成阶段显示青蓝弱化连接线
 */
export function PhaseStepper({ currentPhase }: PhaseStepperProps) {
  const { t } = useTranslation("dashboard");
  const currentIdx = PHASE_ORDER.findIndex((p) => p === currentPhase);

  return (
    <nav aria-label={t("workflow_phases")}>
      <div className="inline-flex items-center gap-0">
        {PHASE_ORDER.map((phase, idx) => {
          const isActive = currentIdx === idx;
          const isPast = currentIdx > idx;
          const isFuture = currentIdx < idx;
          return (
            <div key={phase} className="flex items-center">
              {/* 步骤项 */}
              <div
                aria-current={isActive ? "step" : undefined}
                className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 transition-all"
                style={
                  isActive
                    ? {
                        color: "var(--color-text)",
                        background: "oklch(0.75 0.18 42 / 0.18)",
                        border: "1px solid oklch(0.75 0.18 42 / 0.35)",
                        boxShadow: "0 0 16px -4px var(--color-accent-glow)",
                      }
                    : isPast
                    ? {
                        color: "oklch(0.55 0.010 240)",
                        background: "transparent",
                        border: "1px solid transparent",
                      }
                    : {
                        color: "oklch(0.38 0.008 240)",
                        background: "transparent",
                        border: "1px solid transparent",
                      }
                }
              >
                {/* 步骤圆圈 */}
                <span
                  className="num inline-grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full text-[10px] font-bold"
                  style={
                    isActive
                      ? {
                          background: "var(--color-accent)",
                          color: "oklch(0.08 0 0)",
                          boxShadow: "0 0 12px -2px var(--color-accent-glow)",
                        }
                      : isPast
                      ? {
                          background: "oklch(0.75 0.18 42 / 0.25)",
                          color: "oklch(0.65 0.08 200)",
                          border: "1px solid oklch(0.75 0.18 42 / 0.20)",
                        }
                      : {
                          background: "oklch(0.09 0.004 240)",
                          color: "oklch(0.38 0.008 240)",
                          border: "1px solid oklch(0.75 0.18 42 / 0.08)",
                        }
                  }
                >
                  {idx + 1}
                </span>
                <span className="whitespace-nowrap text-[12px] font-medium">
                  {t(`phase_${phase}`)}
                </span>
              </div>

              {/* 连接线 */}
              {idx < PHASE_ORDER.length - 1 && (
                <div
                  aria-hidden="true"
                  className="h-px w-5 shrink-0"
                  style={{
                    background: isPast
                      ? "linear-gradient(90deg, oklch(0.75 0.18 42 / 0.40), oklch(0.75 0.18 42 / 0.20))"
                      : isActive
                      ? "linear-gradient(90deg, oklch(0.75 0.18 42 / 0.30), oklch(0.75 0.18 42 / 0.08))"
                      : "oklch(0.75 0.18 42 / 0.08)",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </nav>
  );
}
