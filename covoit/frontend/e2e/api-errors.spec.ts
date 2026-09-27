import { expect, test } from "./fixtures";
import { adminToken, createGroup, createUser, gotoHash, seedToken } from "./helpers";

test("array validation errors from the backend are joined into a readable message", async ({ page }) => {
  const admin = await adminToken();
  await seedToken(page, admin);
  await page.route("**/admin/users", async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        detail: [
          { loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" },
          { loc: ["body", "name"], msg: "field required", type: "value_error.missing" },
        ],
      }),
    });
  });
  await gotoHash(page, "/#/admin");
  await page.getByLabel("Nom").fill("X");
  await page.getByLabel("Adresse e-mail").fill("x@covoit.home");
  await page.getByRole("button", { name: "Créer le compte" }).click();
  await expect(page.locator(".error")).toHaveText("value is not a valid email address, field required");
});

test("non-JSON error responses fall back to a generic message", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");
  await seedToken(page, alice.token);
  await page.route("**/vehicles", async (route) => {
    await route.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error" });
  });
  await gotoHash(page, `/#/groups/${group.id}/vehicles`);
  await page.getByLabel("Marque").fill("Peugeot");
  await page.getByLabel("Modèle").fill("308");
  await page.getByLabel("Nombre de places (conducteur inclus)").fill("5");
  await page.getByLabel(/Consommation moyenne/).fill("6");
  await page.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.locator(".error")).toHaveText("Erreur 500");
});

test("searching with an empty query still returns results (bare path, no query string)", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByRole("button", { name: "Rechercher" }).click();
  await expect(page.locator("li", { hasText: alice.name }).getByRole("button", { name: "Inviter" })).toBeVisible();
});

test("a response without a content-type header falls back to raw text", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");
  await seedToken(page, alice.token);
  await page.route("**/vehicles", async (route) => {
    await route.fulfill({ status: 500, headers: {}, body: "Erreur interne sans en-tête" });
  });
  await gotoHash(page, `/#/groups/${group.id}/vehicles`);
  await page.getByLabel("Marque").fill("Peugeot");
  await page.getByLabel("Modèle").fill("308");
  await page.getByLabel("Nombre de places (conducteur inclus)").fill("5");
  await page.getByLabel(/Consommation moyenne/).fill("6");
  await page.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.locator(".error")).toHaveText("Erreur 500");
});
