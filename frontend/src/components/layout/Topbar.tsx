// Верхняя панель: пользователь, кнопка logout, статус синхронизации, кнопки admin-действий.
import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import CircularProgress from "@mui/material/CircularProgress";
import RefreshIcon from "@mui/icons-material/Refresh";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";

export interface TopbarProps {
  title: string;
  subtitle?: string;
  breadcrumb?: string;
  /** MSK time string to show next to sync dot, e.g. "23:07:52" */
  liveTime?: string;
  /** Colour of the sync indicator dot */
  liveColor?: "green" | "yellow" | "red";
  darkMode?: boolean;
  onToggleDark?: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
}

const DOT_COLOR: Record<string, string> = {
  green:  "#22c55e",
  yellow: "#f59e0b",
  red:    "#ef4444",
};

export const Topbar: React.FC<TopbarProps> = ({
  title,
  subtitle,
  breadcrumb,
  liveTime,
  liveColor = "red",
  darkMode = false,
  onToggleDark,
  onRefresh,
  refreshing = false,
}) => (
  <Box
    sx={{
      height: 56,
      flexShrink: 0,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      px: 2.5,
      bgcolor: "var(--app-topbar-bg)",
      borderBottom: "1px solid var(--app-shell-border)",
      boxShadow: "var(--app-topbar-shadow)",
      backdropFilter: "blur(18px)",
      position: "sticky",
      top: 0,
      zIndex: 20,
    }}
  >
    {/* Left: page title */}
    <Box sx={{ minWidth: 0 }}>
      {breadcrumb && (
        <Typography sx={{ fontSize: 11, color: "var(--c-ink3)", textTransform: "uppercase", letterSpacing: "0.08em", mb: 0.15 }}>
          {breadcrumb}
        </Typography>
      )}
      <Typography
        sx={{
          fontSize: 14,
          fontWeight: 700,
          color: "var(--c-ink)",
          letterSpacing: "-0.28px",
        }}
      >
        {title}
      </Typography>
      {subtitle && (
        <Typography sx={{ fontSize: 11.5, color: "var(--c-ink2)", mt: 0.15 }}>
          {subtitle}
        </Typography>
      )}
    </Box>

    {/* Right: live indicator + actions */}
    <Stack direction="row" spacing={1} alignItems="center">
      {liveTime && (
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              bgcolor: DOT_COLOR[liveColor] ?? "#94a3b8",
              boxShadow: `0 0 0 2px ${DOT_COLOR[liveColor] ?? "#94a3b8"}33`,
            }}
          />
          <Typography sx={{ fontSize: 12, color: "var(--c-ink2)", fontVariantNumeric: "tabular-nums" }}>
            {liveTime}
          </Typography>
        </Stack>
      )}

      {onRefresh && (
        <Tooltip title="Обновить данные">
          <IconButton size="small" onClick={onRefresh} disabled={refreshing}>
            {refreshing
              ? <CircularProgress size={16} thickness={4} />
              : <RefreshIcon sx={{ fontSize: 18, color: "var(--c-ink2)" }} />
            }
          </IconButton>
        </Tooltip>
      )}

      {onToggleDark && (
        <Tooltip title={darkMode ? "Светлая тема" : "Тёмная тема"}>
          <IconButton size="small" onClick={onToggleDark}>
            {darkMode
              ? <LightModeIcon sx={{ fontSize: 18, color: "#f59e0b" }} />
              : <DarkModeIcon  sx={{ fontSize: 18, color: "var(--c-ink2)" }} />
            }
          </IconButton>
        </Tooltip>
      )}
    </Stack>
  </Box>
);

export default Topbar;
