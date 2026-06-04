import { apiRequest } from "./client";
import { endpoints } from "./endpoints";
import { mockKogbucks } from "./mock";
import type { Kogbucks } from "./types";

export async function getMe(): Promise<Kogbucks> {
  return apiRequest<Kogbucks>({
    path: endpoints.kogbucks,
    mock: () => mockKogbucks()
  });
}

