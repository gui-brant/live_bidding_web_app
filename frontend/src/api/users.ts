import { apiRequest } from "./client";

type CreateUserPayload = {
  name: string;
  email: string;
  role: "rep" | "admin";
  balance_amount: number;
  balance_committed: boolean;
  has_bid: boolean;
};

type CreateUserResponse = {
  id: string;
  name: string;
  email: string;
  role: "rep" | "admin";
  balance_amount: number;
  balance_committed: boolean;
  has_bid: boolean;
};

export async function createUser(payload: CreateUserPayload): Promise<CreateUserResponse> {
  return apiRequest<CreateUserResponse>({
    path: "/users",
    options: { method: "POST", body: payload },
    mock: () => ({
      id: "mock-user",
      ...payload
    })
  });
}
