/**
 * MealDrama Household Demo — Automated Playwright walkthrough
 *
 * Launches two browser contexts (roommate A + B), walks through the full
 * household feature, and takes screenshots at every step.
 *
 * Usage:
 *   node scripts/household-demo.mjs
 *
 * Requires:
 *   - Vite dev server running on port 3000
 *   - Express backend running on port 3001
 *   - Playwright installed in project root
 */

import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const OUT_DIR = join(__dirname, '..', 'household-demo-screenshots');
const BASE_URL = 'http://localhost:3000';

mkdirSync(OUT_DIR, { recursive: true });

let shotIndex = 0;

async function shot(page, name) {
  const idx = String(++shotIndex).padStart(2, '0');
  const path = join(OUT_DIR, `${idx}-${name}.png`);
  await page.screenshot({ path, fullPage: true });
  console.log(`  📸 ${path}`);
}

async function waitForApp(page) {
  await page.waitForSelector('text=Get Started', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2000);
}

async function createBetaAccount(page, displayName = 'Prateek') {
  // Click "Create Beta Account" button
  const createBtn = page.locator('text=Create Beta Account');
  if (await createBtn.isVisible().catch(() => false)) {
    await createBtn.click();
    await page.waitForTimeout(2000);
  }

  // "Pick your handle" screen — type a name
  const handleInput = page.locator('input').first();
  if (await handleInput.isVisible().catch(() => false)) {
    await handleInput.fill(displayName);
    await page.waitForTimeout(500);
    await page.locator('text=Start Planning').click();
    await page.waitForTimeout(2000);
  }

  // FlashOnboarding: 4 steps — tap through with selections
  // Step 1: Region — select first option
  const firstOption = page.locator('button:has(img), button').filter({ hasText: /India/ }).first();
  if (await firstOption.isVisible().catch(() => false)) {
    await firstOption.click();
    await page.waitForTimeout(500);
    await page.locator('text=Next').click();
    await page.waitForTimeout(1500);
  }

  // Step 2: Diet — select first option
  const dietBtn = page.locator('button').filter({ hasText: /Veg|Egg|Non-Veg|Vegan/ }).first();
  if (await dietBtn.isVisible().catch(() => false)) {
    await dietBtn.click();
    await page.waitForTimeout(500);
    await page.locator('text=Next').click();
    await page.waitForTimeout(1500);
  }

  // Step 3: Health Goal — select first option
  const healthBtn = page.locator('button').filter({ hasText: /Balanced|High Protein/ }).first();
  if (await healthBtn.isVisible().catch(() => false)) {
    await healthBtn.click();
    await page.waitForTimeout(500);
    await page.locator('text=Next').click();
    await page.waitForTimeout(1500);
  }

  // Step 4: Cook Phone — type a number or tap Let's Go
  const letsGoBtn = page.locator('text=Let\'s Go');
  if (await letsGoBtn.isVisible().catch(() => false)) {
    // Try typing a phone number first
    const phoneInput = page.locator('input').last();
    if (await phoneInput.isVisible().catch(() => false)) {
      await phoneInput.fill('+911234567890');
      await page.waitForTimeout(500);
    }
    await letsGoBtn.click();
    await page.waitForTimeout(5000);
  }

  // Wait for main UI to load (auto-seeding tray + loop config)
  await page.waitForTimeout(5000);
}

async function login(page, displayName = 'Prateek') {
  await page.goto(BASE_URL);
  await page.waitForTimeout(3000);

  // Check if we already have an account (shown by tab bar)
  const tabBar = page.locator('nav[role="navigation"]');
  if (await tabBar.isVisible().catch(() => false)) {
    console.log('  ✅ Already logged in');
    return;
  }

  // Create beta account
  await createBetaAccount(page, displayName);

  // Wait for main UI to load
  await page.waitForTimeout(3000);
}

async function clickTab(page, tabName) {
  const tab = page.locator('nav[role="navigation"] button').filter({ hasText: tabName });
  if (await tab.isVisible().catch(() => false)) {
    await tab.click();
    await page.waitForTimeout(2000);
    return true;
  }
  return false;
}

async function main() {
  console.log('🧪 MealDrama Household Demo — Playwright Walkthrough\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, // iPhone 14 Pro size
    deviceScaleFactor: 2,
  });

  try {
    // ─── SCENE 1: Prateek creates household ───
    console.log('📍 Scene 1: User A (Prateek) registers and creates household');
    const pageA = await context.newPage();
    await login(pageA, 'Prateek');
    await shot(pageA, 'a1-app-launch');

    // Navigate to Profile tab
    await clickTab(pageA, 'Profile');
    await shot(pageA, 'a2-profile-tab');

    // Create household
    const createBtn = pageA.locator('text=Create');
    if (await createBtn.isVisible().catch(() => false)) {
      await createBtn.click();
      await pageA.waitForTimeout(1000);
      // Fill household name
      const nameInput = pageA.locator('input').first();
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill("Prateek's Kitchen");
        await pageA.locator('text=Create, text=Submit, text=Done').first().click().catch(() => {});
        await pageA.waitForTimeout(2000);
      }
    }
    await shot(pageA, 'a3-household-created');

    // Get invite code
    let inviteCode = '';
    const codeEl = pageA.locator('text=/[A-Z0-9]{6,8}/').last();
    inviteCode = (await codeEl.textContent().catch(() => '')) || '';
    console.log(`  🔑 Invite code: ${inviteCode || '(read from screen)'}`);

    // Show member list
    await shot(pageA, 'a4-member-list');

    // Show the invite modal (share code)
    const inviteBtn = pageA.locator('text=Invite');
    if (await inviteBtn.isVisible().catch(() => false)) {
      await inviteBtn.click();
      await pageA.waitForTimeout(1000);
      await shot(pageA, 'a5-invite-modal');
      // Close modal
      await pageA.keyboard.press('Escape');
      await pageA.waitForTimeout(500);
    }

    // ─── SCENE 2: Alex joins via code ───
    console.log('\n📍 Scene 2: User B (Alex) joins household');
    const contextB = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
    });
    const pageB = await contextB.newPage();
    await login(pageB, 'Alex');

    // Navigate to Profile
    await clickTab(pageB, 'Profile');
    await pageB.waitForTimeout(1000);
    await shot(pageB, 'b1-profile-empty');

    // Join household
    const joinBtn = pageB.locator('text=Join');
    if (await joinBtn.isVisible().catch(() => false)) {
      await joinBtn.click();
      await pageB.waitForTimeout(1000);
      // Enter invite code
      const codeInput = pageB.locator('input').first();
      if (await codeInput.isVisible().catch(() => false)) {
        await codeInput.fill(inviteCode || 'TEST123');
        await pageB.locator('text=Join, text=Submit, text=Done').first().click().catch(() => {});
        await pageB.waitForTimeout(2000);
      }
    }
    await shot(pageB, 'b2-joined-household');

    // ─── SCENE 3: Both users view the Plan with meal attribution ───
    console.log('\n📍 Scene 3: Both users view the meal plan with meal attribution');

    // Go to Plan tab on both to see meal cards with requestedBy labels
    await clickTab(pageA, 'Plan');
    await pageA.waitForTimeout(1000);
    await shot(pageA, 'a6-plan');

    await clickTab(pageB, 'Plan');
    await pageB.waitForTimeout(1000);
    await shot(pageB, 'b3-plan');

    // ─── SCENE 4: Pantry consolidated view ───

    // ─── SCENE 4: Pantry consolidated view ───
    console.log('\n📍 Scene 4: Pantry with Household tab');

    // Go to Pantry tab on Prateek's view
    await clickTab(pageA, 'Pantry');
    await pageA.waitForTimeout(1000);
    await shot(pageA, 'a7-pantry');

    // Try to click "All Members" tab
    const allMembersTab = pageA.locator('text=/All Members/');
    if (await allMembersTab.isVisible().catch(() => false)) {
      await allMembersTab.click();
      await pageA.waitForTimeout(4000);
      await shot(pageA, 'a8-pantry-all-members');
    } else {
      const hasError = await pageA.locator('text=is not defined').isVisible().catch(() => false);
      if (hasError) {
        console.log('  ⚠️  Pantry has JS error');
        await shot(pageA, 'a7-pantry-error');
      }
    }

    // ─── SCENE 5: Household section with expenses ───
    console.log('\n📍 Scene 5: Household section with activity feed');

    // Go back to Profile on Prateek's view
    await clickTab(pageA, 'Profile');
    await pageA.waitForTimeout(1000);
    await shot(pageA, 'a9-profile-household');

    // Expand Household section (collapsible — closed by default)
    const householdSection = pageA.locator('text=Household');
    if (await householdSection.isVisible().catch(() => false)) {
      await householdSection.click();
      await pageA.waitForTimeout(1000);
    }

    // Try to expand Expenses (inside the expanded Household section)
    const expensesSection = pageA.locator('text=Expenses');
    if (await expensesSection.isVisible().catch(() => false)) {
      await expensesSection.click();
      await pageA.waitForTimeout(1000);
    }
    await shot(pageA, 'a10-expenses');

    // ─── SCENE 6: Alex sees the same household ───
    console.log('\n📍 Scene 6: Alex confirms household membership');
    await clickTab(pageB, 'Profile');
    await pageB.waitForTimeout(1000);
    await shot(pageB, 'b4-profile-household');

    console.log(`\n✅ Done! ${shotIndex} screenshots saved to ${OUT_DIR}`);
    console.log('📁 Open the folder and double-click any .png to view.');

    await contextB.close();
  } catch (err) {
    console.error('❌ Error:', err.message);
    // Take an error screenshot if possible
    try {
      await shot(pageA, 'error-state');
    } catch (_) {}
  } finally {
    await context.close();
    await browser.close();
  }
}

main();
