<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { api, ApiError } from "@/api";
import { currentUser } from "@/composables/session";
import type { Trip, TripParticipation, TripSegment, UserSummary } from "@/types";

const STATUS_LABELS: Record<Trip["status"], string> = {
  planned: "prévu",
  completed: "effectué",
  cancelled: "annulé",
};

const props = defineProps<{ id: string }>();
const tripId = computed(() => Number(props.id));

const trip = ref<Trip | null>(null);
const segments = ref<TripSegment[]>([]);
const participations = ref<TripParticipation[]>([]);
const names = ref<Record<number, string>>({});
const selectedStatus = ref<Trip["status"]>("planned");
const boardingPoint = ref("");
const error = ref<string | null>(null);

// Le garde de navigation garantit que currentUser est chargé avant le montage de cette vue.
const isDriver = computed(() => !!trip.value && currentUser.value!.id === trip.value.driver_id);
const myParticipation = computed(
  () => participations.value.find((p) => p.user_id === currentUser.value!.id) ?? null
);

async function nameOf(userId: number): Promise<void> {
  const user = await api.get<UserSummary>(`/users/${userId}`);
  names.value = { ...names.value, [userId]: user.name };
}

async function load() {
  const [t, s, p] = await Promise.all([
    api.get<Trip>(`/trips/${tripId.value}`),
    api.get<TripSegment[]>(`/trips/${tripId.value}/segments`),
    api.get<TripParticipation[]>(`/trips/${tripId.value}/participations`),
  ]);
  trip.value = t;
  segments.value = s;
  participations.value = p;
  selectedStatus.value = t.status;
  await Promise.all(p.map((participation) => nameOf(participation.user_id)));
}

onMounted(load);

async function updateStatus() {
  error.value = null;
  try {
    trip.value = await api.post<Trip>(`/trips/${tripId.value}/status`, { status: selectedStatus.value });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function requestSeat() {
  error.value = null;
  try {
    await api.post(`/trips/${tripId.value}/participation-requests`, {
      boarding_point: boardingPoint.value || null,
    });
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function decide(participationId: number, approve: boolean) {
  error.value = null;
  try {
    await api.post(`/trips/${tripId.value}/participation-requests/${participationId}/decision`, {
      approve,
    });
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <div v-if="trip">
    <p><router-link :to="{ name: 'group-trips', params: { id: String(trip.group_id) } }">&larr; Retour aux trajets</router-link></p>
    <div class="card">
      <h1>{{ trip.origin }} → {{ trip.destination }}</h1>
      <p class="muted">{{ trip.date }} à {{ trip.time_of_day }} — <span class="badge">{{ STATUS_LABELS[trip.status] }}</span></p>
      <div v-if="error" class="error">{{ error }}</div>
      <form class="row" @submit.prevent="updateStatus">
        <select v-model="selectedStatus">
          <option value="planned">prévu</option>
          <option value="completed">effectué</option>
          <option value="cancelled">annulé</option>
        </select>
        <button type="submit">Mettre à jour le statut</button>
      </form>
    </div>

    <div class="card">
      <h2>Participants</h2>
      <ul class="list">
        <li v-for="participation in participations" :key="participation.id" class="row">
          <span>
            {{ names[participation.user_id] }} — {{ participation.role === "driver" ? "conducteur" : "passager" }}
            <span class="badge">{{ participation.status }}</span>
          </span>
          <template v-if="isDriver && (participation.status === 'pending' || participation.status === 'waitlisted')">
            <button class="secondary" @click="decide(participation.id, true)">Accepter</button>
            <button class="danger" @click="decide(participation.id, false)">Refuser</button>
          </template>
        </li>
      </ul>
      <form v-if="!myParticipation" class="row" @submit.prevent="requestSeat">
        <label>Point de montée (optionnel)<input v-model="boardingPoint" type="text" /></label>
        <button type="submit">Demander une place</button>
      </form>
    </div>

    <div class="card">
      <h2>Tronçons</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Distance</th>
            <th>Détour</th>
            <th>Occupants</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="segment in segments" :key="segment.id">
            <td>{{ segment.sequence }}</td>
            <td>{{ segment.distance_km }} km</td>
            <td>{{ segment.is_detour ? "oui" : "—" }}</td>
            <td>{{ segment.occupant_ids.length }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted">Le détail fin des tronçons/détours et les corrections post-clôture se gèrent via l'API (v1).</p>
    </div>
  </div>
</template>
