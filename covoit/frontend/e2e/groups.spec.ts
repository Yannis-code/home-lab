import { expect, test } from "./fixtures";
import {
  addRecurringParticipant,
  adminToken,
  createGroup,
  createRecurringModel,
  createUser,
  gotoHash,
  inviteAndJoin,
  seedToken,
} from "./helpers";

test("creator becomes manager, member and default driver", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  await seedToken(page, alice.token);
  await gotoHash(page, "/#/groups");
  await expect(page.getByText("Aucun groupe pour le moment.")).toBeVisible();

  await page.getByLabel("Nom du groupe").fill("   ");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator(".error")).toBeVisible();

  await page.getByLabel("Nom du groupe").fill("Trajet boulot");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/#\/groups\/\d+$/);
  await expect(page.getByRole("heading", { name: "Trajet boulot" })).toBeVisible();
  await expect(page.getByText(`Gestionnaire : ${alice.name}`)).toBeVisible();
  await expect(page.getByText(`Conducteur par défaut : ${alice.name}`)).toBeVisible();
  await expect(page.locator(".badge", { hasText: "gestionnaire" })).toBeVisible();
  await expect(page.locator(".badge", { hasText: "conducteur par défaut" })).toBeVisible();
});

test("invitation must be accepted before membership is active", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByLabel("Inviter un utilisateur (recherche par nom)").fill(bob.name);
  await page.getByRole("button", { name: "Rechercher" }).click();
  await page.getByRole("button", { name: "Inviter" }).click();
  await expect(page.getByRole("button", { name: "Invité" })).toBeDisabled();

  await seedToken(page, bob.token);
  await gotoHash(page, "/#/groups");
  await expect(page.getByText("Invitations en attente")).toBeVisible();
  await page.getByRole("button", { name: "Accepter" }).click();
  await expect(page.getByRole("link", { name: "Trajet boulot" })).toBeVisible();
});

test("declining an invitation removes it from the list", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByLabel("Inviter un utilisateur (recherche par nom)").fill(bob.name);
  await page.getByRole("button", { name: "Rechercher" }).click();
  await page.getByRole("button", { name: "Inviter" }).click();

  await seedToken(page, bob.token);
  await gotoHash(page, "/#/groups");
  await page.getByRole("button", { name: "Refuser" }).click();
  await expect(page.getByText("Invitations en attente")).toHaveCount(0);
});

test("sole manager cannot leave the group", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");
  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByRole("button", { name: "Quitter le groupe" }).click();
  await expect(page.locator(".error")).toBeVisible();
});

test("manager can transfer management then leave, and default driver clears when they left", async ({
  page,
}) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByLabel("Transférer la gestion à").selectOption({ label: bob.name });
  await page.getByRole("button", { name: "Transférer" }).click();
  await expect(page.getByText(`Gestionnaire : ${bob.name}`)).toBeVisible();

  await page.getByRole("button", { name: "Quitter le groupe" }).click();
  await expect(page).toHaveURL(/#\/groups$/);

  await seedToken(page, bob.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await expect(page.getByText("Conducteur par défaut : aucun")).toBeVisible();
});

test("any active member can change the default driver", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);

  await seedToken(page, bob.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await expect(page.getByRole("button", { name: "Transférer" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Archiver le groupe" })).toHaveCount(0);
  await page.getByLabel("Conducteur par défaut").selectOption({ label: bob.name });
  await page.getByRole("button", { name: "Changer" }).click();
  await expect(page.getByText(`Conducteur par défaut : ${bob.name}`)).toBeVisible();
});

test("only the manager can archive the group, then actions disappear", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByRole("button", { name: "Archiver le groupe" }).click();
  await expect(page.locator(".badge", { hasText: "archivé" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Quitter le groupe" })).toHaveCount(0);
});

test("groups list shows the archived badge", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const group = await createGroup(alice.token, "Trajet boulot");
  await createGroup(alice.token, "Trajet piscine");

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByRole("button", { name: "Archiver le groupe" }).click();

  await gotoHash(page, "/#/groups");
  const archivedRow = page.locator("li", { hasText: "Trajet boulot" });
  await expect(archivedRow.getByText("archivé")).toBeVisible();
  const activeRow = page.locator("li", { hasText: "Trajet piscine" });
  await expect(activeRow.getByText("archivé")).toHaveCount(0);
});

test("a proposed recurring trip can be accepted from the groups list", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);
  const model = await createRecurringModel(alice.token, group.id, {
    name: "Matin",
    origin: "Maison",
    destination: "Travail",
    weekdays: [0, 1, 2, 3, 4],
    time_of_day: "08:00",
  });
  await addRecurringParticipant(alice.token, model.id, bob.id);

  await seedToken(page, bob.token);
  await gotoHash(page, "/#/groups");
  await expect(page.getByText("Trajets récurrents proposés")).toBeVisible();
  await expect(page.getByText("Matin")).toBeVisible();
  await page.getByRole("button", { name: "Accepter" }).click();
  await expect(page.getByText("Trajets récurrents proposés")).toHaveCount(0);
});

test("inviting the same person twice is rejected by the backend", async ({ page }) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);
  await page.getByLabel("Inviter un utilisateur (recherche par nom)").fill(bob.name);
  await page.getByRole("button", { name: "Rechercher" }).click();
  await page.getByRole("button", { name: "Inviter" }).click();
  await expect(page.getByRole("button", { name: "Invité" })).toBeDisabled();

  await page.reload();
  await page.getByLabel("Inviter un utilisateur (recherche par nom)").fill(bob.name);
  await page.getByRole("button", { name: "Rechercher" }).click();
  await page.getByRole("button", { name: "Inviter" }).click();
  await expect(page.locator(".error")).toBeVisible();
});

test("default-driver change, management transfer and archive show an error when the request fails", async ({
  page,
}) => {
  const admin = await adminToken();
  const alice = await createUser(admin, "Alice");
  const bob = await createUser(admin, "Bob");
  const group = await createGroup(alice.token, "Trajet boulot");
  await inviteAndJoin(alice.token, group.id, bob);

  await seedToken(page, alice.token);
  await gotoHash(page, `/#/groups/${group.id}`);

  await page.route("**/default-driver", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await page.getByLabel("Conducteur par défaut").selectOption({ label: bob.name });
  await page.getByRole("button", { name: "Changer" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await page.unroute("**/default-driver");

  await page.route("**/transfer-management", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await page.getByLabel("Transférer la gestion à").selectOption({ label: bob.name });
  await page.getByRole("button", { name: "Transférer" }).click();
  await expect(page.getByText(`Gestionnaire : ${bob.name}`)).toHaveCount(0);
  await page.unroute("**/transfer-management");

  await page.route("**/archive", async (route) => {
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Erreur" }) });
  });
  await page.getByRole("button", { name: "Archiver le groupe" }).click();
  await expect(page.locator(".badge", { hasText: "archivé" })).toHaveCount(0);
});
