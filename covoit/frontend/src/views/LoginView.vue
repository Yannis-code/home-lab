<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import { api, ApiError, setToken } from "@/api";

interface LoginResult {
  token: string;
  must_change_password: boolean;
}

const router = useRouter();
const email = ref("");
const password = ref("");
const error = ref<string | null>(null);

async function submit() {
  error.value = null;
  try {
    const result = await api.post<LoginResult>("/auth/login", {
      email: email.value,
      password: password.value,
    });
    setToken(result.token);
    await router.push({ name: result.must_change_password ? "change-password" : "groups" });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <div class="card">
    <h1>Connexion</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <form @submit.prevent="submit">
      <label
        >Adresse e-mail
        <input v-model="email" type="email" required autocomplete="username" />
      </label>
      <label
        >Mot de passe
        <input v-model="password" type="password" required autocomplete="current-password" />
      </label>
      <button type="submit">Se connecter</button>
    </form>
  </div>
</template>
