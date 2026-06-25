import { apiFetch } from "./client";
import type { StatsOverview, TopQuestion } from "../types";

export const fetchStats = () =>
  apiFetch<StatsOverview>("/api/stats/overview");

export const fetchHotQuestions = (limit = 10, days = 7) =>
  apiFetch<TopQuestion[]>(
    `/api/stats/top-questions?limit=${limit}&days=${days}`,
  );
