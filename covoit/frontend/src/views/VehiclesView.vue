<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { api, ApiError } from "@/api";
import type { Vehicle } from "@/types";

const ENERGY_TYPES = [
  { value: "petrol", label: "Essence" },
  { value: "diesel", label: "Diesel" },
  { value: "ethanol", label: "Éthanol" },
  { value: "electric", label: "Électrique" },
];

const props = defineProps<{ id: string }>();
const groupId = computed(() => Number(props.id));

const mine = ref<Vehicle[]>([]);
const accessible = ref<Vehicle[]>([]);
const brand = ref("");
const model = ref("");
const seats = ref(5);
const energyType = ref(ENERGY_TYPES[0].value);
const consumption = ref(6);
const sharedIds = ref<Set<number>>(new Set());
const error = ref<string | null>(null);

async function load() {
  const [m, a] = await Promise.all([
    api.get<Vehicle[]>("/vehicles/mine"),
    api.get<Vehicle[]>(`/groups/${groupId.value}/vehicles`),
  ]);
  mine.value = m;
  accessible.value = a;
}

onMounted(load);

async function addVehicle() {
  error.value = null;
  try {
    await api.post("/vehicles", {
      brand: brand.value,
      model: model.value,
      seats: seats.value,
      energies: [{ energy_type: energyType.value, consumption_per_100km: consumption.value }],
    });
    brand.value = "";
    model.value = "";
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function share(vehicleId: number) {
  error.value = null;
  try {
    await api.post(`/vehicles/${vehicleId}/share`, { group_id: groupId.value });
    sharedIds.value = new Set(sharedIds.value).add(vehicleId);
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <p><router-link :to="{ name: 'group-detail', params: { id } }">&larr; Retour au groupe</router-link></p>
  <div class="card">
    <h1>Mes véhicules</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <ul class="list">
      <li v-for="vehicle in mine" :key="vehicle.id">
        <strong>{{ vehicle.brand }} {{ vehicle.model }}</strong> — {{ vehicle.seats }} places
        <div class="muted">
          {{ vehicle.energies.map((e) => `${e.energy_type}: ${e.consumption_per_100km}/100km`).join(", ") }}
        </div>
        <button class="secondary" :disabled="sharedIds.has(vehicle.id)" @click="share(vehicle.id)">
          {{ sharedIds.has(vehicle.id) ? "Partagé" : "Partager avec ce groupe" }}
        </button>
      </li>
      <li v-if="!mine.length" class="muted">Aucun véhicule.</li>
    </ul>
  </div>
  <div class="card">
    <h2>Ajouter un véhicule</h2>
    <form @submit.prevent="addVehicle">
      <label>Marque<input v-model="brand" type="text" required /></label>
      <label>Modèle<input v-model="model" type="text" required /></label>
      <label>Nombre de places (conducteur inclus)<input v-model.number="seats" type="number" min="1" required /></label>
      <label
        >Source d'énergie
        <select v-model="energyType">
          <option v-for="energy in ENERGY_TYPES" :key="energy.value" :value="energy.value">{{ energy.label }}</option>
        </select>
      </label>
      <label
        >Consommation moyenne (/100km)<input v-model.number="consumption" type="number" step="0.1" required
      /></label>
      <button type="submit">Ajouter</button>
    </form>
  </div>
  <div class="card">
    <h2>Véhicules disponibles pour mes trajets dans ce groupe</h2>
    <ul class="list">
      <li v-for="vehicle in accessible" :key="vehicle.id">{{ vehicle.brand }} {{ vehicle.model }} ({{ vehicle.seats }} places)</li>
      <li v-if="!accessible.length" class="muted">Aucun.</li>
    </ul>
  </div>
</template>
