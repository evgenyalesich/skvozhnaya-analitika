import { useEffect, useState } from "react";
import axios from "axios";

const API_BASE = "http://localhost:8000";

export interface FunnelTotal {
  total_users: number;
  total_budget: number;
  cac: number | null;
}

export interface FunnelDailyPoint {
  date: string;
  users: number;
  budget?: number;
  cac?: number;
}

export const useReports = () => {
  const [total, setTotal] = useState<FunnelTotal | null>(null);
  const [daily, setDaily] = useState<FunnelDailyPoint[]>([]);
  const [breakdown, setBreakdown] = useState<any[]>([]);
  const [raw, setRaw] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const totalRes = await axios.get(`${API_BASE}/api/reports/funnel-start/total`);
      const dailyRes = await axios.get(`${API_BASE}/api/reports/funnel-start/daily`);
      const breakdownRes = await axios.get(`${API_BASE}/api/reports/funnel-start/breakdown`);
      const rawRes = await axios.get(`${API_BASE}/api/reports/funnel-start/raw`);
      setTotal(totalRes.data);
      setDaily(dailyRes.data.data || []);
      setBreakdown(breakdownRes.data.breakdown || []);
      setRaw(rawRes.data.users || []);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  return { total, daily, breakdown, raw, loading, refresh: fetchReports };
};
