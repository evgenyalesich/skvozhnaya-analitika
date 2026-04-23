import React from "react";
import { Pill } from "./Pill";
import type { PillVariant } from "./Pill";

// re-export so callers can import from one place
export type { PillVariant };

interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  stripe?: string; // CSS color
  pill?: React.ReactNode;
  foot?: React.ReactNode;
  valueColor?: string;
  onClick?: () => void;
}

export const KpiCard: React.FC<KpiCardProps> = ({
  label, value, stripe = "var(--c-blue)", pill, foot, valueColor, onClick,
}) => (
  <div
    onClick={onClick}
    style={{
      background: "var(--c-surface)",
      border: "1px solid var(--c-border)",
      borderRadius: "var(--r-lg)",
      padding: "18px 18px 16px",
      position: "relative", overflow: "hidden",
      cursor: onClick ? "pointer" : "default",
      transition: "box-shadow 0.15s, transform 0.15s, border-color 0.15s",
      boxShadow: "var(--shadow-sm)",
      minHeight: 144,
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      backdropFilter: "blur(14px)",
    }}
    onMouseEnter={(e) => {
      (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-md)";
      (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)";
      (e.currentTarget as HTMLDivElement).style.borderColor = "var(--c-border2)";
    }}
    onMouseLeave={(e) => {
      (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-sm)";
      (e.currentTarget as HTMLDivElement).style.transform = "none";
      (e.currentTarget as HTMLDivElement).style.borderColor = "var(--c-border)";
    }}
  >
    <div style={{
      position: "absolute",
      inset: 0,
      background: `radial-gradient(circle at top right, ${stripe}18, transparent 28%)`,
      pointerEvents: "none",
    }} />

    {/* Top accent stripe */}
    <div style={{
      position: "absolute", top: 0, left: 0, right: 0, height: 2.5,
      background: stripe, opacity: 0.7,
    }} />

    <div style={{ position: "relative", zIndex: 1 }}>
      <div style={{
        fontSize: 10, fontWeight: 800, letterSpacing: "0.12em",
        textTransform: "uppercase", color: "var(--c-ink3)",
        marginBottom: 14,
      }}>{label}</div>

      <div style={{
        fontSize: 34, fontWeight: 800, letterSpacing: "-0.06em",
        lineHeight: 0.95, color: valueColor || "var(--c-ink)",
        marginBottom: 10, fontFamily: "var(--font)",
      }}>{value}</div>
    </div>

    {(pill || foot) && (
      <div style={{
        position: "relative",
        zIndex: 1,
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexWrap: "wrap",
        fontSize: 11.5,
        color: "var(--c-ink2)",
      }}>
        {pill}
        {foot && <span style={{ color: "var(--c-ink3)" }}>{foot}</span>}
      </div>
    )}
  </div>
);

/** 4-up KPI grid */
export const KpiGrid: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 16,
  }}>{children}</div>
);
