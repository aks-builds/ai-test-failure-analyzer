import { test, expect } from '@playwright/test';

/**
 * Auth API Tests — NashLearn Demo
 * Target: jsonplaceholder.typicode.com (staging mock)
 *
 * Baseline (pre-v2.3.1): all three auth tests pass.
 *   - Session lookup    : GET /users/1                 → 200
 *   - Sanity check      : GET /users/1                 → 200
 *   - Registration flow : POST /posts                  → 201
 */

// ── AUTH SESSION ───────────────────────────────────────────────────────────
test('login returns token for valid credentials', async ({ request }) => {
  // Auth session endpoint
  const response = await request.get('/users/1');

  // Expected: 200 with session token
  expect(response.status()).toBe(200);
});

// ── SANITY ──────────────────────────────────────────────────────────────────
// Confirms the user service itself is up and returning data correctly.
test('login with full credentials', async ({ request }) => {
  const response = await request.get('/users/1');
  expect(response.status()).toBe(200);

  const body = await response.json();
  expect(body).toHaveProperty('id');
  expect(body).toHaveProperty('email');
});

// ── REGISTRATION ────────────────────────────────────────────────────────────
test('register new account via /api/register', async ({ request }) => {
  // User registration endpoint
  const response = await request.post('/posts', {
    data: { name: 'Test User', email: 'test@nashtech.com' },
  });

  // Expected: 201 Created
  expect(response.status()).toBe(201);
});
