// Утилиты экспорта данных: downloadCsvData (скачивает CSV через blob URL), downloadXlsxData (XLSX через xlsx).
import * as XLSX from "xlsx";

export const downloadCsvData = (filename: string, rows: (string | number)[][]) => {
  const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

export const downloadXlsxData = (filename: string, rows: (string | number)[][], sheetName = "Sheet1") => {
  const ws = XLSX.utils.aoa_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, sheetName);
  XLSX.writeFile(wb, filename);
};
