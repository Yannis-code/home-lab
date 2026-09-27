<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "@/api";
import type { Ledger, Membership, Reimbursement, UserSummary } from "@/types";

function money(value: string | number): string {
  return Number(value).toFixed(2) + " €";
}

const props = defineProps<{ id: string }>();
const groupId = computed(() => Number(props.id));
const route = useRoute();
const router = useRouter();

const now = new Date();
const year = ref(Number(route.query.year) || now.getFullYear());
const month = ref(Number(route.query.month) || now.getMonth() + 1);

const ledger = ref<Ledger | null>(null);
const members = ref<Membership[]>([]);
const names = ref<Record<number, string>>({});
const reimbursements = ref<Reimbursement[]>([]);
const payeeId = ref(0);
const amount = ref<number | null>(null);
const error = ref<string | null>(null);

const activeMembers = computed(() => members.value.filter((m) => m.status === "active"));
const balanceEntries = computed(() => Object.entries(ledger.value?.balances ?? {}));
const transfers = computed(() => ledger.value?.transfers ?? []);
const exportUrl = computed(
  () => `/groups/${groupId.value}/ledger/export?year=${year.value}&month=${month.value}`
);

async function nameOf(userId: number): Promise<void> {
  const user = await api.get<UserSummary>(`/users/${userId}`);
  names.value = { ...names.value, [userId]: user.name };
}

async function load() {
  const [l, m, r] = await Promise.all([
    api.get<Ledger>(`/groups/${groupId.value}/ledger`, { year: year.value, month: month.value }),
    api.get<Membership[]>(`/groups/${groupId.value}/members`),
    api.get<Reimbursement[]>(`/groups/${groupId.value}/reimbursements`, {
      year: year.value,
      month: month.value,
    }),
  ]);
  ledger.value = l;
  members.value = m;
  reimbursements.value = r;
  payeeId.value = activeMembers.value[0].user_id;

  const ids = new Set<number>([
    ...Object.keys(l.balances).map(Number),
    ...l.transfers.flatMap((t) => [t.debtor_id, t.creditor_id]),
    ...r.map((x) => x.payer_id),
    ...r.map((x) => x.payee_id),
    ...activeMembers.value.map((x) => x.user_id),
  ]);
  await Promise.all([...ids].map((id) => nameOf(id)));
}

onMounted(load);

async function applyPeriod() {
  await router.replace({ query: { year: String(year.value), month: String(month.value) } });
  await load();
}

async function validate() {
  error.value = null;
  try {
    ledger.value = await api.post<Ledger>(`/groups/${groupId.value}/ledger/validate`, {
      year: year.value,
      month: month.value,
    });
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function declareReimbursement() {
  error.value = null;
  try {
    await api.post(`/groups/${groupId.value}/reimbursements`, {
      payee_id: payeeId.value,
      amount: amount.value,
      year: year.value,
      month: month.value,
    });
    amount.value = null;
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}

async function confirmReimbursement(reimbursementId: number) {
  error.value = null;
  try {
    await api.post(`/reimbursements/${reimbursementId}/confirm`);
    await load();
  } catch (err) {
    error.value = (err as ApiError).message;
  }
}
</script>

<template>
  <p><router-link :to="{ name: 'group-detail', params: { id } }">&larr; Retour au groupe</router-link></p>
  <div class="card">
    <h1>Bilan de {{ String(month).padStart(2, "0") }}/{{ year }}</h1>
    <form class="row" @submit.prevent="applyPeriod">
      <label>Année<input v-model.number="year" type="number" /></label>
      <label>Mois<input v-model.number="month" type="number" min="1" max="12" /></label>
      <button type="submit">Afficher</button>
    </form>
    <p>
      <span class="badge" :class="ledger?.status === 'closed' ? 'ok' : 'warn'">{{
        ledger?.status === "closed" ? "clôturé" : "ouvert"
      }}</span>
    </p>
    <div v-if="ledger?.issues.length" class="error">
      <div v-for="issue in ledger.issues" :key="issue.code">{{ issue.message }}</div>
    </div>
    <a :href="exportUrl" target="_blank"><button class="secondary">Exporter en CSV</button></a>
  </div>

  <div class="card">
    <h2>Soldes</h2>
    <table>
      <thead>
        <tr>
          <th>Membre</th>
          <th>Solde</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="[uid, value] in balanceEntries" :key="uid">
          <td>{{ names[Number(uid)] }}</td>
          <td>{{ money(value) }}</td>
        </tr>
        <tr v-if="!balanceEntries.length">
          <td colspan="2" class="muted">Aucun trajet effectué ce mois-ci.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>Virements suggérés</h2>
    <table>
      <thead>
        <tr>
          <th>De</th>
          <th>Vers</th>
          <th>Montant</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="transfer in transfers" :key="`${transfer.debtor_id}-${transfer.creditor_id}`">
          <td>{{ names[transfer.debtor_id] }}</td>
          <td>{{ names[transfer.creditor_id] }}</td>
          <td>{{ money(transfer.amount) }}</td>
        </tr>
        <tr v-if="!transfers.length">
          <td colspan="3" class="muted">Rien à régler.</td>
        </tr>
      </tbody>
    </table>
    <div v-if="error" class="error">{{ error }}</div>
    <button :disabled="ledger?.status === 'closed'" @click="validate">Valider le bilan</button>
  </div>

  <div class="card">
    <h2>Remboursements</h2>
    <ul class="list">
      <li v-for="reimbursement in reimbursements" :key="reimbursement.id" class="row">
        <span>
          {{ names[reimbursement.payer_id] }} → {{ names[reimbursement.payee_id] }} : {{ money(reimbursement.amount) }}
          <span class="badge" :class="reimbursement.status === 'confirmed' ? 'ok' : 'warn'">{{
            reimbursement.status
          }}</span>
        </span>
        <button v-if="reimbursement.status === 'declared'" class="secondary" @click="confirmReimbursement(reimbursement.id)">
          Confirmer
        </button>
      </li>
      <li v-if="!reimbursements.length" class="muted">Aucun.</li>
    </ul>
    <form class="row" @submit.prevent="declareReimbursement">
      <label
        >Bénéficiaire
        <select v-model.number="payeeId">
          <option v-for="member in activeMembers" :key="member.user_id" :value="member.user_id">
            {{ names[member.user_id] }}
          </option>
        </select>
      </label>
      <label>Montant (€)<input v-model.number="amount" type="number" step="0.01" required /></label>
      <button type="submit">Déclarer un remboursement</button>
    </form>
  </div>
</template>
