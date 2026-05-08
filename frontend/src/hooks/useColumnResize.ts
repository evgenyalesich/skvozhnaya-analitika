// Хук ресайза колонок таблицы с сохранением ширин в localStorage.
// Возвращает getWidth(col)/startResize(col, e) — подключается к mousedown заголовка колонки.
import { useCallback, useRef, useState } from "react";

const loadWidths = (storageKey: string): Record<string, number> => {
  try {
    const stored = localStorage.getItem(storageKey);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed && typeof parsed === "object") return parsed;
    }
  } catch {}
  return {};
};

const saveWidths = (storageKey: string, widths: Record<string, number>) => {
  try {
    localStorage.setItem(storageKey, JSON.stringify(widths));
  } catch {}
};

export function useColumnResize(storageKey: string) {
  const [colWidths, setColWidths] = useState<Record<string, number>>(() => loadWidths(storageKey));
  const resizeRef = useRef<{ key: string; startX: number; startWidth: number } | null>(null);

  const getColWidth = useCallback(
    (colKey: string, defaultWidth: number): number => colWidths[colKey] ?? defaultWidth,
    [colWidths]
  );

  const handleResizeMouseDown = useCallback(
    (e: React.MouseEvent, colKey: string, currentWidth: number) => {
      e.preventDefault();
      e.stopPropagation();
      resizeRef.current = { key: colKey, startX: e.clientX, startWidth: currentWidth };

      const onMouseMove = (ev: MouseEvent) => {
        if (!resizeRef.current) return;
        // Capture values synchronously before setState to avoid null ref inside callback
        const { key, startX, startWidth } = resizeRef.current;
        const delta = ev.clientX - startX;
        const newWidth = Math.max(40, startWidth + delta);
        setColWidths((prev) => ({ ...prev, [key]: newWidth }));
      };

      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        // Capture key before nulling the ref
        const key = resizeRef.current?.key;
        resizeRef.current = null;
        if (key) {
          setColWidths((prev) => {
            saveWidths(storageKey, prev);
            return prev;
          });
        }
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [storageKey]
  );

  const resetColWidths = useCallback(() => {
    setColWidths({});
    saveWidths(storageKey, {});
  }, [storageKey]);

  const hasCustomWidths = Object.keys(colWidths).length > 0;

  return { colWidths, getColWidth, handleResizeMouseDown, resetColWidths, hasCustomWidths };
}
