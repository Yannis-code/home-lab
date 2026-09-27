<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { api, ApiError } from "@/api";
import type { RecurringModel } from "@/types";

const WEEKDAY_LABELS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

const props = defineProps<{ id: string }>();
const groupId = computed(() => Number(props.id));

const models = ref<RecurringModel[]>([]);
const name = ref("");
const origin = ref("");
const destination = ref("");
const timeOfDay = ref("08:00");
const weekdays = ref<Set<number>>(new Set());
const message = ref<string | null>(null);
const error = ref<string | null>(null);

async function load() {
  models.value = await api.get<RecurringModel[]>(`/groups/${groupId.value}/recurring-models`);
}

onMounted(load);

function toggleWeekday(day: number) {
  const next = new Set(weekdays.value);
  if (next.has(day)) next.delete(day);
  else next.add(day);
  weekdays.value = next;
}

async function createModel() {
  error.value = null;
  try {
    await api.post(`/groups/${groupId.value}/recurring-models`, {
      name: name.value,
      origin: origin.value,
      destination: destination.value,
      time_of_day: timeOfDay.value,
      weekdays: [...weekdays.value],
    });
    name.value = "";
    origin.value = "";
    destination.value = "";
    weekdays.value = new Set();
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function pause(modelId: number) {
  await api.post(`/recurring-models/${modelId}/pause`);
  await load();
}

async function resume(modelId: number) {
  await api.post(`/recurring-models/${modelId}/resume`);
  await load();
}

async function remove(modelId: number) {
  await api.del(`/recurring-models/${modelId}`);
  await load();
}

async function generate(modelId: number) {
  error.value = null;
  message.value = null;
  try {
    const created = await api.post<unknown[]>(`/recurring-models/${modelId}/generate-occurrences`, {
      horizon_days: 60,
    });
    message.value = `${created.length} occurrence(s) générée(s).`;
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <p><router-link :to="{ name: 'group-detail', params: { id } }">&larr; Retour au groupe</router-link></p>
  <div class="card">
    <h1>Trajets récurrents</h1>
    <ul class="list">
      <li v-for="model in models" :key="model.id">
        <strong>{{ model.name }}</strong> — {{ model.origin }} → {{ model.destination }} à {{ model.time_of_day }}
        <div class="muted">
          {{ model.weekdays.map((d) => WEEKDAY_LABELS[d]).join(", ") }}
          <span v-if="model.is_paused" class="badge warn">en pause</span>
        </div>
        <div class="row">
          <button v-if="model.is_paused" class="secondary" @click="resume(model.id)">Reprendre</button>
          <button v-else class="secondary" @click="pause(model.id)">Mettre en pause</button>
          <button class="secondary" @click="generate(model.id)">Générer les occurrences</button>
          <button class="danger" @click="remove(model.id)">Supprimer</button>
        </div>
      </li>
      <li v-if="!models.length" class="muted">Aucun modèle récurrent.</li>
    </ul>
  </div>
  <div class="card">
    <h2>Créer un modèle récurrent</h2>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="message" class="card"><p>{{ message }}</p></div>
    <form @submit.prevent="createModel">
      <label>Nom<input v-model="name" type="text" required placeholder="Matin" /></label>
      <label>Départ<input v-model="origin" type="text" required /></label>
      <label>Destination<input v-model="destination" type="text" required /></label>
      <label>Heure<input v-model="timeOfDay" type="time" required /></label>
      <fieldset class="weekday-picker">
        <legend>Jours de la semaine</legend>
        <label v-for="(label, day) in WEEKDAY_LABELS" :key="day">
          <input type="checkbox" :checked="weekdays.has(day)" @change="toggleWeekday(day)" />{{ label }}
        </label>
      </fieldset>
      <button type="submit">Créer</button>
    </form>
  </div>
</template>
