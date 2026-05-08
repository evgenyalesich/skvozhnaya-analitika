// Навигационные вкладки дашборда: overview / totalb / main / tgsubs / lessons / raw / usersearch / faq.
import React from "react";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";

type TabKey =
  | "overview"
  | "totalb"
  | "main"
  | "tgsubs"
  | "lessons"
  | "raw"
  | "usersearch"
  | "faq";

export interface OverviewTabsProps {
  value: TabKey;
  onChange: (value: TabKey) => void;
}

const OverviewTabs: React.FC<OverviewTabsProps> = ({ value, onChange }) => (
  <Tabs value={value} onChange={(_, newValue) => onChange(newValue as TabKey)}>
    <Tab label="Overview" value="overview" />
    <Tab label="BOTs" value="totalb" sx={{ textTransform: "none", fontWeight: 700 }} />
    <Tab label="Основной отчёт" value="main" sx={{ textTransform: "none", fontWeight: 700 }} />
    <Tab label="TG SUBS" value="tgsubs" />
    <Tab label="PokerHub Lessons" value="lessons" />
    <Tab label="RAW Users" value="raw" />
    <Tab label="Поиск" value="usersearch" />
    <Tab label="FAQ" value="faq" />
  </Tabs>
);

export default OverviewTabs;
