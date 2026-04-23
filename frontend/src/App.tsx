import React, { useEffect, useMemo, useState } from "react";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Stack from "@mui/material/Stack";
import CircularProgress from "@mui/material/CircularProgress";
import TelegramIcon from "@mui/icons-material/Telegram";
import OverviewPage from "./components/layout/OverviewPage";
import { useTelegramAuth } from "./hooks/useTelegramAuth";

const App: React.FC = () => {
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    const saved = window.localStorage.getItem("analytics-dark-mode");
    if (saved !== null) {
      return saved === "true";
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? false;
  });

  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? "dark" : "light";
    document.documentElement.style.colorScheme = darkMode ? "dark" : "light";
    window.localStorage.setItem("analytics-dark-mode", String(darkMode));
  }, [darkMode]);

  const muiTheme = useMemo(
    () =>
      createTheme({
        shape: {
          borderRadius: 16,
        },
        palette: {
          mode: darkMode ? "dark" : "light",
          primary: { main: darkMode ? "#6ea8ff" : "#2563eb" },
          secondary: { main: darkMode ? "#7dd3fc" : "#0f766e" },
          background: {
            default: darkMode ? "#09111d" : "#f3f6fb",
            paper: darkMode ? "rgba(15, 23, 38, 0.9)" : "rgba(255, 255, 255, 0.9)",
          },
          text: {
            primary: darkMode ? "#eef4ff" : "#122033",
            secondary: darkMode ? "#9fb0c8" : "#5f7089",
          },
          divider: darkMode ? "rgba(148, 163, 184, 0.18)" : "rgba(15, 23, 42, 0.1)",
        },
        typography: {
          fontFamily: '"Plus Jakarta Sans", "Inter", system-ui, sans-serif',
          button: {
            textTransform: "none",
            fontWeight: 700,
          },
        },
        components: {
          MuiPaper: {
            styleOverrides: {
              root: {
                backgroundImage: "none",
                backdropFilter: darkMode ? "blur(14px)" : "none",
              },
            },
          },
          MuiDialog: {
            defaultProps: {
              BackdropProps: {
                sx: {
                  backgroundColor: darkMode ? "rgba(2, 6, 23, 0.52)" : "rgba(15, 23, 42, 0.12)",
                  backdropFilter: darkMode ? "blur(2px)" : "none",
                },
              },
            },
          },
          MuiButton: {
            styleOverrides: {
              root: {
                borderRadius: 12,
              },
              contained: {
                boxShadow: darkMode
                  ? "0 14px 30px rgba(37, 99, 235, 0.28)"
                  : "0 14px 30px rgba(37, 99, 235, 0.18)",
              },
            },
          },
          MuiTableCell: {
            styleOverrides: {
              root: {
                borderColor: darkMode ? "rgba(148, 163, 184, 0.14)" : "rgba(15, 23, 42, 0.08)",
              },
            },
          },
          MuiChip: {
            styleOverrides: {
              root: {
                fontWeight: 700,
              },
            },
          },
          MuiOutlinedInput: {
            styleOverrides: {
              root: {
                borderRadius: 14,
              },
            },
          },
        },
      }),
    [darkMode]
  );

  const {
    isAuthenticated,
    currentUserId,
    currentUsername,
    startToken,
    loginUrl,
    loading,
    authChecking,
    error,
    startLogin,
    pollStatus,
    resetLogin,
    logout,
  } = useTelegramAuth();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (!startToken) return;
    setPolling(true);
    const timer = window.setInterval(async () => {
      const res = await pollStatus();
      if (res?.status === "ok") {
        setPolling(false);
        setDialogOpen(false);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pollStatus, startToken]);

  const handleOpenLogin = async () => {
    const res = await startLogin();
    if (res) {
      setDialogOpen(true);
    }
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    resetLogin();
    setPolling(false);
  };

  if (authChecking) {
    return (
      <Box
        sx={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(180deg, #0f1017 0%, #171a26 100%)",
          color: "#fff",
        }}
      >
        <Stack spacing={2} alignItems="center">
          <CircularProgress color="inherit" size={28} />
          <Typography variant="body2" color="rgba(255,255,255,0.72)">
            Проверяем сессию...
          </Typography>
        </Stack>
      </Box>
    );
  }

  if (!isAuthenticated) {
    return (
      <Box
        sx={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(180deg, #0f1017 0%, #171a26 100%)",
          color: "#fff",
        }}
      >
        <Stack spacing={3} alignItems="center">
          <Button
            variant="contained"
            startIcon={<TelegramIcon />}
            onClick={handleOpenLogin}
            sx={{
              px: 4,
              py: 1.2,
              borderRadius: 2,
              background: "linear-gradient(90deg, #1c5cff 0%, #3f7bff 100%)",
            }}
          >
            Войти
          </Button>
          {error && (
            <Typography variant="body2" color="error">
              {error}
            </Typography>
          )}
        </Stack>

        <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
          <DialogTitle>Перейти в телеграм-бота</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <Typography variant="body1">
                После нажатия кнопки вы перейдёте в диалог с нашим ботом @pokerhub_robot.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                В диалоге с ботом нажмите кнопку «Авторизоваться» для входа или «Отмена», если это не вы.
              </Typography>
              {polling && (
                <Stack direction="row" spacing={1} alignItems="center">
                  <CircularProgress size={18} />
                  <Typography variant="body2">Ожидаем подтверждение...</Typography>
                </Stack>
              )}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleCloseDialog}>Отмена</Button>
            <Button
              variant="contained"
              startIcon={<TelegramIcon />}
              onClick={() => loginUrl && window.open(loginUrl, "_blank")}
              disabled={!loginUrl || loading}
            >
              Перейти в Telegram
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
    );
  }

  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Box sx={{ height: "100vh", overflow: "hidden" }}>
        <OverviewPage
          userId={currentUserId}
          currentUsername={currentUsername}
          onLogout={logout}
          darkMode={darkMode}
          onToggleDark={() => setDarkMode((d) => !d)}
        />
      </Box>
    </ThemeProvider>
  );
};

export default App;
