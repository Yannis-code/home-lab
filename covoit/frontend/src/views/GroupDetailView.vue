<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { api, ApiError } from "@/api";
import { currentUser } from "@/composables/session";
import type { Group, Membership, UserSummary } from "@/types";

const props = defineProps<{ id: string }>();
const groupId = computed(() => Number(props.id));
const router = useRouter();

const group = ref<Group | null>(null);
const members = ref<Membership[]>([]);
const memberNames = ref<Record<number, string>>({});
const driverSelection = ref<number>(0);
const managerSelection = ref<number>(0);
const searchQuery = ref("");
const searchResults = ref<UserSummary[]>([]);
const invitedIds = ref<Set<number>>(new Set());
const error = ref<string | null>(null);

const activeMembers = computed(() => members.value.filter((m) => m.status === "active"));
// Le garde de navigation garantit que currentUser est chargé avant le montage de cette vue.
const isManager = computed(() => !!group.value && currentUser.value!.id === group.value.manager_id);

async function nameOf(userId: number): Promise<void> {
  const user = await api.get<UserSummary>(`/users/${userId}`);
  memberNames.value = { ...memberNames.value, [userId]: user.name };
}

async function load() {
  const [g, m] = await Promise.all([
    api.get<Group>(`/groups/${groupId.value}`),
    api.get<Membership[]>(`/groups/${groupId.value}/members`),
  ]);
  group.value = g;
  members.value = m;
  await Promise.all(activeMembers.value.map((member) => nameOf(member.user_id)));
  driverSelection.value = activeMembers.value[0].user_id;
  managerSelection.value = activeMembers.value[0].user_id;
}

onMounted(load);

async function changeDefaultDriver() {
  error.value = null;
  try {
    group.value = await api.post<Group>(`/groups/${groupId.value}/default-driver`, {
      user_id: driverSelection.value,
    });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function transferManagement() {
  error.value = null;
  try {
    group.value = await api.post<Group>(`/groups/${groupId.value}/transfer-management`, {
      new_manager_id: managerSelection.value,
    });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function search() {
  searchResults.value = await api.get<UserSummary[]>("/users", { query: searchQuery.value });
}

async function invite(user: UserSummary) {
  error.value = null;
  try {
    await api.post(`/groups/${groupId.value}/invitations`, { user_id: user.id });
    invitedIds.value = new Set(invitedIds.value).add(user.id);
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function archive() {
  error.value = null;
  try {
    group.value = await api.post<Group>(`/groups/${groupId.value}/archive`);
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function leave() {
  error.value = null;
  try {
    await api.post(`/groups/${groupId.value}/leave`);
    await router.push({ name: "groups" });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <div v-if="group" class="card">
    <h1>{{ group.name }} <span v-if="group.is_archived" class="badge">archivé</span></h1>
    <p class="muted">Gestionnaire : {{ memberNames[group.manager_id] }}</p>
    <p class="muted">
      Conducteur par défaut :
      {{ group.default_driver_id ? memberNames[group.default_driver_id] : "aucun" }}
    </p>
    <div class="row">
      <router-link :to="{ name: 'group-vehicles', params: { id } }"><button class="secondary">Véhicules</button></router-link>
      <router-link :to="{ name: 'group-trips', params: { id } }"><button class="secondary">Trajets</button></router-link>
      <router-link :to="{ name: 'group-recurring', params: { id } }"
        ><button class="secondary">Trajets récurrents</button></router-link
      >
      <router-link :to="{ name: 'group-ledger', params: { id } }"><button class="secondary">Bilan mensuel</button></router-link>
    </div>
  </div>

  <div v-if="group" class="card">
    <h2>Membres</h2>
    <ul class="list">
      <li v-for="member in activeMembers" :key="member.id">
        {{ memberNames[member.user_id] }}
        <span v-if="member.user_id === group.manager_id" class="badge">gestionnaire</span>
        <span v-if="member.user_id === group.default_driver_id" class="badge ok">conducteur par défaut</span>
      </li>
    </ul>
  </div>

  <div v-if="group && !group.is_archived" class="card">
    <h2>Actions</h2>
    <div v-if="error" class="error">{{ error }}</div>
    <form class="row" @submit.prevent="changeDefaultDriver">
      <label
        >Conducteur par défaut
        <select v-model.number="driverSelection">
          <option v-for="member in activeMembers" :key="member.user_id" :value="member.user_id">
            {{ memberNames[member.user_id] }}
          </option>
        </select>
      </label>
      <button type="submit">Changer</button>
    </form>

    <template v-if="isManager">
      <form class="row" @submit.prevent="transferManagement">
        <label
          >Transférer la gestion à
          <select v-model.number="managerSelection">
            <option v-for="member in activeMembers" :key="member.user_id" :value="member.user_id">
              {{ memberNames[member.user_id] }}
            </option>
          </select>
        </label>
        <button type="submit">Transférer</button>
      </form>
      <form class="row" @submit.prevent="search">
        <label>Inviter un utilisateur (recherche par nom)<input v-model="searchQuery" type="text" placeholder="alice" /></label>
        <button type="submit">Rechercher</button>
      </form>
      <ul v-if="searchResults.length" class="list">
        <li v-for="user in searchResults" :key="user.id" class="row">
          <span>{{ user.name }}</span>
          <button class="secondary" :disabled="invitedIds.has(user.id)" @click="invite(user)">
            {{ invitedIds.has(user.id) ? "Invité" : "Inviter" }}
          </button>
        </li>
      </ul>
      <button class="danger" @click="archive">Archiver le groupe</button>
    </template>
    <button class="danger" @click="leave">Quitter le groupe</button>
  </div>
</template>
