<script setup lang="ts">
import { onMounted } from "vue";

import { api, UNAUTHORIZED_EVENT } from "@/api";
import { clearSession, currentUser } from "@/composables/session";
import { router } from "@/router";

function handleUnauthorized() {
  clearSession();
  router.push({ name: "login" });
}

onMounted(() => {
  window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
});

async function logout() {
  await api.post("/auth/logout");
  clearSession();
  await router.push({ name: "login" });
}
</script>

<template>
  <header class="topbar">
    <router-link class="brand" to="/groups">Covoit</router-link>
    <nav v-if="currentUser" class="topnav">
      <span class="muted">{{ currentUser.name }}</span>
      <router-link to="/groups">Groupes</router-link>
      <router-link v-if="currentUser.is_admin" to="/admin">Administration</router-link>
      <button class="secondary" @click="logout">Se déconnecter</button>
    </nav>
  </header>
  <main class="app">
    <router-view />
  </main>
</template>
