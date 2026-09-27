import { api, isLoggedIn, setToken } from "./api.js";
import { route, start, navigate } from "./router.js";
import {
  viewLogin,
  viewChangePassword,
  viewAdmin,
  viewGroups,
  viewGroupDetail,
  viewVehicles,
  viewTrips,
  viewTripDetail,
  viewRecurring,
  viewLedger,
} from "./views.js";

function requireAuth(view) {
  return async (root, params) => {
    if (!isLoggedIn()) {
      navigate("#/login");
      return;
    }
    await view(root, params);
  };
}

route(/^#\/login$/, viewLogin);
route(/^#\/change-password$/, requireAuth(viewChangePassword));
route(/^#\/admin$/, requireAuth(viewAdmin));
route(/^#\/groups$/, requireAuth(viewGroups));
route(/^#\/groups\/(?<id>\d+)\/vehicles$/, requireAuth(viewVehicles));
route(/^#\/groups\/(?<id>\d+)\/trips$/, requireAuth(viewTrips));
route(/^#\/groups\/(?<id>\d+)\/recurring$/, requireAuth(viewRecurring));
route(/^#\/groups\/(?<id>\d+)\/ledger(?:\?.*)?$/, requireAuth(viewLedger));
route(/^#\/groups\/(?<id>\d+)$/, requireAuth(viewGroupDetail));
route(/^#\/trips\/(?<id>\d+)$/, requireAuth(viewTripDetail));

async function renderNav() {
  const nav = document.getElementById("topnav");
  if (!isLoggedIn()) {
    nav.innerHTML = "";
    return;
  }
  try {
    const me = await api.get("/users/me");
    nav.innerHTML = `
      <span class="muted">${me.name}</span>
      <a href="#/groups">Groupes</a>
      ${me.is_admin ? '<a href="#/admin">Administration</a>' : ""}
      <button class="secondary" id="logout-btn">Se déconnecter</button>`;
    document.getElementById("logout-btn").addEventListener("click", () => {
      setToken(null);
      navigate("#/login");
      renderNav();
    });
  } catch {
    nav.innerHTML = "";
  }
}

start(document.getElementById("app"), {
  defaultHash: isLoggedIn() ? "#/groups" : "#/login",
  onRender: renderNav,
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {
      // L'application reste utilisable en ligne même si le service worker échoue.
    });
  });
}
