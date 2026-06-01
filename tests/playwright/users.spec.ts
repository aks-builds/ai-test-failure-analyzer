import { test, expect } from '@playwright/test';

/**
 * User API Tests — NashLearn Demo
 * Target: jsonplaceholder.typicode.com (staging mock)
 *
 * ONE FAILURE simulates staging data drift after deployment:
 *   - User ID 9999 no longer exists → 404 (purged in v2.3.1 DB migration)
 */

// ── FAILING TEST ────────────────────────────────────────────────────────────
// Scenario: TEST_CONFIG.STAGING_USER_ID = 9999 was set before the v2.3.1
//           deployment which included a DB data migration that purged all
//           user records with ID > 1000 (inactive staging accounts).
//           Result: GET /users/9999 returns 404 Not Found.
test('get user by id from staging config', async ({ request }) => {
  const stagingUserId = 9999; // Stale config — user was purged in v2.3.1 DB migration

  const response = await request.get(`/users/${stagingUserId}`);

  // Expected: 200 with user profile
  // Actual:   404 — user_id 9999 no longer exists after DB migration
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
