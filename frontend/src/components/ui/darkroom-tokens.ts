import type { CSSProperties } from "react";

export const ACCENT_BUTTON_STYLE: CSSProperties = {
  color: "oklch(0.04 0 0)",
  background: "var(--color-accent)",
  boxShadow:
    "0 0 0 1px oklch(0.75 0.18 42 / 0.5), 0 8px 24px -8px oklch(0.75 0.18 42 / 0.45)",
};

export const CARD_STYLE: CSSProperties = {
  background: "oklch(0.07 0.004 240)",
  border: "1px solid oklch(1 0 0 / 0.08)",
};

export const INPUT_CLS =
  "w-full border border-hairline bg-bg-grad-a/55 px-3 py-2 text-[13px] text-text placeholder:text-text-4 transition-colors hover:border-hairline-strong focus:border-accent/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50";

const GHOST_BTN_BASE_CLS =
  "inline-flex items-center border border-hairline bg-bg-grad-a/55 text-text-2 transition-colors hover:border-hairline-strong hover:bg-bg-grad-a hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50";

export const GHOST_BTN_CLS = `${GHOST_BTN_BASE_CLS} gap-1.5 px-3 py-1.5 text-[12px]`;

export const GHOST_BTN_LG_CLS = `${GHOST_BTN_BASE_CLS} gap-2 px-3.5 py-2 text-[12.5px]`;

export const DROPDOWN_PANEL_STYLE: CSSProperties = {
  background: "oklch(0.08 0.004 240 / 0.97)",
  backdropFilter: "blur(20px) saturate(1.2)",
  WebkitBackdropFilter: "blur(20px) saturate(1.2)",
  border: "1px solid oklch(1 0 0 / 0.10)",
};

const ACCENT_BTN_BASE_CLS =
  "inline-flex items-center font-bold uppercase tracking-[0.06em] transition-all hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50";

export const ACCENT_BTN_CLS = `${ACCENT_BTN_BASE_CLS} gap-2 px-4 py-2 text-[11.5px]`;

export const ACCENT_BTN_SM_CLS = `${ACCENT_BTN_BASE_CLS} gap-1.5 px-3 py-1.5 text-[11px]`;

export const ICON_BTN_CLS =
  "p-1 text-text-4 transition-colors enabled:hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-40";

export const ICON_BTN_FILLED_CLS =
  "p-1.5 text-text-3 transition-colors enabled:hover:bg-bg-grad-a enabled:hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-40";

const RADIO_CARD_BASE_CLS =
  "relative flex-1 cursor-pointer border px-3.5 py-2.5 text-center text-[12.5px] transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent";

export function radioCardClass(selected: boolean): string {
  return selected
    ? `${RADIO_CARD_BASE_CLS} border-accent/45 bg-accent-dim text-text shadow-[0_0_22px_-10px_var(--color-accent-glow)]`
    : `${RADIO_CARD_BASE_CLS} border-hairline-soft bg-bg-grad-a/40 text-text-2 hover:border-hairline hover:text-text`;
}

interface PosterGridOptions {
  size?: number;
  maskShape?: string;
  opacity?: number;
}

export function posterGridStyle(opts?: PosterGridOptions): CSSProperties {
  const size = opts?.size ?? 44;
  const mask = `radial-gradient(${opts?.maskShape ?? "70% 70% at 50% 50%"}, black, transparent)`;
  const style: CSSProperties = {
    backgroundImage:
      "linear-gradient(oklch(0.75 0.18 42 / 0.08) 1px, transparent 1px), linear-gradient(90deg, oklch(0.75 0.18 42 / 0.08) 1px, transparent 1px)",
    backgroundSize: `${size}px ${size}px`,
    maskImage: mask,
    WebkitMaskImage: mask,
  };
  if (opts?.opacity !== undefined) style.opacity = opts.opacity;
  return style;
}

interface AmbientGlowOptions {
  at?: string;
  intensity?: number;
}

export function ambientGlowStyle(opts?: AmbientGlowOptions): CSSProperties {
  const at = opts?.at ?? "50% 0%";
  const alpha = opts?.intensity ?? 0.18;
  return {
    background: `radial-gradient(circle at ${at}, oklch(0.75 0.18 42 / ${alpha}), transparent 60%)`,
  };
}
