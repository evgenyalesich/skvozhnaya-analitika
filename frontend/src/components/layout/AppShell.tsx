import React from "react";
import Box from "@mui/material/Box";

export interface AppShellProps {
  sidebar: React.ReactNode;
  topbar: React.ReactNode;
  filterbar?: React.ReactNode;
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ sidebar, topbar, filterbar, children }) => (
  <Box sx={{ display: "flex", height: "100vh", overflow: "hidden" }}>
    {/* Sidebar */}
    {sidebar}

    {/* Right column */}
    <Box sx={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden", minWidth: 0 }}>
      {/* Topbar */}
      {topbar}

      {/* Filter bar (optional) */}
      {filterbar}

      {/* Scrollable content area */}
      <Box sx={{ flex: 1, overflow: "auto", minHeight: 0 }}>
        {children}
      </Box>
    </Box>
  </Box>
);

export default AppShell;
