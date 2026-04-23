import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const AUTH_HINT_KEY = "roistat_auth_hint";
const AUTH_USER_ID_KEY = "roistat_user_id";
const AUTH_USERNAME_KEY = "roistat_username";
const AUTH_RETRY_DELAYS_MS = [0, 400, 1200];

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
  const [authToken, setAuthToken] = useState<string | null>(() =>
    window.sessionStorage.getItem(AUTH_HINT_KEY) ? "cookie" : null
  );
  const [startToken, setStartToken] = useState<string | null>(null);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authChecking, setAuthChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentUserId, setCurrentUserId] = useState<number | null>(() => {
    const stored = window.sessionStorage.getItem(AUTH_USER_ID_KEY);
    return stored ? Number(stored) : null;
  });
  const [currentUsername, setCurrentUsername] = useState<string | null>(() =>
    window.sessionStorage.getItem(AUTH_USERNAME_KEY)
  );

  const isAuthenticated = useMemo(() => Boolean(authToken), [authToken]);

  useEffect(() => {
    const checkSession = async () => {
      for (const delayMs of AUTH_RETRY_DELAYS_MS) {
        if (delayMs > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, delayMs));
        }
        try {
          const meRes = await axios.get(`${API_BASE}/api/auth/me`);
          const userId = meRes.data?.user?.tg_user_id;
          const username = meRes.data?.user?.username ?? null;
          if (userId) {
            setCurrentUserId(userId);
            window.sessionStorage.setItem(AUTH_USER_ID_KEY, String(userId));
          }
          if (username) {
            setCurrentUsername(username);
            window.sessionStorage.setItem(AUTH_USERNAME_KEY, username);
          }
          window.sessionStorage.setItem(AUTH_HINT_KEY, "1");
          setAuthToken("cookie");
          setAuthChecking(false);
          return;
        } catch {
          continue;
        }
      }
      window.sessionStorage.removeItem(AUTH_HINT_KEY);
      setAuthToken(null);
      setAuthChecking(false);
    };
    checkSession();
  }, []);

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
      if (res.data.status === "ok") {
        window.sessionStorage.setItem(AUTH_HINT_KEY, "1");
        if (res.data.tg_user_id) {
          setCurrentUserId(res.data.tg_user_id);
          window.sessionStorage.setItem(AUTH_USER_ID_KEY, String(res.data.tg_user_id));
        }
        if (res.data.username) {
          setCurrentUsername(res.data.username);
          window.sessionStorage.setItem(AUTH_USERNAME_KEY, res.data.username);
        }
        setAuthToken("cookie");
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
    axios.post(`${API_BASE}/api/auth/logout`).catch(() => null).finally(() => {
      window.sessionStorage.removeItem(AUTH_HINT_KEY);
      window.sessionStorage.removeItem(AUTH_USER_ID_KEY);
      window.sessionStorage.removeItem(AUTH_USERNAME_KEY);
      setAuthToken(null);
      setCurrentUserId(null);
      setCurrentUsername(null);
    });
  }, []);

  return {
    authToken,
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
  };
};
