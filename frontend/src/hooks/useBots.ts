// Хук списка bot-баз данных (GET /api/bots). Упрощённая версия useBotRegistry без CRUD.
import { useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export const useBots = () => {
  const [bots, setBots] = useState<string[]>([]);

  useEffect(() => {
    const fetchBots = async () => {
      try {
        const res = await axios.get(`${API_BASE}/api/bots`);
        setBots(res.data.bots?.map((bot: any) => bot.bot_key) || []);
      } catch (error) {
        console.error(error);
      }
    };
    fetchBots();
  }, []);

  return { bots };
};
