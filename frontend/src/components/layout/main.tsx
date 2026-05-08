// Точка входа layout-слоя: монтирует App с ThemeProvider и авторизацией.
import React from "react";
import ReactDOM from "react-dom/client";
import axios from "axios";
import CssBaseline from "@mui/material/CssBaseline";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import App from "./App";
import "./styles/global.css";

axios.defaults.withCredentials = true;

const theme = createTheme({
  palette: {
    mode: "light",
    primary:   { main: "#2F6FED" },
    success:   { main: "#12A672" },
    warning:   { main: "#D4820A" },
    error:     { main: "#E0403A" },
    background:{ default: "#F4F5F7", paper: "#FFFFFF" },
    text:      { primary: "#0D0F12", secondary: "#5A6174" },
  },
  typography: {
    fontFamily: "'Plus Jakarta Sans', 'Inter', system-ui, sans-serif",
    fontSize: 13,
  },
  shape: { borderRadius: 8 },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 600, fontSize: 12 },
        sizeSmall: { padding: "5px 12px" },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
      },
    },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
