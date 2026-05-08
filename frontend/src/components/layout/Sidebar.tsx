// Боковая панель навигации: иконки вкладок с Tooltip-подписями, сворачивается до иконок.
import React, { useState } from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import DashboardIcon from "@mui/icons-material/Dashboard";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import AssessmentIcon from "@mui/icons-material/Assessment";
import TelegramIcon from "@mui/icons-material/Telegram";
import SchoolIcon from "@mui/icons-material/School";
import TableChartIcon from "@mui/icons-material/TableChart";
import SearchIcon from "@mui/icons-material/Search";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import SettingsIcon from "@mui/icons-material/Settings";
import TuneIcon from "@mui/icons-material/Tune";
import BusinessIcon from "@mui/icons-material/Business";
import AccountBalanceWalletIcon from "@mui/icons-material/AccountBalanceWallet";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import PeopleIcon from "@mui/icons-material/People";
import LockIcon from "@mui/icons-material/Lock";
import RefreshIcon from "@mui/icons-material/Refresh";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

type TabKey = "overview" | "totalb" | "main" | "tgsubs" | "lessons" | "raw" | "usersearch" | "faq";

interface NavItem {
  key: TabKey;
  label: string;
  icon: React.ReactElement;
}

interface AdminActions {
  onBots:      () => void;
  onCompanies: () => void;
  onBudgets:   () => void;
  onAdMetrics: () => void;
  onAccess:    () => void;
  onEmployees: () => void;
  onSettings:  () => void;
  onRefresh:   () => void;
  refreshing?: boolean;
}

export interface SidebarProps {
  tab: TabKey;
  onTabChange: (tab: TabKey) => void;
  admin: AdminActions;
}

const NAV_ITEMS: NavItem[] = [
  { key: "overview",   label: "Overview",        icon: <DashboardIcon   fontSize="small" /> },
  { key: "totalb",     label: "BOTs",            icon: <SmartToyIcon    fontSize="small" /> },
  { key: "main",       label: "Основной отчёт",  icon: <AssessmentIcon  fontSize="small" /> },
  { key: "tgsubs",     label: "TG SUBS",         icon: <TelegramIcon    fontSize="small" /> },
  { key: "lessons",    label: "PokerHub",         icon: <SchoolIcon      fontSize="small" /> },
  { key: "raw",        label: "RAW Users",        icon: <TableChartIcon  fontSize="small" /> },
  { key: "usersearch", label: "Поиск",            icon: <SearchIcon      fontSize="small" /> },
  { key: "faq",        label: "FAQ",              icon: <HelpOutlineIcon fontSize="small" /> },
];

interface AdminItem {
  label: string;
  icon: React.ReactElement;
  onClick: () => void;
  loading?: boolean;
}

const COLLAPSED_W = 56;
const EXPANDED_W  = 220;

const BG = "var(--app-sidebar-bg)";
const TEXT_MU = "var(--app-sidebar-text)";
const TEXT_ACT = "var(--app-sidebar-text-active)";
const ACT_BG = "var(--app-sidebar-active-bg)";
const ACT_BORDER = "var(--app-sidebar-accent)";
const HOVER_BG = "var(--app-sidebar-hover-bg)";

/* ── shared row ── */
const Row: React.FC<{
  icon: React.ReactElement;
  label: string;
  active?: boolean;
  collapsed: boolean;
  onClick: () => void;
  loading?: boolean;
}> = ({ icon, label, active = false, collapsed, onClick, loading }) => {
  const [hovered, setHovered] = useState(false);

  const inner = (
    <Box
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: collapsed ? 0 : "10px",
        px: collapsed ? 0 : "12px",
        py: "8px",
        mx: "6px",
        borderRadius: "14px",
        cursor: "pointer",
        position: "relative",
        justifyContent: collapsed ? "center" : "flex-start",
        color: active ? TEXT_ACT : TEXT_MU,
        bgcolor: active ? ACT_BG : hovered ? HOVER_BG : "transparent",
        transition: "background 0.15s, color 0.15s",
        userSelect: "none",
        "&::before": active ? {
          content: '""',
          position: "absolute",
          left: "-6px",
          top: "50%",
          transform: "translateY(-50%)",
          width: "3px",
          height: "22px",
          bgcolor: ACT_BORDER,
          borderRadius: "0 3px 3px 0",
        } : {},
      }}
    >
      <Box sx={{
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        color: active ? ACT_BORDER : hovered ? TEXT_ACT : TEXT_MU,
        transition: "color 0.15s",
      }}>
        {loading ? <CircularProgress size={16} sx={{ color: TEXT_MU }} /> : icon}
      </Box>
      {!collapsed && (
        <Box component="span" sx={{ fontSize: "13px", fontWeight: active ? 600 : 400, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {label}
        </Box>
      )}
    </Box>
  );

  return collapsed
    ? <Tooltip title={label} placement="right" arrow>{inner}</Tooltip>
    : inner;
};

export const Sidebar: React.FC<SidebarProps> = ({ tab, onTabChange, admin }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const w = collapsed ? COLLAPSED_W : EXPANDED_W;

  const adminItems: AdminItem[] = [
    { label: "Обновить базы",    icon: <RefreshIcon     fontSize="small" />, onClick: admin.onRefresh,   loading: admin.refreshing },
    { label: "Настроить базы",   icon: <TuneIcon        fontSize="small" />, onClick: admin.onBots },
    { label: "Настроить РК",     icon: <BusinessIcon    fontSize="small" />, onClick: admin.onCompanies },
    { label: "Бюджеты",          icon: <AccountBalanceWalletIcon fontSize="small" />, onClick: admin.onBudgets },
    { label: "Рекл. метрики",    icon: <ShowChartIcon   fontSize="small" />, onClick: admin.onAdMetrics },
    { label: "Доступы",          icon: <LockIcon        fontSize="small" />, onClick: admin.onAccess },
    { label: "Сотрудники",       icon: <PeopleIcon      fontSize="small" />, onClick: admin.onEmployees },
    { label: "Настройки обновл.", icon: <SettingsIcon   fontSize="small" />, onClick: admin.onSettings },
  ];

  return (
    <Box sx={{
      width: `${w}px`,
      minWidth: `${w}px`,
      height: "100vh",
      bgcolor: BG,
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
      borderRight: "1px solid rgba(255,255,255,0.07)",
      boxShadow: "inset -1px 0 0 var(--app-sidebar-border)",
      transition: "width 0.22s ease, min-width 0.22s ease",
      overflow: "hidden",
      zIndex: 50,
    }}>
      {/* Brand */}
      <Box sx={{
        height: 48, display: "flex", alignItems: "center",
        justifyContent: collapsed ? "center" : "flex-start",
        px: collapsed ? 0 : "16px", gap: "10px",
        borderBottom: "1px solid var(--app-sidebar-border)", flexShrink: 0,
      }}>
        <Box sx={{
          width: 30, height: 30, borderRadius: "10px",
          background: "linear-gradient(135deg, #2563eb 0%, #14b8a6 100%)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "13px", fontWeight: 800, color: "#fff", flexShrink: 0,
        }}>A</Box>
        {!collapsed && (
          <Box component="span" sx={{ fontSize: "14px", fontWeight: 700, color: TEXT_ACT, letterSpacing: "-0.3px", whiteSpace: "nowrap" }}>
            Analytics
          </Box>
        )}
      </Box>

      {/* Nav */}
      <Box sx={{ flex: 1, overflowY: "auto", overflowX: "hidden", py: "8px" }}>
        {NAV_ITEMS.map((item) => (
          <Row
            key={item.key}
            icon={item.icon}
            label={item.label}
            active={tab === item.key}
            collapsed={collapsed}
            onClick={() => onTabChange(item.key)}
          />
        ))}
      </Box>

      {/* Admin section */}
      <Box sx={{ borderTop: "1px solid var(--app-sidebar-border)", flexShrink: 0 }}>
        {/* Toggle admin section */}
        <Row
          icon={<SettingsIcon fontSize="small" />}
          label="Управление"
          collapsed={collapsed}
          onClick={() => setAdminOpen((v) => !v)}
          active={adminOpen}
        />

        {/* Admin items — only when expanded sidebar AND admin open */}
        {!collapsed && adminOpen && (
          <Box sx={{ pb: "4px" }}>
            <Divider sx={{ borderColor: "var(--app-sidebar-border)", mx: 1, my: 0.5 }} />
            {adminItems.map((item) => (
              <Row
                key={item.label}
                icon={item.icon}
                label={item.label}
                collapsed={false}
                onClick={item.onClick}
                loading={item.loading}
              />
            ))}
          </Box>
        )}

        {/* When collapsed — individual tooltips for admin items */}
        {collapsed && adminOpen && adminItems.map((item) => (
          <Row
            key={item.label}
            icon={item.icon}
            label={item.label}
            collapsed={true}
            onClick={item.onClick}
            loading={item.loading}
          />
        ))}

        {/* Collapse toggle */}
        <Box sx={{ display: "flex", justifyContent: collapsed ? "center" : "flex-end", px: collapsed ? 0 : "10px", pb: "6px", pt: "2px" }}>
          <Tooltip title={collapsed ? "Развернуть" : "Свернуть"} placement="right" arrow>
            <IconButton size="small" onClick={() => setCollapsed((v) => !v)} sx={{ color: TEXT_MU, "&:hover": { color: TEXT_ACT, bgcolor: HOVER_BG } }}>
              {collapsed ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>
    </Box>
  );
};

export default Sidebar;
