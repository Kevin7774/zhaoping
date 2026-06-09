import { test, expect } from 'playwright/test';
test('smoke', async ({ page }) => { await page.goto('http://127.0.0.1:5178/'); await expect(page).toHaveTitle(/Vite|React|机器人|招聘/i); });
