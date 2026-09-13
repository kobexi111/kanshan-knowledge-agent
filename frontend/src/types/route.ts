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
