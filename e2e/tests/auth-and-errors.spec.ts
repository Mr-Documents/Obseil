import { expect, test } from '@playwright/test';

import { createProject, register, samplePath, signIn, uniqueAccount } from './helpers';

test.describe('authentication', () => {
  test('rejects a wrong password without revealing whether the account exists', async ({
    page,
  }) => {
    const account = await register(page);
    await page.getByRole('button', { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel('Email address').fill(account.email);
    await page.getByLabel('Password').fill('definitely-the-wrong-one-1');
    await page.getByRole('button', { name: /^sign in$/i }).click();

    const knownAccount = await page.getByRole('alert').textContent();
    expect(knownAccount).toMatch(/incorrect email or password/i);

    await page.getByLabel('Email address').fill('nobody-at-all@example.com');
    await page.getByRole('button', { name: /^sign in$/i }).click();

    // Identical wording, so the form cannot be used to enumerate accounts.
    await expect(page.getByRole('alert')).toHaveText(knownAccount as string);
  });

  test('sends an anonymous visitor to sign in, then back where they were going', async ({
    page,
  }) => {
    const account = uniqueAccount();
    await register(page, account);
    await createProject(page, 'Warehouse Exports');

    const projectUrl = await page
      .getByRole('link', { name: /warehouse exports/i })
      .getAttribute('href');

    await page.getByRole('button', { name: /sign out/i }).click();
    await page.goto(projectUrl as string);
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel('Email address').fill(account.email);
    await page.getByLabel('Password').fill(account.password);
    await page.getByRole('button', { name: /^sign in$/i }).click();

    await expect(page).toHaveURL(new RegExp(`${projectUrl}$`));
    await expect(page.getByRole('heading', { name: 'Warehouse Exports' })).toBeVisible();
  });

  test('keeps the session across a reload', async ({ page }) => {
    await register(page);
    await page.reload();

    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
  });

  test('rejects a weak password before contacting the server', async ({ page }) => {
    await page.goto('/register');
    await page.getByLabel('Full name').fill('Ada Lovelace');
    await page.getByLabel('Email address').fill('weak@example.com');
    await page.getByLabel('Password').fill('short');
    await page.getByRole('button', { name: /create account/i }).click();

    await expect(page.getByText(/use at least 8 characters/i)).toBeVisible();
    await expect(page).toHaveURL(/\/register$/);
  });
});

test.describe('errors the user can actually hit', () => {
  test('explains an unsupported file type instead of failing silently', async ({ page }) => {
    await register(page);
    await createProject(page, 'Uploads');
    await page.getByRole('link', { name: /uploads/i }).click();

    await page.getByRole('button', { name: /^upload dataset$/i }).click();
    const dialog = page.getByRole('dialog');

    // A dropped file bypasses the input's `accept`, so this is the path that
    // actually needs the client-side check.
    await dialog.locator('input[type="file"]').setInputFiles({
      name: 'notes.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 not really'),
    });

    await expect(dialog.getByRole('alert')).toContainText(/not one of them/i);
  });

  test('reports a file it cannot parse without exposing a stack trace', async ({ page }) => {
    await register(page);
    await createProject(page, 'Uploads');
    await page.getByRole('link', { name: /uploads/i }).click();

    await page.getByRole('button', { name: /^upload dataset$/i }).click();
    const dialog = page.getByRole('dialog');
    await dialog.locator('input[type="file"]').setInputFiles({
      name: 'header-only.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('id,amount,category\n'),
    });
    await dialog.getByRole('button', { name: /upload and analyse/i }).click();

    const alert = dialog.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/no data rows|empty/i);
    await expect(alert).not.toContainText(/Traceback|File "|Exception/);
  });

  test('another account cannot open your project by guessing the URL', async ({ page }) => {
    await register(page);
    await createProject(page, 'Private Project');
    const projectUrl = await page
      .getByRole('link', { name: /private project/i })
      .getAttribute('href');

    await page.getByRole('button', { name: /sign out/i }).click();
    const intruder = await register(page, uniqueAccount());
    expect(intruder.email).toBeTruthy();

    await page.goto(projectUrl as string);

    await expect(page.getByText(/project not found/i)).toBeVisible();
    await expect(page.getByText(/may not have access/i)).toBeVisible();
  });

  test('shows a useful 404 for an unknown route', async ({ page }) => {
    await page.goto('/this-route-does-not-exist');

    await expect(page.getByRole('heading', { name: /couldn.t find that page/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /back to obseil/i })).toBeVisible();
  });

  test('an empty project explains what to do next', async ({ page }) => {
    await register(page);

    await expect(page.getByText(/no projects yet/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /create your first project/i })).toBeVisible();
  });
});

test.describe('a clean dataset', () => {
  test('scores well and says nothing is wrong', async ({ page }) => {
    await register(page);
    await createProject(page, 'Clean Data');
    await page.getByRole('link', { name: /clean data/i }).click();

    await page.getByRole('button', { name: /^upload dataset$/i }).click();
    const dialog = page.getByRole('dialog');
    await dialog.locator('input[type="file"]').setInputFiles(samplePath('clean_transactions.csv'));
    await dialog.getByRole('button', { name: /upload and analyse/i }).click();

    await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]+/, { timeout: 60_000 });
    await expect(page.getByText('Excellent')).toBeVisible();

    await page.getByRole('link', { name: /^findings/i }).click();
    // No deterministic finding fires on the clean fixture; the unsupervised
    // model may still surface a handful of candidates, which is expected.
    await page.getByRole('button', { name: /^critical$/i }).click();
    await expect(page.getByText(/no findings match these filters/i)).toBeVisible();
  });
});
