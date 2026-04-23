import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

interface EmptyStateProps {
  title: string;
  description?: string;
  compact?: boolean;
}

const EmptyState: React.FC<EmptyStateProps> = ({ title, description, compact = false }) => (
  <Box
    sx={{
      px: compact ? 2 : 3,
      py: compact ? 3 : 5,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      textAlign: "center",
      gap: 1,
      color: "var(--c-ink2)",
    }}
  >
    <Box
      sx={{
        width: compact ? 42 : 54,
        height: compact ? 42 : 54,
        borderRadius: "16px",
        background:
          "linear-gradient(135deg, color-mix(in srgb, var(--c-blue) 16%, transparent), color-mix(in srgb, var(--c-green) 12%, transparent))",
        border: "1px solid var(--app-shell-border)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.24)",
      }}
    />
    <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "var(--c-ink)" }}>
      {title}
    </Typography>
    {description && (
      <Typography variant="body2" sx={{ maxWidth: 420, color: "var(--c-ink2)" }}>
        {description}
      </Typography>
    )}
  </Box>
);

export default EmptyState;
