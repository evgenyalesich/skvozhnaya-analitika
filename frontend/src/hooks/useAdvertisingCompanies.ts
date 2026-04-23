import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface UtmRule {
  bot_keys?: string[];
  utm_source?: string | null;
  utm_campaign?: string | null;
  utm_medium?: string | null;
  utm_content?: string | null;
  utm_term?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  priority?: number;
  match_mode?: string | null;
}

export interface AdvertisingCompanyOption {
  company_id?: string | null;
  company_name: string;
  platform?: string | null;
  is_active: boolean;
  bot_keys: string[];
  utm_rules: UtmRule[];
}

export const useAdvertisingCompanies = () => {
  const [companies, setCompanies] = useState<AdvertisingCompanyOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toPayload = (company: AdvertisingCompanyOption) => ({
    company_id: company.company_id || null,
    company_name: company.company_name,
    platform: company.platform || null,
    is_active: company.is_active,
    bot_keys: company.bot_keys || [],
    utm_rules: company.utm_rules || [],
  });

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
      await axios.post(`${API_BASE}/api/advertising-companies`, toPayload(company));
      await refresh();
    },
    [refresh]
  );

  const saveAll = useCallback(
    async (nextCompanies: AdvertisingCompanyOption[]) => {
      try {
        await axios.post(`${API_BASE}/api/advertising-companies/bulk`, nextCompanies.map(toPayload), {
          timeout: 120000,
        });
      } catch (err: any) {
        const status = err?.response?.status;
        // Fallback for older backend without /bulk.
        if (status === 404 || status === 405 || status === 501) {
          for (const company of nextCompanies) {
            await axios.post(`${API_BASE}/api/advertising-companies`, toPayload(company), {
              timeout: 60000,
            });
          }
        } else {
          throw err;
        }
      }
      await refresh();
    },
    [refresh]
  );

  const remove = useCallback(
    async (companyId: string) => {
      await axios.delete(`${API_BASE}/api/advertising-companies/${companyId}`);
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { companies, loading, error, refresh, upsert, saveAll, remove };
};
