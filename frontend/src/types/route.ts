export interface LearningMaterial {
  title: string;
  reason: string;
  url: string | null;
  is_mock: boolean;
}

export interface RouteStep {
  title: string;
  description: string;
  difficulty: "入门" | "基础" | "进阶";
  materials: LearningMaterial[];
}

export interface LearningRouteResponse {
  source: {
    url: string;
    title: string;
    summary: string;
    content_type: "mock" | "zhihu";
  };
  route: {
    prerequisite: RouteStep[];
    current: RouteStep[];
    advanced: RouteStep[];
  };
  notice: string;
}

export type RouteStageName = "prerequisite" | "current" | "advanced";

export type RouteStreamEvent =
  | { type: "progress"; stage: RouteStageName; status: "running" }
  | {
      type: "source";
      source: LearningRouteResponse["source"];
      notice: string;
    }
  | { type: "stage"; stage: RouteStageName; steps: RouteStep[] }
  | {
      type: "recommendations";
      items: Array<{
        url: string;
        title: string;
        topic: string;
        reason: string;
        stage: Exclude<RouteStageName, "current"> | "related";
      }>;
    }
  | { type: "complete" }
  | { type: "error"; message: string };
