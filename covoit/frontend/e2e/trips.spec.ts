import { expect, test } from "./fixtures";
import {
  adminToken,
  createGroup,
  createTrip,
  createUser,
  createVehicle,
  gotoHash,
  inviteAndJoin,
  leaveGroup,
  seedToken,
  today,
  transferManagement,
} from "./helpers";

async function setupGroupWithVehicle(seats: number) {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const carol = await createUser(admin, "Carol");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);
  await inviteAndJoin(alice.token, group.id, carol);
  const vehicle = await createVehicle(alice.token, {
    brand: "Peugeot",
    model: "308",
    seats,
    energies: [{ energy_type: "petrol", consumption_per_100km: 6 }],
  });
  return { alice, bob, carol, group, vehicle };
}

test("create a one-off trip and see it listed", async ({ page }) => {
  const { alice, bob, group } = await setupGroupWithVehicle(4);
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  await expect(page.getByText("Aucun trajet.")).toBeVisible();

  const { date } = today();
  await page.getByLabel("Date").fill(date);
  await page.getByLabel("Heure").fill("08:00");
  await page.getByLabel("Départ").fill("Maison");
  await page.getByLabel("Destination").fill("Travail");
  await page.getByLabel("Véhicule").selectOption({ label: "Peugeot 308 (4 places)" });
  await page.getByRole("checkbox", { name: bob.name }).check();
  await page.getByRole("checkbox", { name: bob.name }).uncheck();
  await page.getByRole("checkbox", { name: bob.name }).check();
  await page.getByLabel("Distance totale du trajet (km)").fill("100");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page.getByText(`${date} 08:00 — Maison → Travail`)).toBeVisible();
  await expect(page.getByText("Aucun trajet.")).toHaveCount(0);
});

test("trip creation over vehicle capacity shows an error", async ({ page }) => {
  const { alice, bob, carol, group } = await setupGroupWithVehicle(2);
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  const { date } = today();
  await page.getByLabel("Date").fill(date);
  await page.getByLabel("Heure").fill("08:00");
  await page.getByLabel("Départ").fill("Maison");
  await page.getByLabel("Destination").fill("Travail");
  await page.getByLabel("Véhicule").selectOption({ label: "Peugeot 308 (2 places)" });
  await page.getByRole("checkbox", { name: bob.name }).check();
  await page.getByRole("checkbox", { name: carol.name }).check();
  await page.getByLabel("Distance totale du trajet (km)").fill("100");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator(".error")).toBeVisible();
});

test("passenger request is waitlisted when the trip is full, driver can refuse it", async ({ page }) => {
  const { alice, bob, carol, group } = await setupGroupWithVehicle(2);
  const { date } = today();
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  await page.getByLabel("Date").fill(date);
  await page.getByLabel("Heure").fill("08:00");
  await page.getByLabel("Départ").fill("Maison");
  await page.getByLabel("Destination").fill("Travail");
  await page.getByLabel("Véhicule").selectOption({ label: "Peugeot 308 (2 places)" });
  await page.getByRole("checkbox", { name: bob.name }).check();
  await page.getByLabel("Distance totale du trajet (km)").fill("100");
  await page.getByRole("button", { name: "Créer" }).click();
  await page.getByRole("link", { name: new RegExp(date) }).click();
  await expect(page).toHaveURL(/#\/trips\/\d+$/);

  await seedToken(page, carol.token);
  await page.reload();
  await page.getByLabel("Point de montée (optionnel)").fill("Arrêt de bus");
  await page.getByRole("button", { name: "Demander une place" }).click();
  await expect(page.locator("li", { hasText: carol.name })).toContainText("waitlisted");
  await expect(page.getByRole("button", { name: "Demander une place" })).toHaveCount(0);

  await seedToken(page, alice.token);
  await page.reload();
  const carolRow = page.locator("li", { hasText: carol.name });
  await carolRow.getByRole("button", { name: "Refuser" }).click();
  await expect(carolRow.getByText("refused")).toBeVisible();
  await expect(carolRow.getByRole("button", { name: "Refuser" })).toHaveCount(0);
});

test("driver can accept a pending request under capacity and update trip status", async ({ page }) => {
  const { alice, bob, group } = await setupGroupWithVehicle(3);
  const { date } = today();
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  await page.getByLabel("Date").fill(date);
  await page.getByLabel("Heure").fill("08:00");
  await page.getByLabel("Départ").fill("Maison");
  await page.getByLabel("Destination").fill("Travail");
  await page.getByLabel("Véhicule").selectOption({ label: "Peugeot 308 (3 places)" });
  await page.getByLabel("Distance totale du trajet (km)").fill("100");
  await page.getByRole("button", { name: "Créer" }).click();
  await page.getByRole("link", { name: new RegExp(date) }).click();

  await seedToken(page, bob.token);
  await page.reload();
  await page.getByRole("button", { name: "Demander une place" }).click();
  await expect(page.locator("li", { hasText: bob.name })).toContainText("pending");

  await seedToken(page, alice.token);
  await page.reload();
  const bobRow = page.locator("li", { hasText: bob.name });
  await bobRow.getByRole("button", { name: "Accepter" }).click();
  await expect(bobRow.getByText("accepted")).toBeVisible();

  await page.getByRole("combobox").selectOption({ label: "effectué" });
  await page.getByRole("button", { name: "Mettre à jour le statut" }).click();
  await expect(page.locator(".badge", { hasText: "effectué" })).toBeVisible();
});

test("changing the selected driver reloads the available vehicles", async ({ page }) => {
  const { alice, bob, group } = await setupGroupWithVehicle(4);
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  await expect(page.getByLabel("Véhicule").locator("option")).toHaveCount(2);

  await page.getByLabel("Conducteur").selectOption({ label: bob.name });
  await expect(page.getByLabel("Véhicule").locator("option")).toHaveCount(1);
});

test("trips list is sorted by date, most recent first", async ({ page }) => {
  const { alice, group } = await setupGroupWithVehicle(4);
  const { date } = today();
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
  for (const d of [date, yesterday, tomorrow]) {
    await createTrip(alice.token, group.id, {
      date: d,
      time_of_day: "08:00",
      origin: "Maison",
      destination: "Travail",
      driver_id: alice.id,
      vehicle_id: null,
      passenger_ids: [],
      segments: [{ distance_km: 10, occupant_ids: [alice.id] }],
    });
  }

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  const rows = page.locator("ul.list li");
  await expect(rows.first()).toContainText(tomorrow);
  await expect(rows.last()).toContainText(yesterday);
});

test("a trip segment marked as a detour is shown accordingly", async ({ page }) => {
  const { alice, bob, group } = await setupGroupWithVehicle(4);
  const { date } = today();
  const trip = await createTrip(alice.token, group.id, {
    date,
    time_of_day: "08:00",
    origin: "Maison",
    destination: "Travail",
    driver_id: alice.id,
    vehicle_id: null,
    passenger_ids: [bob.id],
    segments: [
      { distance_km: 10, occupant_ids: [alice.id] },
      { distance_km: 5, occupant_ids: [alice.id, bob.id], is_detour: true, detour_for_id: bob.id },
    ],
  });

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/trips/${trip.id}`);
  const rows = page.locator("table tbody tr");
  await expect(rows.nth(0)).toContainText("—");
  await expect(rows.nth(1)).toContainText("oui");
});

test("trips page falls back to the first active member when there is no default driver", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);
  await transferManagement(alice.token, group.id, bob.id);
  await leaveGroup(alice.token, group.id);

  await seedToken(page, bob.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  await expect(page.getByLabel("Conducteur")).toHaveValue(String(bob.id));
});

test("update status, request seat and decide show an error when the request fails", async ({ page }) => {
  const { alice, bob, group } = await setupGroupWithVehicle(3);
  const { date } = today();
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/trips`);
  await page.getByLabel("Date").fill(date);
  await page.getByLabel("Heure").fill("08:00");
  await page.getByLabel("Départ").fill("Maison");
  await page.getByLabel("Destination").fill("Travail");
  await page.getByLabel("Véhicule").selectOption({ label: "Peugeot 308 (3 places)" });
  await page.getByLabel("Distance totale du trajet (km)").fill("100");
  await page.getByRole("button", { name: "Créer" }).click();
  await page.getByRole("link", { name: new RegExp(date) }).click();

  await page.route("**/status", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await page.getByRole("combobox").selectOption({ label: "effectué" });
  await page.getByRole("button", { name: "Mettre à jour le statut" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await page.unroute("**/status");

  await seedToken(page, bob.token);
  await page.reload();
  await page.route("**/participation-requests", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await page.getByRole("button", { name: "Demander une place" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await page.unroute("**/participation-requests");
  await page.getByRole("button", { name: "Demander une place" }).click();
  await expect(page.locator("li", { hasText: bob.name })).toContainText("pending");

  await seedToken(page, alice.token);
  await page.reload();
  await page.route("**/decision", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  const bobRow = page.locator("li", { hasText: bob.name });
  await bobRow.getByRole("button", { name: "Accepter" }).click();
  await expect(page.locator(".error")).toBeVisible();
});
