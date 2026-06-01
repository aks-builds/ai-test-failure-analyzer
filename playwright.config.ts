import { defineConfig } from '@playwright/test';

/**
 * Playwright configuration for AI-Assisted Test Failure Analysis demo.
 * API tests against jsonplaceholder.typicode.com (public REST API, no auth required).
 * Reporters: list (stdout) + JSON + JUnit (written to test-results/)
 */
export default defineConfig({
  testDir: './tests/playwright',

  // Single worker — sequential execution, easier to follow in a live demo
  workers: 1,

  // list streams to stdout; json and junit are read by the AI analyzer
  reporter: [
    ['list'],
    ['json',  { outputFile: 'test-results/results.json' }],
    ['junit', { outputFile: 'test-results/results.xml'  }],
  ],

  use: {
    baseURL: 'https://jsonplaceholder.typicode.com',
    extraHTTPHeaders: {
      'Accept':       'application/json',
      'Content-Type': 'application/json',
    },
  },

  timeout: 15_000,
});
