// Кнопки экспорта (CSV/Excel) — переиспользуемый UI-компонент.
import React from "react";
import Button from "@mui/material/Button";
import ButtonGroup from "@mui/material/ButtonGroup";
import DownloadIcon from "@mui/icons-material/Download";
import { downloadCsvData, downloadXlsxData } from "../utils/exportUtils";

interface ExportButtonsProps {
  getData: () => (string | number)[][];
  baseName: string;
  sheetName?: string;
  disabled?: boolean;
  size?: "small" | "medium";
}

const ExportButtons: React.FC<ExportButtonsProps> = ({
  getData,
  baseName,
  sheetName = "Sheet1",
  disabled = false,
  size = "small",
}) => {
  const handleCsv = () => {
    const data = getData();
    if (!data.length) return;
    downloadCsvData(`${baseName}.csv`, data);
  };
  const handleXlsx = () => {
    const data = getData();
    if (!data.length) return;
    downloadXlsxData(`${baseName}.xlsx`, data, sheetName);
  };

  return (
    <ButtonGroup size={size} variant="outlined" disabled={disabled}>
      <Button startIcon={<DownloadIcon />} onClick={handleCsv}>
        CSV
      </Button>
      <Button onClick={handleXlsx}>XLSX</Button>
    </ButtonGroup>
  );
};

export default ExportButtons;
