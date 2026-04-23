import React from "react";

interface DCardProps {
  title?: React.ReactNode;
  subtitle?: string;
  accent?: string; // CSS color for accent bar, default blue
  actions?: React.ReactNode;
  children: React.ReactNode;
  style?: React.CSSProperties;
  noPad?: boolean;
}

export const DCard: React.FC<DCardProps> = ({
  title, subtitle, accent = "var(--c-blue)", actions, children, style, noPad,
}) => (
  <div style={{
    background: "var(--c-surface)",
    border: "1px solid var(--c-border)",
    borderRadius: "var(--r-lg)",
    boxShadow: "var(--shadow-sm)",
    overflow: "hidden",
    backdropFilter: "blur(14px)",
    ...style,
  }}>
    {(title || actions) && (
      <div style={{
        padding: "16px 20px",
        borderBottom: "1px solid var(--c-border)",
        display: "flex", alignItems: "center", gap: 12,
        background: "linear-gradient(180deg, rgba(255,255,255,0.28), rgba(255,255,255,0))",
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 13, fontWeight: 800, letterSpacing: "-0.03em",
            display: "flex", alignItems: "center", gap: 8,
            color: "var(--c-ink)",
          }}>
            <div style={{ width: 4, height: 18, borderRadius: 4, background: accent, flexShrink: 0, boxShadow: `0 0 16px ${accent}33` }} />
            {title}
          </div>
          {subtitle && (
            <div style={{ fontSize: 11.5, color: "var(--c-ink3)", marginTop: 4, marginLeft: 12 }}>
              {subtitle}
            </div>
          )}
        </div>
        {actions && (
          <div style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
            {actions}
          </div>
        )}
      </div>
    )}
    <div style={noPad ? undefined : { /* content area has no extra pad; children manage their own */ }}>
      {children}
    </div>
  </div>
);

/** Small export button (CSV / XLSX) */
export const XBtn: React.FC<{ onClick?: () => void; children: React.ReactNode }> = ({ onClick, children }) => (
  <button
    onClick={onClick}
    style={{
      padding: "5px 10px", borderRadius: 10,
      border: "1px solid var(--c-border2)",
      background: "rgba(255,255,255,0.55)",
      fontFamily: "var(--mono)", fontSize: 10.5, fontWeight: 500,
      color: "var(--c-ink3)", cursor: "pointer", transition: "all 0.15s",
    }}
    onMouseEnter={(e) => {
      (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--c-green)";
      (e.currentTarget as HTMLButtonElement).style.color = "var(--c-green)";
    }}
    onMouseLeave={(e) => {
      (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--c-border2)";
      (e.currentTarget as HTMLButtonElement).style.color = "var(--c-ink3)";
    }}
  >{children}</button>
);

/** Segmented control */
interface SegProps {
  options: { label: string; value: string }[];
  value: string;
  onChange: (v: string) => void;
}
export const Seg: React.FC<SegProps> = ({ options, value, onChange }) => (
  <div style={{
    display: "flex",
    background: "var(--c-surface2)",
    border: "1px solid var(--c-border2)",
    borderRadius: 999, overflow: "hidden", flexShrink: 0,
    padding: 2,
  }}>
    {options.map((o) => (
      <div
        key={o.value}
        onClick={() => onChange(o.value)}
        style={{
          padding: "6px 12px",
          fontSize: 11, fontWeight: 700,
          color: value === o.value ? "#fff" : "var(--c-ink3)",
          background: value === o.value ? "var(--c-blue)" : "transparent",
          borderRadius: 999,
          cursor: "pointer", transition: "all 0.15s", whiteSpace: "nowrap",
        }}
      >{o.label}</div>
    ))}
  </div>
);
