import React from "react";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";

type TabKey =
  | "overview"
  | "funnel"
  | "totalb"
  | "totala"
  | "totalc"
  | "tgsubs"
  | "weekly"
  | "raw"
  | "rawutm";

export interface OverviewTabsProps {
  value: TabKey;
  onChange: (value: TabKey) => void;
}

const OverviewTabs: React.FC<OverviewTabsProps> = ({ value, onChange }) => (
  <Tabs value={value} onChange={(_, newValue) => onChange(newValue as TabKey)}>
    <Tab label="Overview" value="overview" />
    <Tab label="Funnel" value="funnel" />
    <Tab label="TotalB" value="totalb" />
    <Tab label="TotalA" value="totala" />
    <Tab label="TotalC" value="totalc" />
    <Tab label="TG SUBS" value="tgsubs" />
    <Tab label="Weekly" value="weekly" />
    <Tab label="RAW Users" value="raw" />
    <Tab label="RAW UTM" value="rawutm" />
  </Tabs>
);

export default OverviewTabs;
