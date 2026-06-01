import { test, expect } from '@playwright/test';

/**
 * User API Tests — NashLearn Demo
 * Target: jsonplaceholder.typicode.com (staging mock)
 *
 * Baseline (pre-v2.3.1): all three user tests pass.
 *   - Staging user lookup   : GET /users/5            → 200
 *   - List users (paginated) : GET /users?_limit=5    → 200
 *   - Known user profile     : GET /users/2          → 200
 */

// ── STAGING USER LOOKUP ─────────────────────────────────────────────────────
test('get user by id from staging config', async ({ request }) => {
  const stagingUserId = 5; // active staging account in current DB snapshot

  const response = await request.get(`/users/${stagingUserId}`);

  // Expected: 200 with user profile
  expect(response.status()).toBe(200);
});

// ── PASSING TEST 1 ──────────────────────────────────────────────────────────
test('list users returns paginated data', async ({ request }) => {
  const response = await request.get('/users?_limit=5');
  expect(response.status()).toBe(200);

  const body = await response.json();
  expect(Array.isArray(body)).toBe(true);
  expect(body.length).toBeGreaterThan(0);
});

// ── PASSING TEST 2 ──────────────────────────────────────────────────────────
test('get known user by id returns user profile', async ({ request }) => {
  const response = await request.get('/users/2');
  expect(response.status()).toBe(200);

  const body = await response.json();
  expect(body.id).toBe(2);
  expect(body).toHaveProperty('email');
  expect(body).toHaveProperty('name');
});
