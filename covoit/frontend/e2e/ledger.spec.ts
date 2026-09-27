import { expect, test } from "./fixtures";
import {
  adminToken,
  createGroup,
  createTrip,
  createUser,
  createVehicle,
  gotoHash,
  inviteAndJoin,
  seedToken,
  setMonthlyPrice,
  setTripStatus,
  today,
} from "./helpers";

test("full billing lifecycle: missing price, validation, closure and reimbursement", async ({ page }) => {
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
    seats: 2,
    energies: [{ energy_type: "petrol", consumption_per_100km: 6 }],
  });
  const { date, year, month } = today();
  const trip = await createTrip(alice.token, group.id, {
    date,
    time_of_day: "08:00",
    origin: "Maison",
    destination: "Travail",
    driver_id: alice.id,
    vehicle_id: vehicle.id,
    passenger_ids: [bob.id],
    segments: [{ distance_km: 100, occupant_ids: [alice.id, bob.id] }],
  });
  await setTripStatus(alice.token, trip.id, "completed");

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/ledger`);
  await expect(page.locator(".error")).toBeVisible();
  await expect(page.getByText("Aucun trajet effectué ce mois-ci.")).toBeVisible();
  await expect(page.getByText("ouvert")).toBeVisible();

  await setMonthlyPrice(alice.token, vehicle.id, "petrol", year, month, 1.8);
  await page.getByLabel("Année").fill(String(year));
  await page.getByLabel("Mois").fill(String(month));
  await page.getByRole("button", { name: "Afficher" }).click();

  await expect(page.locator(".error")).toHaveCount(0);
  await expect(page.getByText("5.40 €").first()).toBeVisible();
  await expect(page.getByText("Rien à régler.")).toHaveCount(0);

  // Carol did not take part in this trip and cannot validate the ledger.
  await seedToken(page, carol.token);
  await gotoHash(page, `/#/groups/${group.id}/ledger`);
  await page.getByRole("button", { name: "Valider le bilan" }).click();
  await expect(page.locator(".error")).toBeVisible();

  await seedToken(page, bob.token);
  await gotoHash(page, `/#/groups/${group.id}/ledger`);
  await page.getByRole("button", { name: "Valider le bilan" }).click();
  await expect(page.getByText("ouvert")).toBeVisible();

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/ledger`);
  await page.getByRole("button", { name: "Valider le bilan" }).click();
  await expect(page.getByText("clôturé")).toBeVisible();
  await expect(page.getByRole("button", { name: "Valider le bilan" })).toBeDisabled();

  await expect(page.getByRole("link", { name: "Exporter en CSV" })).toHaveAttribute(
    "href",
    new RegExp(`/groups/${group.id}/ledger/export\\?year=${year}&month=${month}`)
  );

  await seedToken(page, bob.token);
  await gotoHash(page, `/#/groups/${group.id}/ledger`);
  await page.getByLabel("Bénéficiaire").selectOption({ label: alice.name });
  await page.getByLabel("Montant (€)").fill("-5");
  await page.getByRole("button", { name: "Déclarer un remboursement" }).click();
  await expect(page.locator(".error")).toBeVisible();

  await page.getByLabel("Montant (€)").fill("5.4");
  await page.getByRole("button", { name: "Déclarer un remboursement" }).click();
  await expect(page.getByText(/declared/)).toBeVisible();

  // Carol is not the reimbursement's payee and cannot confirm it.
  await seedToken(page, carol.token);
  await gotoHash(page, `/#/groups/${group.id}/ledger`);
  await page.getByRole("button", { name: "Confirmer" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await expect(page.getByText("confirmed")).toHaveCount(0);

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/ledger`);
  await page.getByRole("button", { name: "Confirmer" }).click();
  await expect(page.getByText("confirmed")).toBeVisible();
  await expect(page.getByText("Rien à régler.")).toBeVisible();
});
