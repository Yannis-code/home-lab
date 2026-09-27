import { createRouter, createWebHashHistory } from "vue-router";

import { isLoggedIn } from "@/api";
import { currentUser, refreshCurrentUser } from "@/composables/session";

const routes = [
  { path: "/", redirect: () => (isLoggedIn() ? "/groups" : "/login") },
  { path: "/login", name: "login", component: () => import("@/views/LoginView.vue") },
  {
    path: "/change-password",
    name: "change-password",
    component: () => import("@/views/ChangePasswordView.vue"),
  },
  { path: "/admin", name: "admin", component: () => import("@/views/AdminView.vue") },
  { path: "/groups", name: "groups", component: () => import("@/views/GroupsView.vue") },
  {
    path: "/groups/:id",
    name: "group-detail",
    component: () => import("@/views/GroupDetailView.vue"),
    props: true,
  },
  {
    path: "/groups/:id/vehicles",
    name: "group-vehicles",
    component: () => import("@/views/VehiclesView.vue"),
    props: true,
  },
  {
    path: "/groups/:id/trips",
    name: "group-trips",
    component: () => import("@/views/TripsView.vue"),
    props: true,
  },
  {
    path: "/groups/:id/recurring",
    name: "group-recurring",
    component: () => import("@/views/RecurringView.vue"),
    props: true,
  },
  {
    path: "/groups/:id/ledger",
    name: "group-ledger",
    component: () => import("@/views/LedgerView.vue"),
    props: true,
  },
  { path: "/trips/:id", name: "trip-detail", component: () => import("@/views/TripDetailView.vue"), props: true },
  { path: "/:pathMatch(.*)*", name: "not-found", component: () => import("@/views/NotFoundView.vue") },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach(async (to) => {
  if (to.name === "login") return true;
  if (!isLoggedIn()) return { name: "login" };
  if (!currentUser.value) {
    await refreshCurrentUser();
  }
  if (!currentUser.value) {
    return { name: "login" };
  }
  return true;
});
