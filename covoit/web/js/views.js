import { api, setToken } from "./api.js";
import { navigate } from "./router.js";

const userNameCache = new Map();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

function money(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) + " €" : String(value);
}

async function userName(id) {
  if (userNameCache.has(id)) return userNameCache.get(id);
  try {
    const user = await api.get(`/users/${id}`);
    userNameCache.set(id, user.name);
    return user.name;
  } catch {
    return `#${id}`;
  }
}

function onSubmit(form, handler) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = form.querySelector(".form-error");
    if (errorBox) errorBox.remove();
    try {
      await handler(new FormData(form));
    } catch (error) {
      const box = document.createElement("div");
      box.className = "error form-error";
      box.textContent = error.message;
      form.prepend(box);
    }
  });
}

const WEEKDAY_LABELS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

// ---------------------------------------------------------------------------
// Authentification
// ---------------------------------------------------------------------------

export async function viewLogin(root) {
  root.innerHTML = `
    <div class="card">
      <h1>Connexion</h1>
      <form id="login-form">
        <label>Adresse e-mail<input type="email" name="email" required autocomplete="username"></label>
        <label>Mot de passe<input type="password" name="password" required autocomplete="current-password"></label>
        <button type="submit">Se connecter</button>
      </form>
    </div>`;
  onSubmit(root.querySelector("#login-form"), async (form) => {
    const result = await api.post("/auth/login", {
      email: form.get("email"),
      password: form.get("password"),
    });
    setToken(result.token);
    navigate(result.must_change_password ? "#/change-password" : "#/groups");
  });
}

export async function viewChangePassword(root) {
  root.innerHTML = `
    <div class="card">
      <h1>Changer le mot de passe</h1>
      <p class="muted">Un nouveau mot de passe est requis avant de continuer.</p>
      <form id="pwd-form">
        <label>Mot de passe actuel<input type="password" name="current_password" required></label>
        <label>Nouveau mot de passe<input type="password" name="new_password" minlength="8" required></label>
        <button type="submit">Valider</button>
      </form>
    </div>`;
  onSubmit(root.querySelector("#pwd-form"), async (form) => {
    await api.post("/auth/change-password", {
      current_password: form.get("current_password"),
      new_password: form.get("new_password"),
    });
    navigate("#/groups");
  });
}

// ---------------------------------------------------------------------------
// Administration (comptes utilisateurs)
// ---------------------------------------------------------------------------

export async function viewAdmin(root) {
  const users = await api.get("/users");

  root.innerHTML = `
    <div class="card">
      <h1>Administration des comptes</h1>
      <form id="create-user-form">
        <label>Nom<input type="text" name="name" required></label>
        <label>Adresse e-mail<input type="email" name="email" required></label>
        <button type="submit">Créer le compte</button>
      </form>
      <div id="admin-result"></div>
    </div>
    <div class="card">
      <h2>Comptes existants</h2>
      <ul class="list">
        ${users
          .map(
            (u) => `<li class="row">
              <span>${escapeHtml(u.name)} ${u.is_admin ? '<span class="badge">admin</span>' : ""} ${!u.is_active ? '<span class="badge danger">désactivé</span>' : ""}</span>
              <button class="secondary" data-reset="${u.id}">Réinitialiser le mot de passe</button>
            </li>`
          )
          .join("")}
      </ul>
    </div>`;

  onSubmit(root.querySelector("#create-user-form"), async (form) => {
    const result = await api.post("/admin/users", { name: form.get("name"), email: form.get("email") });
    root.querySelector("#admin-result").innerHTML = `<div class="card"><p>Compte créé pour <strong>${escapeHtml(result.user.name)}</strong>.</p>
      <p>Mot de passe temporaire (à communiquer, affiché une seule fois) : <code>${escapeHtml(result.temporary_password)}</code></p></div>`;
    viewAdmin(root);
  });

  root.querySelectorAll("[data-reset]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const result = await api.post(`/admin/users/${btn.dataset.reset}/reset-password`);
      root.querySelector("#admin-result").innerHTML = `<div class="card"><p>Nouveau mot de passe temporaire : <code>${escapeHtml(result.temporary_password)}</code></p></div>`;
    })
  );
}

// ---------------------------------------------------------------------------
// Groupes
// ---------------------------------------------------------------------------

export async function viewGroups(root) {
  const [groups, invitations, recurringInvites] = await Promise.all([
    api.get("/groups"),
    api.get("/users/me/invitations"),
    api.get("/users/me/recurring-participations"),
  ]);

  root.innerHTML = `
    ${invitations.length ? `
      <div class="card">
        <h2>Invitations en attente</h2>
        <ul class="list">
          ${invitations
            .map(
              (inv) => `
            <li class="row">
              <span>${escapeHtml(inv.group_name)}</span>
              <button class="secondary" data-accept="${inv.group_id}:${inv.id}">Accepter</button>
              <button class="danger" data-decline="${inv.group_id}:${inv.id}">Refuser</button>
            </li>`
            )
            .join("")}
        </ul>
      </div>` : ""}
    ${recurringInvites.length ? `
      <div class="card">
        <h2>Trajets récurrents proposés</h2>
        <ul class="list">
          ${recurringInvites
            .map(
              (inv) => `
            <li class="row">
              <span>${escapeHtml(inv.model_name)}</span>
              <button class="secondary" data-accept-recurring="${inv.recurring_model_id}:${inv.id}">Accepter</button>
            </li>`
            )
            .join("")}
        </ul>
      </div>` : ""}
    <div class="card">
      <h1>Mes groupes</h1>
      <ul class="list">
        ${groups
          .map(
            (g) => `<li><a href="#/groups/${g.id}">${escapeHtml(g.name)}</a>${g.is_archived ? ' <span class="badge">archivé</span>' : ""}</li>`
          )
          .join("") || '<li class="muted">Aucun groupe pour le moment.</li>'}
      </ul>
    </div>
    <div class="card">
      <h2>Créer un groupe</h2>
      <form id="create-group-form">
        <label>Nom du groupe<input type="text" name="name" required></label>
        <button type="submit">Créer</button>
      </form>
    </div>`;

  onSubmit(root.querySelector("#create-group-form"), async (form) => {
    const group = await api.post("/groups", { name: form.get("name") });
    navigate(`#/groups/${group.id}`);
  });

  root.querySelectorAll("[data-accept]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [groupId, membershipId] = btn.dataset.accept.split(":");
      await api.post(`/groups/${groupId}/invitations/${membershipId}/accept`);
      viewGroups(root);
    })
  );
  root.querySelectorAll("[data-decline]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [groupId, membershipId] = btn.dataset.decline.split(":");
      await api.post(`/groups/${groupId}/invitations/${membershipId}/decline`);
      viewGroups(root);
    })
  );
  root.querySelectorAll("[data-accept-recurring]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [modelId, participantId] = btn.dataset.acceptRecurring.split(":");
      await api.post(`/recurring-models/${modelId}/participants/${participantId}/accept`);
      viewGroups(root);
    })
  );
}

export async function viewGroupDetail(root, { id }) {
  const groupId = Number(id);
  const [group, members, me] = await Promise.all([
    api.get(`/groups/${groupId}`),
    api.get(`/groups/${groupId}/members`),
    api.get("/users/me"),
  ]);
  const activeMembers = members.filter((m) => m.status === "active");
  const names = await Promise.all(activeMembers.map((m) => userName(m.user_id)));
  const isManager = group.manager_id === me.id;

  root.innerHTML = `
    <div class="card">
      <h1>${escapeHtml(group.name)} ${group.is_archived ? '<span class="badge">archivé</span>' : ""}</h1>
      <p class="muted">Gestionnaire : ${escapeHtml(names[activeMembers.findIndex((m) => m.user_id === group.manager_id)] || group.manager_id)}</p>
      <p class="muted">Conducteur par défaut : ${
        group.default_driver_id
          ? escapeHtml(names[activeMembers.findIndex((m) => m.user_id === group.default_driver_id)] || group.default_driver_id)
          : "aucun"
      }</p>
      <div class="row">
        <a href="#/groups/${groupId}/vehicles"><button class="secondary">Véhicules</button></a>
        <a href="#/groups/${groupId}/trips"><button class="secondary">Trajets</button></a>
        <a href="#/groups/${groupId}/recurring"><button class="secondary">Trajets récurrents</button></a>
        <a href="#/groups/${groupId}/ledger"><button class="secondary">Bilan mensuel</button></a>
      </div>
    </div>

    <div class="card">
      <h2>Membres</h2>
      <ul class="list">
        ${activeMembers
          .map(
            (m, i) => `<li>${escapeHtml(names[i])} ${m.user_id === group.manager_id ? '<span class="badge">gestionnaire</span>' : ""} ${m.user_id === group.default_driver_id ? '<span class="badge ok">conducteur par défaut</span>' : ""}</li>`
          )
          .join("")}
      </ul>
    </div>

    ${!group.is_archived ? `
    <div class="card">
      <h2>Actions</h2>
      <form id="driver-form" class="row">
        <label>Conducteur par défaut
          <select name="user_id">
            ${activeMembers.map((m, i) => `<option value="${m.user_id}">${escapeHtml(names[i])}</option>`).join("")}
          </select>
        </label>
        <button type="submit">Changer</button>
      </form>
      ${isManager ? `
      <form id="transfer-form" class="row">
        <label>Transférer la gestion à
          <select name="new_manager_id">
            ${activeMembers.map((m, i) => `<option value="${m.user_id}">${escapeHtml(names[i])}</option>`).join("")}
          </select>
        </label>
        <button type="submit">Transférer</button>
      </form>
      <form id="invite-form" class="row">
        <label>Inviter un utilisateur (recherche par nom)<input type="text" name="query" placeholder="alice"></label>
        <button type="submit">Rechercher</button>
      </form>
      <div id="invite-results"></div>
      <button id="archive-btn" class="danger">Archiver le groupe</button>
      ` : ""}
      <button id="leave-btn" class="danger">Quitter le groupe</button>
    </div>` : ""}
    <div id="action-error"></div>`;

  function reload() {
    viewGroupDetail(root, { id });
  }
  function showError(message) {
    const box = root.querySelector("#action-error");
    box.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
  }

  const driverForm = root.querySelector("#driver-form");
  if (driverForm) {
    onSubmit(driverForm, async (form) => {
      await api.post(`/groups/${groupId}/default-driver`, { user_id: Number(form.get("user_id")) });
      reload();
    });
  }
  const transferForm = root.querySelector("#transfer-form");
  if (transferForm) {
    onSubmit(transferForm, async (form) => {
      await api.post(`/groups/${groupId}/transfer-management`, {
        new_manager_id: Number(form.get("new_manager_id")),
      });
      reload();
    });
  }
  const inviteForm = root.querySelector("#invite-form");
  if (inviteForm) {
    onSubmit(inviteForm, async (form) => {
      const results = await api.get("/users", { query: form.get("query") });
      const box = root.querySelector("#invite-results");
      box.innerHTML = `<ul class="list">${results
        .map((u) => `<li class="row"><span>${escapeHtml(u.name)}</span><button class="secondary" data-invite="${u.id}">Inviter</button></li>`)
        .join("") || '<li class="muted">Aucun résultat.</li>'}</ul>`;
      box.querySelectorAll("[data-invite]").forEach((btn) =>
        btn.addEventListener("click", async () => {
          try {
            await api.post(`/groups/${groupId}/invitations`, { user_id: Number(btn.dataset.invite) });
            btn.textContent = "Invité";
            btn.disabled = true;
          } catch (error) {
            showError(error.message);
          }
        })
      );
    });
  }
  const archiveBtn = root.querySelector("#archive-btn");
  if (archiveBtn) {
    archiveBtn.addEventListener("click", async () => {
      try {
        await api.post(`/groups/${groupId}/archive`);
        reload();
      } catch (error) {
        showError(error.message);
      }
    });
  }
  const leaveBtn = root.querySelector("#leave-btn");
  if (leaveBtn) {
    leaveBtn.addEventListener("click", async () => {
      try {
        await api.post(`/groups/${groupId}/leave`);
        navigate("#/groups");
      } catch (error) {
        showError(error.message);
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Véhicules
// ---------------------------------------------------------------------------

const ENERGY_TYPES = [
  { value: "petrol", label: "Essence" },
  { value: "diesel", label: "Diesel" },
  { value: "ethanol", label: "Éthanol" },
  { value: "electric", label: "Électrique" },
];

export async function viewVehicles(root, { id }) {
  const groupId = Number(id);
  const [mine, accessible] = await Promise.all([
    api.get("/vehicles/mine"),
    api.get(`/groups/${groupId}/vehicles`),
  ]);

  root.innerHTML = `
    <p><a href="#/groups/${groupId}">&larr; Retour au groupe</a></p>
    <div class="card">
      <h1>Mes véhicules</h1>
      <ul class="list">
        ${mine
          .map(
            (v) => `<li>
              <strong>${escapeHtml(v.brand)} ${escapeHtml(v.model)}</strong> — ${v.seats} places
              <div class="muted">${v.energies.map((e) => `${escapeHtml(e.energy_type)}: ${e.consumption_per_100km}/100km`).join(", ")}</div>
              <button class="secondary" data-share="${v.id}">Partager avec ce groupe</button>
            </li>`
          )
          .join("") || '<li class="muted">Aucun véhicule.</li>'}
      </ul>
    </div>
    <div class="card">
      <h2>Ajouter un véhicule</h2>
      <form id="vehicle-form">
        <label>Marque<input type="text" name="brand" required></label>
        <label>Modèle<input type="text" name="model" required></label>
        <label>Nombre de places (conducteur inclus)<input type="number" name="seats" min="1" value="5" required></label>
        <label>Source d'énergie
          <select name="energy_type">
            ${ENERGY_TYPES.map((e) => `<option value="${e.value}">${e.label}</option>`).join("")}
          </select>
        </label>
        <label>Consommation moyenne (/100km)<input type="number" step="0.1" name="consumption" required></label>
        <button type="submit">Ajouter</button>
      </form>
    </div>
    <div class="card">
      <h2>Véhicules disponibles pour mes trajets dans ce groupe</h2>
      <ul class="list">
        ${accessible.map((v) => `<li>${escapeHtml(v.brand)} ${escapeHtml(v.model)} (${v.seats} places)</li>`).join("") || '<li class="muted">Aucun.</li>'}
      </ul>
    </div>`;

  onSubmit(root.querySelector("#vehicle-form"), async (form) => {
    await api.post("/vehicles", {
      brand: form.get("brand"),
      model: form.get("model"),
      seats: Number(form.get("seats")),
      energies: [
        {
          energy_type: form.get("energy_type"),
          consumption_per_100km: Number(form.get("consumption")),
        },
      ],
    });
    viewVehicles(root, { id });
  });

  root.querySelectorAll("[data-share]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api.post(`/vehicles/${btn.dataset.share}/share`, { group_id: groupId });
      btn.textContent = "Partagé";
      btn.disabled = true;
    })
  );
}

// ---------------------------------------------------------------------------
// Trajets
// ---------------------------------------------------------------------------

const STATUS_LABELS = { planned: "prévu", completed: "effectué", cancelled: "annulé" };

export async function viewTrips(root, { id }) {
  const groupId = Number(id);
  const [members, trips, me] = await Promise.all([
    api.get(`/groups/${groupId}/members`),
    api.get(`/groups/${groupId}/trips`),
    api.get("/users/me"),
  ]);
  const activeMembers = members.filter((m) => m.status === "active");
  const names = await Promise.all(activeMembers.map((m) => userName(m.user_id)));
  const vehicles = await api.get(`/groups/${groupId}/vehicles`, { driver_id: me.id });

  trips.sort((a, b) => (a.date < b.date ? 1 : -1));

  root.innerHTML = `
    <p><a href="#/groups/${groupId}">&larr; Retour au groupe</a></p>
    <div class="card">
      <h1>Trajets</h1>
      <ul class="list">
        ${trips
          .map(
            (t) => `<li>
              <a href="#/trips/${t.id}">${t.date} ${t.time_of_day} — ${escapeHtml(t.origin)} → ${escapeHtml(t.destination)}</a>
              <span class="badge">${STATUS_LABELS[t.status] || t.status}</span>
            </li>`
          )
          .join("") || '<li class="muted">Aucun trajet.</li>'}
      </ul>
    </div>
    <div class="card">
      <h2>Créer un trajet ponctuel</h2>
      <form id="trip-form">
        <label>Date<input type="date" name="date" required></label>
        <label>Heure<input type="time" name="time_of_day" required></label>
        <label>Départ<input type="text" name="origin" required></label>
        <label>Destination<input type="text" name="destination" required></label>
        <label>Conducteur
          <select name="driver_id">
            ${activeMembers.map((m, i) => `<option value="${m.user_id}">${escapeHtml(names[i])}</option>`).join("")}
          </select>
        </label>
        <label>Véhicule
          <select name="vehicle_id">
            <option value="">— aucun —</option>
            ${vehicles.map((v) => `<option value="${v.id}">${escapeHtml(v.brand)} ${escapeHtml(v.model)} (${v.seats} places)</option>`).join("")}
          </select>
        </label>
        <fieldset>
          <legend>Passagers</legend>
          ${activeMembers
            .map(
              (m, i) => `<label class="checkbox-row"><input type="checkbox" name="passenger" value="${m.user_id}">${escapeHtml(names[i])}</label>`
            )
            .join("")}
        </fieldset>
        <label>Distance totale du trajet (km)<input type="number" step="0.1" name="distance_km" required></label>
        <p class="muted">Le conducteur et les passagers cochés sont tous considérés à bord sur l'ensemble du trajet (un seul tronçon). Les tronçons détaillés et détours sont modifiables via l'API.</p>
        <button type="submit">Créer</button>
      </form>
    </div>`;

  onSubmit(root.querySelector("#trip-form"), async (form) => {
    const driverId = Number(form.get("driver_id"));
    const passengerIds = form.getAll("passenger").map(Number).filter((pid) => pid !== driverId);
    const vehicleId = form.get("vehicle_id") ? Number(form.get("vehicle_id")) : null;
    await api.post(`/groups/${groupId}/trips`, {
      date: form.get("date"),
      time_of_day: form.get("time_of_day"),
      origin: form.get("origin"),
      destination: form.get("destination"),
      driver_id: driverId,
      vehicle_id: vehicleId,
      passenger_ids: passengerIds,
      segments: [
        {
          distance_km: Number(form.get("distance_km")),
          occupant_ids: [driverId, ...passengerIds],
        },
      ],
    });
    viewTrips(root, { id });
  });
}

export async function viewTripDetail(root, { id }) {
  const tripId = Number(id);
  const [trip, segments, participations, me] = await Promise.all([
    api.get(`/trips/${tripId}`),
    api.get(`/trips/${tripId}/segments`),
    api.get(`/trips/${tripId}/participations`),
    api.get("/users/me"),
  ]);
  const names = await Promise.all(participations.map((p) => userName(p.user_id)));
  const isDriver = trip.driver_id === me.id;
  const myParticipation = participations.find((p) => p.user_id === me.id);

  root.innerHTML = `
    <p><a href="#/groups/${trip.group_id}/trips">&larr; Retour aux trajets</a></p>
    <div class="card">
      <h1>${escapeHtml(trip.origin)} → ${escapeHtml(trip.destination)}</h1>
      <p class="muted">${trip.date} à ${trip.time_of_day} — <span class="badge">${STATUS_LABELS[trip.status] || trip.status}</span></p>
      <form id="status-form" class="row">
        <select name="status">
          <option value="planned" ${trip.status === "planned" ? "selected" : ""}>prévu</option>
          <option value="completed" ${trip.status === "completed" ? "selected" : ""}>effectué</option>
          <option value="cancelled" ${trip.status === "cancelled" ? "selected" : ""}>annulé</option>
        </select>
        <button type="submit">Mettre à jour le statut</button>
      </form>
    </div>

    <div class="card">
      <h2>Participants</h2>
      <ul class="list">
        ${participations
          .map(
            (p, i) => `<li class="row">
              <span>${escapeHtml(names[i])} — ${p.role === "driver" ? "conducteur" : "passager"} <span class="badge">${p.status}</span></span>
              ${isDriver && (p.status === "pending" || p.status === "waitlisted")
                ? `<button class="secondary" data-approve="${p.id}">Accepter</button><button class="danger" data-refuse="${p.id}">Refuser</button>`
                : ""}
            </li>`
          )
          .join("")}
      </ul>
      ${!myParticipation ? `
      <form id="request-form" class="row">
        <label>Point de montée (optionnel)<input type="text" name="boarding_point"></label>
        <button type="submit">Demander une place</button>
      </form>` : ""}
    </div>

    <div class="card">
      <h2>Tronçons</h2>
      <table>
        <thead><tr><th>#</th><th>Distance</th><th>Détour</th><th>Occupants</th></tr></thead>
        <tbody>
          ${segments
            .map(
              (s) => `<tr><td>${s.sequence}</td><td>${s.distance_km} km</td><td>${s.is_detour ? "oui" : "—"}</td><td>${s.occupant_ids.length}</td></tr>`
            )
            .join("")}
        </tbody>
      </table>
      <p class="muted">Le détail fin des tronçons/détours et les corrections post-clôture se gèrent via l'API (v1).</p>
    </div>
    <div id="trip-error"></div>`;

  function showError(message) {
    root.querySelector("#trip-error").innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
  }

  onSubmit(root.querySelector("#status-form"), async (form) => {
    await api.post(`/trips/${tripId}/status`, { status: form.get("status") });
    viewTripDetail(root, { id });
  });

  const requestForm = root.querySelector("#request-form");
  if (requestForm) {
    onSubmit(requestForm, async (form) => {
      await api.post(`/trips/${tripId}/participation-requests`, {
        boarding_point: form.get("boarding_point") || null,
      });
      viewTripDetail(root, { id });
    });
  }

  root.querySelectorAll("[data-approve]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await api.post(`/trips/${tripId}/participation-requests/${btn.dataset.approve}/decision`, { approve: true });
        viewTripDetail(root, { id });
      } catch (error) {
        showError(error.message);
      }
    })
  );
  root.querySelectorAll("[data-refuse]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await api.post(`/trips/${tripId}/participation-requests/${btn.dataset.refuse}/decision`, { approve: false });
        viewTripDetail(root, { id });
      } catch (error) {
        showError(error.message);
      }
    })
  );
}

// ---------------------------------------------------------------------------
// Trajets récurrents
// ---------------------------------------------------------------------------

export async function viewRecurring(root, { id }) {
  const groupId = Number(id);
  const models = await api.get(`/groups/${groupId}/recurring-models`);

  root.innerHTML = `
    <p><a href="#/groups/${groupId}">&larr; Retour au groupe</a></p>
    <div class="card">
      <h1>Trajets récurrents</h1>
      <ul class="list">
        ${models
          .map(
            (m) => `<li>
              <strong>${escapeHtml(m.name)}</strong> — ${escapeHtml(m.origin)} → ${escapeHtml(m.destination)} à ${m.time_of_day}
              <div class="muted">${m.weekdays.map((d) => WEEKDAY_LABELS[d]).join(", ")} ${m.is_paused ? '<span class="badge warn">en pause</span>' : ""}</div>
              <div class="row">
                ${m.is_paused
                  ? `<button class="secondary" data-resume="${m.id}">Reprendre</button>`
                  : `<button class="secondary" data-pause="${m.id}">Mettre en pause</button>`}
                <button class="secondary" data-generate="${m.id}">Générer les occurrences</button>
                <button class="danger" data-delete="${m.id}">Supprimer</button>
              </div>
            </li>`
          )
          .join("") || '<li class="muted">Aucun modèle récurrent.</li>'}
      </ul>
    </div>
    <div class="card">
      <h2>Créer un modèle récurrent</h2>
      <form id="recurring-form">
        <label>Nom<input type="text" name="name" required placeholder="Matin"></label>
        <label>Départ<input type="text" name="origin" required></label>
        <label>Destination<input type="text" name="destination" required></label>
        <label>Heure<input type="time" name="time_of_day" required></label>
        <fieldset class="weekday-picker">
          <legend>Jours de la semaine</legend>
          ${WEEKDAY_LABELS.map((label, i) => `<label><input type="checkbox" name="weekday" value="${i}">${label}</label>`).join("")}
        </fieldset>
        <button type="submit">Créer</button>
      </form>
    </div>
    <div id="recurring-error"></div>`;

  function showError(message) {
    root.querySelector("#recurring-error").innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
  }

  onSubmit(root.querySelector("#recurring-form"), async (form) => {
    const weekdays = form.getAll("weekday").map(Number);
    await api.post(`/groups/${groupId}/recurring-models`, {
      name: form.get("name"),
      origin: form.get("origin"),
      destination: form.get("destination"),
      time_of_day: form.get("time_of_day"),
      weekdays,
    });
    viewRecurring(root, { id });
  });

  root.querySelectorAll("[data-pause]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api.post(`/recurring-models/${btn.dataset.pause}/pause`);
      viewRecurring(root, { id });
    })
  );
  root.querySelectorAll("[data-resume]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api.post(`/recurring-models/${btn.dataset.resume}/resume`);
      viewRecurring(root, { id });
    })
  );
  root.querySelectorAll("[data-delete]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api.del(`/recurring-models/${btn.dataset.delete}`);
      viewRecurring(root, { id });
    })
  );
  root.querySelectorAll("[data-generate]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        const created = await api.post(`/recurring-models/${btn.dataset.generate}/generate-occurrences`, {
          horizon_days: 60,
        });
        showError(`${created.length} occurrence(s) générée(s).`);
      } catch (error) {
        showError(error.message);
      }
    })
  );
}

// ---------------------------------------------------------------------------
// Bilan mensuel
// ---------------------------------------------------------------------------

export async function viewLedger(root, { id }) {
  const groupId = Number(id);
  const now = new Date();
  const year = Number(new URLSearchParams(location.hash.split("?")[1]).get("year")) || now.getFullYear();
  const month = Number(new URLSearchParams(location.hash.split("?")[1]).get("month")) || now.getMonth() + 1;

  const [ledger, members, reimbursements] = await Promise.all([
    api.get(`/groups/${groupId}/ledger`, { year, month }),
    api.get(`/groups/${groupId}/members`),
    api.get(`/groups/${groupId}/reimbursements`, { year, month }),
  ]);
  const activeMembers = members.filter((m) => m.status === "active");
  const names = await Promise.all(activeMembers.map((m) => userName(m.user_id)));
  const nameOf = async (uid) => userName(uid);
  const balanceRows = await Promise.all(
    Object.entries(ledger.balances).map(async ([uid, amount]) => `<tr><td>${escapeHtml(await nameOf(uid))}</td><td>${money(amount)}</td></tr>`)
  );
  const transferRows = await Promise.all(
    ledger.transfers.map(
      async (t) => `<tr><td>${escapeHtml(await nameOf(t.debtor_id))}</td><td>${escapeHtml(await nameOf(t.creditor_id))}</td><td>${money(t.amount)}</td></tr>`
    )
  );

  root.innerHTML = `
    <p><a href="#/groups/${groupId}">&larr; Retour au groupe</a></p>
    <div class="card">
      <h1>Bilan de ${String(month).padStart(2, "0")}/${year}</h1>
      <form id="period-form" class="row">
        <label>Année<input type="number" name="year" value="${year}"></label>
        <label>Mois<input type="number" name="month" min="1" max="12" value="${month}"></label>
        <button type="submit">Afficher</button>
      </form>
      <p><span class="badge ${ledger.status === "closed" ? "ok" : "warn"}">${ledger.status === "closed" ? "clôturé" : "ouvert"}</span></p>
      ${ledger.issues.length
        ? `<div class="error">${ledger.issues.map((i) => escapeHtml(i.message)).join("<br>")}</div>`
        : ""}
      <a href="/groups/${groupId}/ledger/export?year=${year}&month=${month}" target="_blank"><button class="secondary">Exporter en CSV</button></a>
    </div>

    <div class="card">
      <h2>Soldes</h2>
      <table><thead><tr><th>Membre</th><th>Solde</th></tr></thead><tbody>${balanceRows.join("") || "<tr><td colspan=2 class=muted>Aucun trajet effectué ce mois-ci.</td></tr>"}</tbody></table>
    </div>

    <div class="card">
      <h2>Virements suggérés</h2>
      <table><thead><tr><th>De</th><th>Vers</th><th>Montant</th></tr></thead><tbody>${transferRows.join("") || "<tr><td colspan=3 class=muted>Rien à régler.</td></tr>"}</tbody></table>
      <button id="validate-btn" ${ledger.status === "closed" ? "disabled" : ""}>Valider le bilan</button>
    </div>

    <div class="card">
      <h2>Remboursements</h2>
      <ul class="list">
        ${reimbursements
          .map(
            (r) => `<li class="row">
              <span>#${r.payer_id} → #${r.payee_id} : ${money(r.amount)} <span class="badge ${r.status === "confirmed" ? "ok" : "warn"}">${r.status}</span></span>
              ${r.status === "declared" ? `<button class="secondary" data-confirm="${r.id}">Confirmer</button>` : ""}
            </li>`
          )
          .join("") || '<li class="muted">Aucun.</li>'}
      </ul>
      <form id="reimb-form" class="row">
        <label>Bénéficiaire
          <select name="payee_id">
            ${activeMembers.map((m, i) => `<option value="${m.user_id}">${escapeHtml(names[i])}</option>`).join("")}
          </select>
        </label>
        <label>Montant (€)<input type="number" step="0.01" name="amount" required></label>
        <button type="submit">Déclarer un remboursement</button>
      </form>
    </div>
    <div id="ledger-error"></div>`;

  function showError(message) {
    root.querySelector("#ledger-error").innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
  }

  onSubmit(root.querySelector("#period-form"), async (form) => {
    location.hash = `#/groups/${groupId}/ledger?year=${form.get("year")}&month=${form.get("month")}`;
    viewLedger(root, { id });
  });

  root.querySelector("#validate-btn").addEventListener("click", async () => {
    try {
      await api.post(`/groups/${groupId}/ledger/validate`, { year, month });
      viewLedger(root, { id });
    } catch (error) {
      showError(error.message);
    }
  });

  onSubmit(root.querySelector("#reimb-form"), async (form) => {
    await api.post(`/groups/${groupId}/reimbursements`, {
      payee_id: Number(form.get("payee_id")),
      amount: Number(form.get("amount")),
      year,
      month,
    });
    viewLedger(root, { id });
  });

  root.querySelectorAll("[data-confirm]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await api.post(`/reimbursements/${btn.dataset.confirm}/confirm`);
        viewLedger(root, { id });
      } catch (error) {
        showError(error.message);
      }
    })
  );
}
