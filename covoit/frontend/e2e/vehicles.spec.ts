import { expect, test } from "./fixtures";
import { adminToken, createGroup, createUser, gotoHash, inviteAndJoin, seedToken } from "./helpers";

test("create a vehicle with one energy and see it listed", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/vehicles`);

  const mineCard = page.locator(".card", { hasText: "Mes véhicules" });
  await expect(mineCard.getByText("Aucun véhicule.")).toBeVisible();

  await page.getByLabel("Marque").fill("Peugeot");
  await page.getByLabel("Modèle").fill("308");
  await page.getByLabel("Nombre de places (conducteur inclus)").fill("5");
  await page.getByLabel("Source d'énergie").selectOption({ label: "Diesel" });
  await page.getByLabel(/Consommation moyenne/).fill("6");
  await page.getByRole("button", { name: "Ajouter" }).click();

  await expect(mineCard.getByText("Peugeot 308", { exact: true })).toBeVisible();
  await expect(mineCard.getByText("diesel: 6/100km")).toBeVisible();
  await expect(mineCard.getByText("Aucun véhicule.")).toHaveCount(0);
});

test("share a vehicle with the group and see it become accessible", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/vehicles`);
  await page.getByLabel("Marque").fill("Renault");
  await page.getByLabel("Modèle").fill("Clio");
  await page.getByLabel("Nombre de places (conducteur inclus)").fill("4");
  await page.getByLabel(/Consommation moyenne/).fill("5");
  await page.getByRole("button", { name: "Ajouter" }).click();

  await page.route("**/share", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await page.getByRole("button", { name: "Partager avec ce groupe" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await page.unroute("**/share");

  const shareButton = page.getByRole("button", { name: "Partager avec ce groupe" });
  await shareButton.click();
  await expect(page.getByRole("button", { name: "Partagé" })).toBeDisabled();

  await seedToken(page, bob.token);
  await gotoHash(page, `/#/groups/${group.id}/vehicles`);
  const accessibleCard = page.locator(".card", { hasText: "disponibles pour mes trajets" });
  await expect(accessibleCard.getByText("Renault Clio")).toBeVisible();
});
