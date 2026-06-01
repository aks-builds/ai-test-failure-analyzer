import { test, expect } from '@playwright/test';

/**
 * Auth API Tests — NashLearn Demo
 * Target: jsonplaceholder.typicode.com (staging mock)
 *
 * FAILURES simulate post-deployment regressions in the auth-service:
 *   - Auth session endpoint now returns 404 (endpoint path renamed in v2.3.1)
 *   - Registration endpoint now returns 404 (moved to a new route in v2.3.1)
 */

// ── FAILING TEST 1 ─────────────────────────────────────────────────────────
// Scenario: auth_service.py was refactored in v2.3.1 and the session endpoint
//           was renamed from /auth/session → /auth/v2/session.
//           The test config still points at the old path → 404 Not Found.
test('login returns token for valid credentials', async ({ request }) => {
  // Old endpoint path — renamed during v2.3.1 service refactor
  const response = await request.get('/auth/session');

  // Expected: 200 with session token
  // Actual:   404 — endpoint path changed in v2.3.1 deployment
  expect(response.status()).toBe(200);
});

// ── PASSING TEST ────────────────────────────────────────────────────────────
// Confirms the user service itself is up and returning data correctly.
test('login with full credentials', async ({ request }) => {
  const response = await request.get('/users/1');
  expect(response.status()).toBe(200);

  const body = await response.json();
  expect(body).toHaveProperty('id');
  expect(body).toHaveProperty('email');
});

// ── FAILING TEST 2 ─────────────────────────────────────────────────────────
// Scenario: User registration route was restructured in v2.3.1.
//           Old path /register/users no longer exists (404).
//           New path is /auth/v2/register — test config not updated.
test('register new account via /api/register', async ({ request }) => {
  // Old registration endpoint — moved during v2.3.1 API restructuring
  const response = await request.post('/register/users', {
    data: { name: 'Test User', email: 'test@nashtech.com' },
  });

  // Expected: 201 Created
  // Actual:   404 — endpoint path changed in v2.3.1 deployment
  expect(response.status()).toBe(201);
});
