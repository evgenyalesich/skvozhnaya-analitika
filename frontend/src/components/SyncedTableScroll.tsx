// Утилита синхронизированной горизонтальной прокрутки двух таблиц (header + body).
import React from "react";
import Box from "@mui/material/Box";

interface SyncedTableScrollProps {
  children: React.ReactNode;
  maxHeight?: string | number;
  topOffset?: number;
}

const SyncedTableScroll: React.FC<SyncedTableScrollProps> = ({
  children,
  maxHeight = "calc(100vh - 320px)",
  topOffset = 0,
}) => {
  const topRef = React.useRef<HTMLDivElement | null>(null);
  const bottomRef = React.useRef<HTMLDivElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);
  const topInnerRef = React.useRef<HTMLDivElement | null>(null);
  const bottomInnerRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    const top = topRef.current;
    const bottom = bottomRef.current;
    const body = bodyRef.current;
    const topInner = topInnerRef.current;
    const bottomInner = bottomInnerRef.current;
    if (!top || !bottom || !body || !topInner || !bottomInner) {
      return;
    }

    let syncingFromTop = false;
    let syncingFromBottom = false;
    let syncingFromBody = false;

    const syncWidths = () => {
      const width = `${body.scrollWidth}px`;
      topInner.style.width = width;
      bottomInner.style.width = width;
      top.scrollLeft = body.scrollLeft;
      bottom.scrollLeft = body.scrollLeft;
    };

    const onTopScroll = () => {
      if (syncingFromBody || syncingFromBottom) {
        syncingFromBody = false;
        syncingFromBottom = false;
        return;
      }
      syncingFromTop = true;
      body.scrollLeft = top.scrollLeft;
      bottom.scrollLeft = top.scrollLeft;
    };

    const onBottomScroll = () => {
      if (syncingFromBody || syncingFromTop) {
        syncingFromBody = false;
        syncingFromTop = false;
        return;
      }
      syncingFromBottom = true;
      body.scrollLeft = bottom.scrollLeft;
      top.scrollLeft = bottom.scrollLeft;
    };

    const onBodyScroll = () => {
      if (syncingFromTop || syncingFromBottom) {
        syncingFromTop = false;
        syncingFromBottom = false;
        return;
      }
      syncingFromBody = true;
      top.scrollLeft = body.scrollLeft;
      bottom.scrollLeft = body.scrollLeft;
    };

    syncWidths();
    top.addEventListener("scroll", onTopScroll, { passive: true });
    bottom.addEventListener("scroll", onBottomScroll, { passive: true });
    body.addEventListener("scroll", onBodyScroll, { passive: true });

    const resizeObserver = new ResizeObserver(syncWidths);
    resizeObserver.observe(body);
    const firstChild = body.firstElementChild;
    if (firstChild instanceof HTMLElement) {
      resizeObserver.observe(firstChild);
    }

    window.addEventListener("resize", syncWidths);

    return () => {
      top.removeEventListener("scroll", onTopScroll);
      bottom.removeEventListener("scroll", onBottomScroll);
      body.removeEventListener("scroll", onBodyScroll);
      resizeObserver.disconnect();
      window.removeEventListener("resize", syncWidths);
    };
  }, []);

  return (
    <Box sx={{ position: "relative" }}>
      <Box
        ref={topRef}
        sx={{
          position: "sticky",
          top: topOffset,
          zIndex: 7,
          overflowX: "auto",
          overflowY: "hidden",
          height: 16,
          backgroundColor: "var(--app-table-head-bg)",
          borderBottom: "1px solid var(--app-table-divider)",
        }}
      >
        <Box ref={topInnerRef} sx={{ height: 1 }} />
      </Box>
      <Box
        ref={bodyRef}
        sx={{
          overflowY: "auto",
          overflowX: "auto",
          maxHeight,
        }}
      >
        {children}
      </Box>
      <Box
        ref={bottomRef}
        sx={{
          position: "sticky",
          bottom: 0,
          zIndex: 7,
          overflowX: "auto",
          overflowY: "hidden",
          height: 16,
          backgroundColor: "var(--app-table-head-bg)",
          borderTop: "1px solid var(--app-table-divider)",
        }}
      >
        <Box ref={bottomInnerRef} sx={{ height: 1 }} />
      </Box>
    </Box>
  );
};

export default SyncedTableScroll;
