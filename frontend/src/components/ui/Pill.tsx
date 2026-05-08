// Цветной badge/pill для отображения дельты или статуса (blue/green/red/amber/purple/neutral).
import React from "react";

export type PillVariant = "blue" | "green" | "red" | "amber" | "purple" | "neutral";

interface PillProps {
  variant?: PillVariant;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

const COLORS: Record<PillVariant, { bg: string; color: string }> = {
  blue:    { bg: "var(--c-blue-bg)",   color: "var(--c-blue)"   },
  green:   { bg: "var(--c-green-bg)",  color: "var(--c-green)"  },
  red:     { bg: "var(--c-red-bg)",    color: "var(--c-red)"    },
  amber:   { bg: "var(--c-amber-bg)",  color: "var(--c-amber)"  },
  purple:  { bg: "var(--c-purple-bg)", color: "var(--c-purple)" },
  neutral: { bg: "var(--c-surface2)",  color: "var(--c-ink3)"   },
};

export const Pill: React.FC<PillProps> = ({ variant = "blue", children, style }) => {
  const { bg, color } = COLORS[variant];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "2px 8px", borderRadius: 20,
      fontSize: 10.5, fontWeight: 700,
      background: bg, color,
      ...style,
    }}>{children}</span>
  );
};

/** Auto-selects green/red/amber based on value sign */
export const PillPct: React.FC<{ value: number; decimals?: number; suffix?: string }> = ({
  value, decimals = 1, suffix = "%",
}) => {
  const v = variant(value);
  return <Pill variant={v}>{value > 0 ? "▲ " : value < 0 ? "▼ " : ""}{Math.abs(value).toFixed(decimals)}{suffix}</Pill>;
};

function variant(v: number): PillVariant {
  if (v > 0) return "green";
  if (v < 0) return "red";
  return "amber";
}
