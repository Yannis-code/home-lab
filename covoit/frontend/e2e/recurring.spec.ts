import { expect, test } from "./fixtures";
import {
  adminToken,
  createGroup,
  createUser,
  gotoHash,
  inviteAndJoin,
  leaveGroup,
  seedToken,
  transferManagement,
} from "./helpers";

test("create, pause, resume, generate and delete a recurring model", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}/recurring`);

  await expect(page.getByText("Aucun modèle récurrent.")).toBeVisible();

  await page.getByLabel("Nom").fill("Matin");
  await page.getByLabel("Départ").fill("Maison");
  await page.getByLabel("Destination").fill("Travail");
  await page.getByLabel("Heure").fill("08:00");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator(".error")).toBeVisible();

  for (const day of ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]) {
    await page.getByLabel(day).check();
  }
  await page.getByLabel("Lun").uncheck();
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page.getByText("Matin")).toBeVisible();
  await expect(page.locator(".badge.warn")).toHaveCount(0);

  await page.getByRole("button", { name: "Mettre en pause" }).click();
  await expect(page.locator(".badge.warn", { hasText: "en pause" })).toBeVisible();

  await page.getByRole("button", { name: "Reprendre" }).click();
  await expect(page.locator(".badge.warn")).toHaveCount(0);

  await page.getByRole("button", { name: "Générer les occurrences" }).click();
  await expect(page.getByText(/occurrence\(s\) générée\(s\)/)).toBeVisible();

  await page.getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByText("Aucun modèle récurrent.")).toBeVisible();
});

test("generating occurrences fails when the group has no default driver", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);
  await transferManagement(alice.token, group.id, bob.id);
  await leaveGroup(alice.token, group.id);

  await seedToken(page, bob.token);
  await gotoHash(page, `/#/groups/${group.id}/recurring`);
  await page.getByLabel("Nom").fill("Matin");
  await page.getByLabel("Départ").fill("Maison");
  await page.getByLabel("Destination").fill("Travail");
  await page.getByLabel("Heure").fill("08:00");
  await page.getByLabel("Lun").check();
  await page.getByRole("button", { name: "Créer" }).click();
  await page.getByRole("button", { name: "Générer les occurrences" }).click();
  await expect(page.locator(".error")).toBeVisible();
});
