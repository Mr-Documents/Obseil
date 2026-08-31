import fs from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { createProject, register, samplePath, uploadDataset } from './helpers';

/**
 * Captures the product's main screens for design review.
 *
 * Not an assertion suite - it exists so a person can look at every screen in
 * both themes without clicking through the app by hand. Run it deliberately:
 *
 *     OBSEIL_CAPTURE=1 npx playwright test screenshots --project=chromium
 *     OBSEIL_CAPTURE=1 npx playwright test screenshots --project=mobile
 *
 * Skipped by default so it does not slow the real suite down.
 */
const OUTPUT = path.resolve('screenshots');
const CAPTURE = process.env.OBSEIL_CAPTURE === '1';

test.describe('design review captures', () => {
  test.skip(!CAPTURE, 'Set OBSEIL_CAPTURE=1 to capture screenshots.');
  test.setTimeout(180_000);

  test('capture every main screen in both themes', async ({ page }, testInfo) => {
    fs.mkdirSync(OUTPUT, { recursive: true });
    const suffix = testInfo.project.name === 'mobile' ? 'mobile' : 'desktop';

    async function shot(name: string) {
      await page.waitForTimeout(400); // let charts settle
      await page.screenshot({
        path: path.join(OUTPUT, `${suffix}-${name}.png`),
        fullPage: true,
      });
    }

    await page.goto('/');
    await shot('01-landing');

    await page.goto('/register');
    await shot('02-register');

    await register(page);
    await shot('03-projects-empty');

    await createProject(page, 'Customer Transactions');
    await page.getByRole('link', { name: /customer transactions/i }).click();
    await shot('04-project-empty');

    await uploadDataset(page, 'invalid_values.csv', 'March transactions');
    await shot('05-dataset-overview');

    await page.getByRole('link', { name: /^findings/i }).click();
    await shot('06-findings');

    await page
      .getByRole('button', { name: /outlying values in/i })
      .first()
      .click();
    await shot('07-finding-detail');
    await page
      .getByRole('dialog')
      .getByRole('button', { name: /close dialog/i })
      .click();

    await page.getByRole('link', { name: /^anomalies/i }).click();
    await shot('08-anomalies');

    await page.getByRole('link', { name: /^columns/i }).click();
    await page.getByRole('button', { name: /show statistics for amount/i }).click();
    await shot('09-columns');

    await page.getByRole('link', { name: /^rows/i }).click();
    await shot('10-rows');

    // A second dataset so the history has something to compare against.
    await page.getByRole('link', { name: /back to project/i }).click();
    await page
      .getByRole('button', { name: /^upload$/i })
      .first()
      .click();
    const dialog = page.getByRole('dialog');
    await dialog.locator('input[type="file"]').setInputFiles(samplePath('clean_transactions.csv'));
    await dialog.getByRole('button', { name: /upload and analyse/i }).click();
    await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]+/, { timeout: 60_000 });
    await shot('11-dataset-clean');

    await page.getByRole('link', { name: /back to project/i }).click();
    await page.getByRole('link', { name: /^history$/i }).click();
    await page
      .getByRole('button', { name: /^compare$/i })
      .first()
      .click();
    await shot('12-history-comparison');

    // Everything again in the dark theme. Below `lg` the account panel that
    // holds the toggle lives in the navigation drawer, so open it first.
    const menu = page.getByRole('button', { name: /open navigation menu/i });
    if (await menu.isVisible()) {
      await menu.click();
    }
    await page.getByRole('button', { name: /switch to dark theme/i }).click();
    if (
      await page
        .getByRole('button', { name: /close navigation menu/i })
        .first()
        .isVisible()
    ) {
      await page.keyboard.press('Escape');
    }
    await shot('13-history-dark');

    await page.goBack();
    await page.goto(page.url());
    await shot('14-project-dark');
  });
});
