import { expect, test } from "./fixtures";
import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  adminToken,
  changePassword,
  createUser,
  gotoHash,
  seedToken,
} from "./helpers";

test("admin can log in and must change password on first login", async ({ page }) => {
  await page.goto("/#/login");
  await page.getByLabel("Adresse e-mail").fill(ADMIN_EMAIL);
  await page.getByLabel("Mot de passe").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/#\/change-password/);
  await expect(page.getByText("Administrateur")).toBeVisible();
  await expect(page.getByRole("link", { name: "Administration" })).toBeVisible();
});

test("wrong password shows an error", async ({ page }) => {
  await page.goto("/#/login");
  await page.getByLabel("Adresse e-mail").fill(ADMIN_EMAIL);
  await page.getByLabel("Mot de passe").fill("not-the-password");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await expect(page).toHaveURL(/#\/login/);
});

test("change password form: failed attempt then success", async ({ page }) => {
  const admin = await adminToken();
  const user = await createUser(admin, "Alice");
  await seedToken(page, user.token);
  await gotoHash(page, "/#/change-password");

  // A 401 on this endpoint would also log the user out globally, so the
  // failure case exercised here uses a non-auth error (e.g. business-rule
  // rejection) to check the form's own error rendering in isolation.
  await page.route("**/auth/change-password", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await page.getByLabel("Mot de passe actuel").fill(user.temporaryPassword);
  await page.getByLabel("Nouveau mot de passe").fill("NewPassword123!");
  await page.getByRole("button", { name: "Valider" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await page.unroute("**/auth/change-password");

  await page.getByLabel("Mot de passe actuel").fill(user.temporaryPassword);
  await page.getByLabel("Nouveau mot de passe").fill("NewPassword123!");
  await page.getByRole("button", { name: "Valider" }).click();
  await expect(page).toHaveURL(/#\/groups/);
});

test("logging in after the password was already changed goes straight to groups", async ({ page }) => {
  const admin = await adminToken();
  const user = await createUser(admin, "Carol");
  await changePassword(user.token, user.temporaryPassword, "CarolPass123!");
  await gotoHash(page, "/#/login");
  await page.getByLabel("Adresse e-mail").fill(user.email);
  await page.getByLabel("Mot de passe").fill("CarolPass123!");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/#\/groups/);
});

test("regular user does not see the administration link and can log out", async ({ page }) => {
  const admin = await adminToken();
  const user = await createUser(admin, "Bob");
  await seedToken(page, user.token);
  await page.goto("/#/groups");
  await expect(page.getByText(user.name)).toBeVisible();
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);

  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/#\/login/);
});

test("invalid session token redirects to login", async ({ page }) => {
  await seedToken(page, "this-token-does-not-exist");
  await page.goto("/#/groups");
  await expect(page).toHaveURL(/#\/login/);
});

test("missing authorization redirects protected routes to login", async ({ page }) => {
  await page.goto("/#/groups");
  await expect(page).toHaveURL(/#\/login/);
});

test("visiting the root redirects to groups when logged in", async ({ page }) => {
  const admin = await adminToken();
  const user = await createUser(admin, "Dave");
  await changePassword(user.token, user.temporaryPassword, "DavePass123!");
  await seedToken(page, user.token);
  await gotoHash(page, "/#/");
  await expect(page).toHaveURL(/#\/groups/);
});

test("visiting the root redirects to login when logged out", async ({ page }) => {
  await gotoHash(page, "/#/");
  await expect(page).toHaveURL(/#\/login/);
});

test("unknown route shows the not-found page", async ({ page }) => {
  const admin = await adminToken();
  const user = await createUser(admin, "Erin");
  await seedToken(page, user.token);
  await gotoHash(page, "/#/this-route-does-not-exist");
  await expect(page.getByText("Page introuvable.")).toBeVisible();
});
