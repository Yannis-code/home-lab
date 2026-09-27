import { ref } from "vue";

import { api, setToken } from "@/api";
import type { Me } from "@/types";

export const currentUser = ref<Me | null>(null);

// N'est appelée que par le garde de navigation, qui a déjà vérifié qu'un
// jeton est présent (isLoggedIn()) avant tout appel.
export async function refreshCurrentUser(): Promise<void> {
  try {
    currentUser.value = await api.get<Me>("/users/me");
  } catch {
    currentUser.value = null;
  }
}

export function clearSession(): void {
  setToken(null);
  currentUser.value = null;
}
