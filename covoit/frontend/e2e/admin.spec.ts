import { expect, test } from "./fixtures";
import { ADMIN_EMAIL, ADMIN_PASSWORD, createUser, gotoHash, login, seedToken } from "./helpers";

test("admin creates a user, resets password, deactivates it", async ({ page }) => {
  const adminLoginToken = await login(ADMIN_EMAIL, ADMIN_PASSWORD);
  await seedToken(page, adminLoginToken);
  await gotoHash(page, "/#/admin");

  await page.getByLabel("Nom").fill("Charlie");
  await page.getByLabel("Adresse e-mail").fill("charlie@covoit.home");
  await page.getByRole("button", { name: "Créer le compte" }).click();

  await expect(page.getByText(/Compte créé pour Charlie/)).toBeVisible();
  await expect(page.getByText("Charlie", { exact: true })).toBeVisible();

  const row = page.locator("li", { hasText: "Charlie" });
  await row.getByRole("button", { name: "Réinitialiser le mot de passe" }).click();
  await expect(page.getByText(/Nouveau mot de passe temporaire/)).toBeVisible();

  await row.getByRole("button", { name: "Désactiver" }).click();
  await expect(row.getByText("désactivé")).toBeVisible();
  await expect(row.getByRole("button", { name: "Désactiver" })).toHaveCount(0);
});

test("admin badge is shown for the bootstrap account", async ({ page }) => {
  const adminLoginToken = await login(ADMIN_EMAIL, ADMIN_PASSWORD);
  await seedToken(page, adminLoginToken);
  await gotoHash(page, "/#/admin");
  const row = page.locator("li", { hasText: "Administrateur" });
  await expect(row.getByText("admin")).toBeVisible();
});

test("non-admin gets a forbidden error when trying to create a user", async ({ page }) => {
  const adminLoginToken = await login(ADMIN_EMAIL, ADMIN_PASSWORD);
  const user = await createUser(adminLoginToken, "Dave");
  await seedToken(page, user.token);
  await gotoHash(page, "/#/admin");

  await page.getByLabel("Nom").fill("Eve");
  await page.getByLabel("Adresse e-mail").fill("eve@covoit.home");
  await page.getByRole("button", { name: "Créer le compte" }).click();

  await expect(page.locator(".error")).toBeVisible();
});

test("reset-password and deactivate show an error when the request fails", async ({ page }) => {
  const adminLoginToken = await login(ADMIN_EMAIL, ADMIN_PASSWORD);
  await createUser(adminLoginToken, "Frank");
  await seedToken(page, adminLoginToken);
  await gotoHash(page, "/#/admin");
  const row = page.locator("li", { hasText: "Frank" });

  await page.route("**/admin/users/*/reset-password", async (route) => {
    await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await row.getByRole("button", { name: "Réinitialiser le mot de passe" }).click();
  await expect(page.locator(".error")).toBeVisible();

  await page.unroute("**/admin/users/*/reset-password");
  await page.route("**/admin/users/*/deactivate", async (route) => {
    await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await row.getByRole("button", { name: "Désactiver" }).click();
  await expect(row.getByText("désactivé")).toHaveCount(0);
});
