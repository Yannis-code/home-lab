<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { api, ApiError } from "@/api";
import type { Group, Invitation, RecurringParticipationSummary } from "@/types";

const router = useRouter();
const groups = ref<Group[]>([]);
const invitations = ref<Invitation[]>([]);
const recurringInvitations = ref<RecurringParticipationSummary[]>([]);
const name = ref("");
const error = ref<string | null>(null);

async function load() {
  const [g, inv, rec] = await Promise.all([
    api.get<Group[]>("/groups"),
    api.get<Invitation[]>("/users/me/invitations"),
    api.get<RecurringParticipationSummary[]>("/users/me/recurring-participations"),
  ]);
  groups.value = g;
  invitations.value = inv;
  recurringInvitations.value = rec;
}

onMounted(load);

async function createGroup() {
  error.value = null;
  try {
    const group = await api.post<Group>("/groups", { name: name.value });
    await router.push({ name: "group-detail", params: { id: String(group.id) } });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function acceptInvitation(invitation: Invitation) {
  await api.post(`/groups/${invitation.group_id}/invitations/${invitation.id}/accept`);
  await load();
}

async function declineInvitation(invitation: Invitation) {
  await api.post(`/groups/${invitation.group_id}/invitations/${invitation.id}/decline`);
  await load();
}

async function acceptRecurring(participation: RecurringParticipationSummary) {
  await api.post(
    `/recurring-models/${participation.recurring_model_id}/participants/${participation.id}/accept`
  );
  await load();
}
</script>

<template>
  <div v-if="invitations.length" class="card">
    <h2>Invitations en attente</h2>
    <ul class="list">
      <li v-for="invitation in invitations" :key="invitation.id" class="row">
        <span>{{ invitation.group_name }}</span>
        <button class="secondary" @click="acceptInvitation(invitation)">Accepter</button>
        <button class="danger" @click="declineInvitation(invitation)">Refuser</button>
      </li>
    </ul>
  </div>
  <div v-if="recurringInvitations.length" class="card">
    <h2>Trajets récurrents proposés</h2>
    <ul class="list">
      <li v-for="participation in recurringInvitations" :key="participation.id" class="row">
        <span>{{ participation.model_name }}</span>
        <button class="secondary" @click="acceptRecurring(participation)">Accepter</button>
      </li>
    </ul>
  </div>
  <div class="card">
    <h1>Mes groupes</h1>
    <ul class="list">
      <li v-for="group in groups" :key="group.id">
        <router-link :to="{ name: 'group-detail', params: { id: String(group.id) } }">{{ group.name }}</router-link>
        <span v-if="group.is_archived" class="badge">archivé</span>
      </li>
      <li v-if="!groups.length" class="muted">Aucun groupe pour le moment.</li>
    </ul>
  </div>
  <div class="card">
    <h2>Créer un groupe</h2>
    <div v-if="error" class="error">{{ error }}</div>
    <form @submit.prevent="createGroup">
      <label>Nom du groupe<input v-model="name" type="text" required /></label>
      <button type="submit">Créer</button>
    </form>
  </div>
</template>
