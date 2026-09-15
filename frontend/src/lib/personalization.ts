import type { RouteStageName } from "@/types/route";

export interface BrowsingItem {
  url: string;
  title: string;
  topic: string;
  reason: string;
  stage: RouteStageName | "source" | "related";
  viewedAt: number;
  visits: number;
}

export interface RecommendationItem {
  url: string;
  title: string;
  topic: string;
  reason: string;
  stage: RouteStageName | "related";
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

function fragments(value: string) {
  const normalized = value.toLowerCase().replace(/\s+/g, "");
  const parts = new Set<string>();
  normalized
    .split(/[，。、《》：:；;（）()\[\]【】·!?！？—\-_]/)
    .filter((part) => part.length >= 2)
    .forEach((part) => parts.add(part));
  for (let index = 0; index < normalized.length - 1; index += 1) {
    parts.add(normalized.slice(index, index + 2));
  }
  return [...parts];
}

function seededRandom(value: string, seed: number) {
  let hash = seed | 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  }
  return ((hash >>> 0) % 10000) / 10000;
}

export function recommendations(data: PersonalizationData, seed = 1) {
  const historySignals = data.history.map((item, index) => ({
    terms: fragments(`${item.title} ${item.topic}`),
    weight: Math.max(1, 4 - index * 0.08) + Math.min(item.visits, 4) * 0.35,
  }));

  return data.candidates
    .map((item) => {
      const candidateText = `${item.title} ${item.topic}`.toLowerCase();
      const interestScore = historySignals.reduce(
        (total, signal) => total + signal.terms.reduce(
          (score, term) => score + (candidateText.includes(term) ? signal.weight : 0),
          0,
        ),
        0,
      );
      return {
        ...item,
        score:
          interestScore
          + seededRandom(item.url, seed) * 8
          + item.addedAt / 1e13,
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 6);
}
