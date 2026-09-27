<script setup lang="ts">
import { onMounted, ref } from "vue";

import { api, ApiError } from "@/api";
import type { UserSummary } from "@/types";

interface CreatedUser {
  user: UserSummary;
  temporary_password: string;
}

interface TemporaryPassword {
  temporary_password: string;
}

const users = ref<UserSummary[]>([]);
const name = ref("");
const email = ref("");
const resultMessage = ref<string | null>(null);
const error = ref<string | null>(null);

async function load() {
  users.value = await api.get<UserSummary[]>("/admin/users");
}

onMounted(load);

async function createUser() {
  error.value = null;
  try {
    const result = await api.post<CreatedUser>("/admin/users", { name: name.value, email: email.value });
    resultMessage.value = `Compte créé pour ${result.user.name}. Mot de passe temporaire (à communiquer, affiché une seule fois) : ${result.temporary_password}`;
    name.value = "";
    email.value = "";
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function resetPassword(userId: number) {
  error.value = null;
  try {
    const result = await api.post<TemporaryPassword>(`/admin/users/${userId}/reset-password`);
    resultMessage.value = `Nouveau mot de passe temporaire : ${result.temporary_password}`;
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function deactivate(userId: number) {
  error.value = null;
  try {
    await api.patch(`/admin/users/${userId}/deactivate`);
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <div class="card">
    <h1>Administration des comptes</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <form @submit.prevent="createUser">
      <label>Nom<input v-model="name" type="text" required /></label>
      <label>Adresse e-mail<input v-model="email" type="email" required /></label>
      <button type="submit">Créer le compte</button>
    </form>
    <div v-if="resultMessage" class="card"><p>{{ resultMessage }}</p></div>
  </div>
  <div class="card">
    <h2>Comptes existants</h2>
    <ul class="list">
      <li v-for="user in users" :key="user.id" class="row">
        <span>
          {{ user.name }}
          <span v-if="user.is_admin" class="badge">admin</span>
          <span v-if="!user.is_active" class="badge danger">désactivé</span>
        </span>
        <button class="secondary" @click="resetPassword(user.id)">Réinitialiser le mot de passe</button>
        <button v-if="user.is_active && !user.is_admin" class="danger" @click="deactivate(user.id)">
          Désactiver
        </button>
      </li>
    </ul>
  </div>
</template>
