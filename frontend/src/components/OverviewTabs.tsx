import React from "react";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";

type TabKey = "overview" | "conversions" | "details" | "raw";

export interface OverviewTabsProps {
  value: TabKey;
  onChange: (value: TabKey) => void;
}

const OverviewTabs: React.FC<OverviewTabsProps> = ({ value, onChange }) => (
  <Tabs value={value} onChange={(_, newValue) => onChange(newValue as TabKey)}>
    <Tab label="Overview" value="overview" />
    <Tab label="Conversions" value="conversions" />
    <Tab label="Details Raw" value="details" />
    <Tab label="RAW Users" value="raw" />
  </Tabs>
);

export default OverviewTabs;
