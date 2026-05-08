// Skeleton-заглушка для таблицы пока данные загружаются.
import React from "react";
import Box from "@mui/material/Box";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";

interface TableSkeletonProps {
  columns?: number;
  rows?: number;
}

const TableSkeleton: React.FC<TableSkeletonProps> = ({ columns = 7, rows = 6 }) => (
  <Box sx={{ px: 1.5, py: 1 }}>
    <Stack spacing={1}>
      <Stack direction="row" spacing={1}>
        {Array.from({ length: columns }).map((_, index) => (
          <Skeleton
            key={`head-${index}`}
            variant="rounded"
            height={24}
            sx={{ flex: index === 0 ? 1.6 : 1, borderRadius: "10px" }}
          />
        ))}
      </Stack>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <Stack key={`row-${rowIndex}`} direction="row" spacing={1}>
          {Array.from({ length: columns }).map((__, colIndex) => (
            <Skeleton
              key={`${rowIndex}-${colIndex}`}
              variant="rounded"
              height={32}
              sx={{ flex: colIndex === 0 ? 1.6 : 1, borderRadius: "12px" }}
            />
          ))}
        </Stack>
      ))}
    </Stack>
  </Box>
);

export default TableSkeleton;
