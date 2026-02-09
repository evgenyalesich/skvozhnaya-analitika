import React, { useEffect, useState } from "react";
import Container from "@mui/material/Container";
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
import OverviewPage from "./pages/OverviewPage";
import { useTelegramAuth } from "./hooks/useTelegramAuth";

const App: React.FC = () => {
  const {
    isAuthenticated,
    startToken,
    loginUrl,
    loading,
    error,
    startLogin,
    pollStatus,
    resetLogin,
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
    <Container maxWidth="xl">
      <Box my={3}>
        <OverviewPage />
      </Box>
    </Container>
  );
};

export default App;
