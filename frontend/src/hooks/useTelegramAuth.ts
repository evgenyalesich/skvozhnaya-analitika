import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const STORAGE_KEY = "auth_token";

export interface TelegramStartResponse {
  start_token: string;
  login_url: string;
}

export interface TelegramStatusResponse {
  status: "pending" | "ok" | "denied";
  access_token?: string;
  tg_user_id?: number;
  username?: string | null;
  error?: string;
}

export const useTelegramAuth = () => {
  const [authToken, setAuthToken] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY)
  );
  const [startToken, setStartToken] = useState<string | null>(null);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAuthenticated = useMemo(() => Boolean(authToken), [authToken]);

  useEffect(() => {
    if (authToken) {
      axios.defaults.headers.common.Authorization = `Bearer ${authToken}`;
    } else {
      delete axios.defaults.headers.common.Authorization;
    }
  }, [authToken]);

  const startLogin = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.post<TelegramStartResponse>(
        `${API_BASE}/api/auth/telegram/start`
      );
      setStartToken(res.data.start_token);
      setLoginUrl(res.data.login_url);
      return res.data;
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось начать вход");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const pollStatus = useCallback(async () => {
    if (!startToken) return null;
    try {
      const res = await axios.get<TelegramStatusResponse>(
        `${API_BASE}/api/auth/telegram/status`,
        { params: { token: startToken } }
      );
      if (res.data.status === "denied") {
        setError("Авторизация отклонена в Telegram");
        setStartToken(null);
        setLoginUrl(null);
        return res.data;
      }
      if (res.data.status === "ok" && res.data.access_token) {
        localStorage.setItem(STORAGE_KEY, res.data.access_token);
        setAuthToken(res.data.access_token);
      }
      return res.data;
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Ошибка статуса входа");
      return null;
    }
  }, [startToken]);

  const resetLogin = useCallback(() => {
    setStartToken(null);
    setLoginUrl(null);
    setError(null);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setAuthToken(null);
  }, []);

  return {
    authToken,
    isAuthenticated,
    startToken,
    loginUrl,
    loading,
    error,
    startLogin,
    pollStatus,
    resetLogin,
    logout,
  };
};
