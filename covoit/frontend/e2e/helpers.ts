import type { Page } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8000";

export const ADMIN_EMAIL = "admin@covoit.home";
export const ADMIN_PASSWORD = "AdminPass123!";

interface RequestOptions {
  method?: string;
  token?: string;
  body?: unknown;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function request(path: string, options: RequestOptions = {}): Promise<any> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`${options.method ?? "GET"} ${path} -> ${response.status}: ${await response.text()}`);
  }
  if (response.status === 204) return undefined;
  return response.json();
}

export async function login(email: string, password: string): Promise<string> {
  const result = await request("/auth/login", { method: "POST", body: { email, password } });
  return result.token as string;
}

export async function adminToken(): Promise<string> {
  return login(ADMIN_EMAIL, ADMIN_PASSWORD);
}

export interface TestUser {
  id: number;
  name: string;
  email: string;
  token: string;
  temporaryPassword: string;
}

export async function createUser(adminTok: string, name: string): Promise<TestUser> {
  const unique = crypto.randomUUID().slice(0, 6);
  const displayName = `${name}-${unique}`;
  const email = `${name.toLowerCase()}.${unique}@covoit.home`;
  const created = await request("/admin/users", {
    method: "POST",
    token: adminTok,
    body: { name: displayName, email },
  });
  const temporaryPassword = created.temporary_password as string;
  const token = await login(email, temporaryPassword);
  return { id: created.user.id as number, name: displayName, email, token, temporaryPassword };
}

export async function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string
): Promise<void> {
  await request("/auth/change-password", {
    method: "POST",
    token,
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export async function createGroup(token: string, name: string): Promise<{ id: number; name: string }> {
  return request("/groups", { method: "POST", token, body: { name } });
}

export async function inviteAndJoin(managerToken: string, groupId: number, invitee: TestUser): Promise<void> {
  const membership = await request(`/groups/${groupId}/invitations`, {
    method: "POST",
    token: managerToken,
    body: { user_id: invitee.id },
  });
  await request(`/groups/${groupId}/invitations/${membership.id}/accept`, {
    method: "POST",
    token: invitee.token,
  });
}

export async function transferManagement(token: string, groupId: number, newManagerId: number): Promise<void> {
  await request(`/groups/${groupId}/transfer-management`, {
    method: "POST",
    token,
    body: { new_manager_id: newManagerId },
  });
}

export async function leaveGroup(token: string, groupId: number): Promise<void> {
  await request(`/groups/${groupId}/leave`, { method: "POST", token });
}

interface EnergyInput {
  energy_type: string;
  consumption_per_100km: number;
}

export async function createVehicle(
  token: string,
  payload: { brand: string; model: string; seats: number; energies: EnergyInput[] }
): Promise<{ id: number }> {
  return request("/vehicles", { method: "POST", token, body: payload });
}

export async function shareVehicle(token: string, vehicleId: number, groupId: number): Promise<void> {
  await request(`/vehicles/${vehicleId}/share`, { method: "POST", token, body: { group_id: groupId } });
}

interface TripSegmentInput {
  distance_km: number;
  occupant_ids: number[];
  is_detour?: boolean;
  detour_for_id?: number;
}

export async function createTrip(
  token: string,
  groupId: number,
  payload: {
    date: string;
    time_of_day: string;
    origin: string;
    destination: string;
    driver_id: number;
    vehicle_id: number | null;
    passenger_ids: number[];
    segments: TripSegmentInput[];
  }
): Promise<{ id: number }> {
  return request(`/groups/${groupId}/trips`, { method: "POST", token, body: payload });
}

export async function setTripStatus(token: string, tripId: number, status: string): Promise<void> {
  await request(`/trips/${tripId}/status`, { method: "POST", token, body: { status } });
}

export async function createRecurringModel(
  token: string,
  groupId: number,
  payload: { name: string; origin: string; destination: string; weekdays: number[]; time_of_day: string }
): Promise<{ id: number }> {
  return request(`/groups/${groupId}/recurring-models`, { method: "POST", token, body: payload });
}

export async function addRecurringParticipant(
  token: string,
  modelId: number,
  userId: number
): Promise<{ id: number }> {
  return request(`/recurring-models/${modelId}/participants`, {
    method: "POST",
    token,
    body: { user_id: userId },
  });
}

export async function setMonthlyPrice(
  token: string,
  vehicleId: number,
  energyType: string,
  year: number,
  month: number,
  price: number
): Promise<void> {
  await request(`/vehicles/${vehicleId}/monthly-prices`, {
    method: "POST",
    token,
    body: { energy_type: energyType, year, month, price_per_unit: price },
  });
}

export async function seedToken(page: Page, token: string): Promise<void> {
  await page.addInitScript((value) => {
    window.localStorage.setItem("covoit_token", value);
  }, token);
}

// Naviguer vers une URL qui ne diffère que par le fragment #hash ne force pas
// un rechargement complet de page (comportement standard des navigateurs), ce
// qui empêcherait un jeton injecté via seedToken() de prendre effet lors d'un
// changement d'identité en cours de test. Le paramètre de requête garantit un
// vrai rechargement à chaque navigation.
export async function gotoHash(page: Page, hash: string): Promise<void> {
  await page.goto(`/?_r=${Date.now()}${hash}`);
}

export function today(): { date: string; year: number; month: number } {
  const now = new Date();
  const date = now.toISOString().slice(0, 10);
  return { date, year: now.getFullYear(), month: now.getMonth() + 1 };
}
