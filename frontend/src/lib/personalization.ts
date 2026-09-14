import type { RouteStageName } from "@/types/route";

export interface BrowsingItem {
  url: string;
  title: string;
  topic: string;
  reason: string;
  stage: RouteStageName | "source";
  viewedAt: number;
  visits: number;
}

export interface RecommendationItem {
  url: string;
  title: string;
  topic: string;
  reason: string;
  stage: RouteStageName;
  addedAt: number;
}

export interface PersonalizationData {
  history: BrowsingItem[];
  candidates: RecommendationItem[];
}

const emptyData = (): PersonalizationData => ({ history: [], candidates: [] });

function storageKey(profileId: string) {
  return `kanshan-personalization-v2:${profileId}`;
}

export function loadPersonalization(profileId: string): PersonalizationData {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey(profileId)) ?? "null") as Partial<PersonalizationData> | null;
    return {
      history: Array.isArray(parsed?.history) ? parsed.history.slice(0, 50) : [],
      candidates: Array.isArray(parsed?.candidates) ? parsed.candidates.slice(0, 120) : [],
    };
  } catch {
    return emptyData();
  }
}

function save(profileId: string, data: PersonalizationData) {
  localStorage.setItem(storageKey(profileId), JSON.stringify(data));
}

export function recordView(profileId: string, item: Omit<BrowsingItem, "viewedAt" | "visits">) {
  const data = loadPersonalization(profileId);
  const old = data.history.find((entry) => entry.url === item.url);
  data.history = [
    { ...item, viewedAt: Date.now(), visits: (old?.visits ?? 0) + 1 },
    ...data.history.filter((entry) => entry.url !== item.url),
  ].slice(0, 50);
  save(profileId, data);
  return data;
}

export function rememberRecommendations(
  profileId: string,
  items: Array<Omit<RecommendationItem, "addedAt">>,
) {
  const data = loadPersonalization(profileId);
  const additions = items.map((item) => ({ ...item, addedAt: Date.now() }));
  const urls = new Set(additions.map((item) => item.url));
  data.candidates = [...additions, ...data.candidates.filter((item) => !urls.has(item.url))].slice(0, 120);
  save(profileId, data);
  return data;
}

export function recommendations(data: PersonalizationData) {
  const viewed = new Set(data.history.map((item) => item.url));
  const interests = data.history.flatMap((item) => `${item.title} ${item.topic}`.toLowerCase().split(/\s+|[，。、《》：:；;（）()]/).filter((word) => word.length > 1));
  return data.candidates
    .filter((item) => !viewed.has(item.url))
    .map((item) => ({
      ...item,
      score: interests.reduce((score, word) => score + (`${item.title} ${item.topic}`.toLowerCase().includes(word) ? 2 : 0), 0) + item.addedAt / 1e13,
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 6);
}
