import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface AdvertisingCompanyOption {
  company_id?: string | null;
  company_name: string;
  is_active: boolean;
  bot_keys: string[];
}

export const useAdvertisingCompanies = () => {
  const [companies, setCompanies] = useState<AdvertisingCompanyOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/api/advertising-companies`);
      setCompanies(res.data.advertising_companies || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось получить список РК");
    } finally {
      setLoading(false);
    }
  }, []);

  const upsert = useCallback(
    async (company: AdvertisingCompanyOption) => {
      await axios.post(`${API_BASE}/api/advertising-companies`, {
        company_id: company.company_id || null,
        company_name: company.company_name,
        is_active: company.is_active,
        bot_keys: company.bot_keys || [],
      });
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { companies, loading, error, refresh, upsert };
};
