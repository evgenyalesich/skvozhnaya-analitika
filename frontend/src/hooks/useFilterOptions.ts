import { useEffect, useState } from "react";
import axios from "axios";
import { buildQueryParams } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export const useFilterOptions = (allDatabases: string[] = [], selectedDatabases: string[] = []) => {
  const [bots, setBots] = useState<string[]>([]);
  const [companies, setCompanies] = useState<string[]>([]);
  const [utmSource, setUtmSource] = useState<string[]>([]);
  const [utmCampaign, setUtmCampaign] = useState<string[]>([]);
  const [utmMedium, setUtmMedium] = useState<string[]>([]);
  const [utmContent, setUtmContent] = useState<string[]>([]);
  const [utmTerm, setUtmTerm] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchOptions = async () => {
      setLoading(true);
      setError(null);
      try {
        const [companiesRes, utmRes] = await Promise.all([
          axios.get(`${API_BASE}/api/advertising-companies`),
          axios.get(`${API_BASE}/api/utm/options`, {
            params: buildQueryParams({ databases: selectedDatabases.length ? selectedDatabases : allDatabases }),
          }),
        ]);
        setBots(allDatabases);
        setCompanies(
          companiesRes.data.advertising_companies
            ?.filter((company: any) => company.is_active)
            .map((company: any) => company.company_name) || []
        );
        setUtmSource(utmRes.data.sources || []);
        setUtmCampaign(utmRes.data.campaigns || []);
        setUtmMedium(utmRes.data.mediums || []);
        setUtmContent(utmRes.data.contents || []);
        setUtmTerm(utmRes.data.terms || []);
      } catch (err: any) {
        console.error(err);
        setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить список фильтров");
      } finally {
        setLoading(false);
      }
    };
    fetchOptions();
  }, [allDatabases.join(","), selectedDatabases.join(",")]);

  return {
    bots,
    companies,
    utmSource,
    utmCampaign,
    utmMedium,
    utmContent,
    utmTerm,
    loading,
    error,
  };
};
