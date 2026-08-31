import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { expect, type Page } from '@playwright/test';

/** The committed sample datasets — realistic data, not toy fixtures. */
export const SAMPLES_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../data/samples',
);

export function samplePath(name: string): string {
  return path.join(SAMPLES_DIR, name);
}

/** A unique account per test run, so runs never collide on the email index. */
export function uniqueAccount() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    fullName: 'Ada Lovelace',
    email: `e2e-${suffix}@example.com`,
    password: 'analytical-engine-1843',
  };
}

export async function register(page: Page, account = uniqueAccount()) {
  await page.goto('/register');
  await page.getByLabel('Full name').fill(account.fullName);
  await page.getByLabel('Email address').fill(account.email);
  await page.getByLabel('Password').fill(account.password);
  await page.getByRole('button', { name: /create account/i }).click();

  await expect(page).toHaveURL(/\/projects$/);
  return account;
}

export async function signIn(page: Page, account: { email: string; password: string }) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(account.email);
  await page.getByLabel('Password').fill(account.password);
  await page.getByRole('button', { name: /^sign in$/i }).click();
  await expect(page).toHaveURL(/\/projects$/);
}

export async function createProject(page: Page, name: string) {
  await page.getByRole('button', { name: /new project|create your first project/i }).first().click();

  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill(name);
  await dialog.getByRole('button', { name: /create project/i }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByRole('link', { name: new RegExp(name, 'i') })).toBeVisible();
}

/**
 * Upload a sample dataset and wait for the analysis to finish.
 *
 * The upload dialog navigates to the dataset on success, so the assertion is
 * the URL rather than an arbitrary timeout.
 */
export async function uploadDataset(page: Page, sample: string, displayName?: string) {
  await page.getByRole('button', { name: /^upload dataset$|^upload$/i }).first().click();

  const dialog = page.getByRole('dialog');
  await dialog.locator('input[type="file"]').setInputFiles(samplePath(sample));
  if (displayName) {
    await dialog.getByLabel('Display name').fill(displayName);
  }
  await dialog.getByRole('button', { name: /upload and analyse/i }).click();

  // Profiling, quality checks and the Isolation Forest all run in this request.
  await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]+/, { timeout: 60_000 });
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
}

/** Open one of the dataset tabs and wait for it to render. */
export async function openTab(page: Page, name: string) {
  await page.getByRole('link', { name: new RegExp(`^${name}`, 'i') }).click();
  await expect(page).toHaveURL(new RegExp(`/${name.toLowerCase()}$`));
}
