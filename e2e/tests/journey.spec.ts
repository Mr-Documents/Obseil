import { expect, test } from '@playwright/test';

import { createProject, register, uploadDataset } from './helpers';

/**
 * The acceptance journey.
 *
 * One test, end to end, using the committed sample data rather than a
 * hand-made fixture: register, create a project, upload a real dataset, get a
 * score, read the findings, triage one, look at the ML anomalies, and export a
 * report. If this passes, the product does what it claims.
 */
test('a new user can go from sign-up to an exported report', async ({ page }, testInfo) => {
  const isMobile = testInfo.project.name === 'mobile';

  await test.step('register', async () => {
    await register(page);
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
  });

  await test.step('create a project', async () => {
    await createProject(page, 'Customer Transactions');
    await page.getByRole('link', { name: /customer transactions/i }).click();
    await expect(page.getByRole('heading', { name: 'Customer Transactions' })).toBeVisible();
  });

  await test.step('upload a dataset and analyse it', async () => {
    await uploadDataset(page, 'invalid_values.csv', 'March transactions');
    await expect(page.getByRole('heading', { name: /march transactions/i })).toBeVisible();
  });

  await test.step('see a quality score with its derivation', async () => {
    await expect(page.getByText('Dataset quality')).toBeVisible();
    // The meter's accessible name carries the score, so this asserts the
    // number and its accessibility in one go.
    await expect(page.getByRole('img', { name: /quality score .* out of 100/i })).toBeVisible();
    await expect(page.getByText('Where the points went')).toBeVisible();

    // The score must be explainable, not just displayed.
    await page.getByRole('button', { name: /why this score/i }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('Starting score')).toBeVisible();
    await expect(dialog.getByText('Final score')).toBeVisible();
    await dialog.getByRole('button', { name: /close dialog/i }).click();
    await expect(dialog).toBeHidden();
  });

  await test.step('see dataset statistics', async () => {
    await expect(page.getByText('Dataset details')).toBeVisible();
    await expect(page.getByText('Total cells')).toBeVisible();
    await expect(page.getByText('Issues by severity')).toBeVisible();
  });

  await test.step('inspect the findings', async () => {
    await page.getByRole('link', { name: /^findings/i }).click();
    await expect(page).toHaveURL(/\/findings$/);

    // invalid_values.csv is built to trigger the validity detectors.
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('button', { name: /negative values in/i }).first()).toBeVisible();
  });

  await test.step('open a finding and read all five answers', async () => {
    await page.getByRole('button', { name: /negative values in/i }).first().click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('What happened')).toBeVisible();
    await expect(dialog.getByText('Why it matters')).toBeVisible();
    await expect(dialog.getByText('How it was detected')).toBeVisible();
    await expect(dialog.getByText('What to do')).toBeVisible();
  });

  await test.step('triage the finding as a false positive', async () => {
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: /false positive/i }).click();

    await expect(page.getByText(/finding updated/i)).toBeVisible();
    await expect(dialog.getByText(/you marked this a/i)).toBeVisible();
    await dialog.getByRole('button', { name: /close dialog/i }).click();
  });

  await test.step('the triage is reflected in the filters', async () => {
    await page.getByRole('button', { name: /^ignored$/i }).click();
    await expect(page.getByRole('table').getByRole('row')).toHaveCount(2); // header + one
  });

  await test.step('inspect the ML anomalies', async () => {
    await page.getByRole('link', { name: /^anomalies/i }).click();
    await expect(page).toHaveURL(/\/anomalies$/);

    // Exact match: the method note below also names the algorithm.
    await expect(page.getByText('Isolation Forest', { exact: true })).toBeVisible();
    await expect(page.getByText('Rows flagged')).toBeVisible();
    // The honesty requirement, asserted rather than assumed.
    await expect(page.getByText(/does not know why/i)).toBeVisible();
  });

  await test.step('browse the raw rows', async () => {
    await page.getByRole('link', { name: /^rows/i }).click();
    await expect(page).toHaveURL(/\/rows$/);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByText(/of 450 rows/)).toBeVisible();
  });

  await test.step('explore the columns', async () => {
    await page.getByRole('link', { name: /^columns/i }).click();
    await expect(page).toHaveURL(/\/columns$/);

    await page.getByLabel('Search columns').fill('amount');
    await expect(page.getByRole('table').getByText('amount', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: /show statistics for amount/i }).click();
    await expect(page.getByText('Std. deviation')).toBeVisible();
  });

  await test.step('export a report', async () => {
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: /^export$/i }).click();
    await page.getByRole('menuitem', { name: /full report/i }).click();

    const file = await download;
    expect(file.suggestedFilename()).toMatch(/^obseil-.*\.pdf$/);
  });

  if (!isMobile) {
    await test.step('nothing scrolls the page sideways', async () => {
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    });
  }
});
