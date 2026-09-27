<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { api, ApiError } from "@/api";
import type { Group, Membership, Trip, UserSummary, Vehicle } from "@/types";

const STATUS_LABELS: Record<Trip["status"], string> = {
  planned: "prévu",
  completed: "effectué",
  cancelled: "annulé",
};

const props = defineProps<{ id: string }>();
const groupId = computed(() => Number(props.id));

const group = ref<Group | null>(null);
const members = ref<Membership[]>([]);
const memberNames = ref<Record<number, string>>({});
const trips = ref<Trip[]>([]);
const vehicles = ref<Vehicle[]>([]);
const error = ref<string | null>(null);

const date = ref("");
const timeOfDay = ref("08:00");
const origin = ref("");
const destination = ref("");
const driverId = ref(0);
const vehicleId = ref<number | null>(null);
const passengerIds = ref<Set<number>>(new Set());
const distanceKm = ref<number | null>(null);

const activeMembers = computed(() => members.value.filter((m) => m.status === "active"));
const sortedTrips = computed(() => [...trips.value].sort((a, b) => (a.date < b.date ? 1 : -1)));

async function nameOf(userId: number): Promise<void> {
  const user = await api.get<UserSummary>(`/users/${userId}`);
  memberNames.value = { ...memberNames.value, [userId]: user.name };
}

async function loadVehiclesForDriver(): Promise<void> {
  vehicles.value = await api.get<Vehicle[]>(`/groups/${groupId.value}/vehicles`, {
    driver_id: driverId.value,
  });
}

async function load() {
  const [g, m, t] = await Promise.all([
    api.get<Group>(`/groups/${groupId.value}`),
    api.get<Membership[]>(`/groups/${groupId.value}/members`),
    api.get<Trip[]>(`/groups/${groupId.value}/trips`),
  ]);
  group.value = g;
  members.value = m;
  trips.value = t;
  await Promise.all(activeMembers.value.map((member) => nameOf(member.user_id)));
  driverId.value = group.value.default_driver_id ?? activeMembers.value[0].user_id;
  await loadVehiclesForDriver();
}

onMounted(load);

function togglePassenger(userId: number) {
  const next = new Set(passengerIds.value);
  if (next.has(userId)) next.delete(userId);
  else next.add(userId);
  passengerIds.value = next;
}

async function createTrip() {
  error.value = null;
  try {
    const passengers = [...passengerIds.value].filter((userId) => userId !== driverId.value);
    await api.post(`/groups/${groupId.value}/trips`, {
      date: date.value,
      time_of_day: timeOfDay.value,
      origin: origin.value,
      destination: destination.value,
      driver_id: driverId.value,
      vehicle_id: vehicleId.value,
      passenger_ids: passengers,
      segments: [{ distance_km: distanceKm.value, occupant_ids: [driverId.value, ...passengers] }],
    });
    origin.value = "";
    destination.value = "";
    distanceKm.value = null;
    passengerIds.value = new Set();
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <p><router-link :to="{ name: 'group-detail', params: { id } }">&larr; Retour au groupe</router-link></p>
  <div class="card">
    <h1>Trajets</h1>
    <ul class="list">
      <li v-for="trip in sortedTrips" :key="trip.id">
        <router-link :to="{ name: 'trip-detail', params: { id: String(trip.id) } }">
          {{ trip.date }} {{ trip.time_of_day }} — {{ trip.origin }} → {{ trip.destination }}
        </router-link>
        <span class="badge">{{ STATUS_LABELS[trip.status] }}</span>
      </li>
      <li v-if="!sortedTrips.length" class="muted">Aucun trajet.</li>
    </ul>
  </div>
  <div v-if="group && !group.is_archived" class="card">
    <h2>Créer un trajet ponctuel</h2>
    <div v-if="error" class="error">{{ error }}</div>
    <form @submit.prevent="createTrip">
      <label>Date<input v-model="date" type="date" required /></label>
      <label>Heure<input v-model="timeOfDay" type="time" required /></label>
      <label>Départ<input v-model="origin" type="text" required /></label>
      <label>Destination<input v-model="destination" type="text" required /></label>
      <label
        >Conducteur
        <select v-model.number="driverId" @change="loadVehiclesForDriver">
          <option v-for="member in activeMembers" :key="member.user_id" :value="member.user_id">
            {{ memberNames[member.user_id] }}
          </option>
        </select>
      </label>
      <label
        >Véhicule
        <select v-model.number="vehicleId">
          <option :value="null">— aucun —</option>
          <option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">
            {{ vehicle.brand }} {{ vehicle.model }} ({{ vehicle.seats }} places)
          </option>
        </select>
      </label>
      <fieldset>
        <legend>Passagers</legend>
        <label v-for="member in activeMembers" :key="member.user_id" class="checkbox-row">
          <input
            type="checkbox"
            :checked="passengerIds.has(member.user_id)"
            @change="togglePassenger(member.user_id)"
          />
          {{ memberNames[member.user_id] }}
        </label>
      </fieldset>
      <label>Distance totale du trajet (km)<input v-model.number="distanceKm" type="number" step="0.1" required /></label>
      <p class="muted">
        Le conducteur et les passagers cochés sont tous considérés à bord sur l'ensemble du trajet (un seul
        tronçon). Les tronçons détaillés et détours sont modifiables via l'API.
      </p>
      <button type="submit">Créer</button>
    </form>
  </div>
</template>
