<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import { api, ApiError } from "@/api";

const router = useRouter();
const currentPassword = ref("");
const newPassword = ref("");
const error = ref<string | null>(null);

async function submit() {
  error.value = null;
  try {
    await api.post("/auth/change-password", {
      current_password: currentPassword.value,
      new_password: newPassword.value,
    });
    await router.push({ name: "groups" });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <div class="card">
    <h1>Changer le mot de passe</h1>
    <p class="muted">Un nouveau mot de passe est requis avant de continuer.</p>
    <div v-if="error" class="error">{{ error }}</div>
    <form @submit.prevent="submit">
      <label>Mot de passe actuel<input v-model="currentPassword" type="password" required /></label>
      <label>Nouveau mot de passe<input v-model="newPassword" type="password" minlength="8" required /></label>
      <button type="submit">Valider</button>
    </form>
  </div>
</template>
