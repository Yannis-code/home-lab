import fs from "node:fs";
import path from "node:path";

import { test as base } from "@playwright/test";

const outputDir = path.join(process.cwd(), ".nyc_output");
const STORAGE_KEY = "__covoit_coverage_backup__";

// De nombreux tests changent d'identité via un rechargement complet de page
// (gotoHash/page.reload), ce qui réinitialise window.__coverage__ à chaque
// fois. Ce script restaure la couverture précédente avant que les modules
// instrumentés ne s'initialisent (istanbul réutilise l'objet existant si son
// hash correspond), et la sauvegarde dans sessionStorage juste avant que la
// page ne se décharge, afin qu'aucune couverture ne soit perdue entre deux
// chargements au sein d'un même test.
const PERSIST_COVERAGE_SCRIPT = `
  (() => {
    const key = ${JSON.stringify(STORAGE_KEY)};
    try {
      const backup = window.sessionStorage.getItem(key);
      if (backup) {
        window.__coverage__ = JSON.parse(backup);
      }
    } catch {
      // sessionStorage indisponible ou backup corrompu: on repart d'une couverture vide.
    }
    window.addEventListener("pagehide", () => {
      try {
        window.sessionStorage.setItem(key, JSON.stringify(window.__coverage__ || {}));
      } catch {
        // stockage plein ou indisponible: la couverture de cette page sera simplement perdue.
      }
    });
  })();
`;

export const test = base.extend<{ collectCoverage: void }>({
  collectCoverage: [
    async ({ page }, use, testInfo) => {
      await page.addInitScript(PERSIST_COVERAGE_SCRIPT);
      await use();
      const coverage = await page.evaluate(
        () => (window as unknown as { __coverage__?: object }).__coverage__
      );
      if (coverage) {
        fs.mkdirSync(outputDir, { recursive: true });
        const file = path.join(outputDir, `coverage-${testInfo.testId}-${Date.now()}.json`);
        fs.writeFileSync(file, JSON.stringify(coverage));
      }
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
