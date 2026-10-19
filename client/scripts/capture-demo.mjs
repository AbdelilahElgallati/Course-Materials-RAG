import { chromium } from 'playwright';
import { mkdir, rename } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const baseUrl = process.env.DEMO_URL ?? 'http://127.0.0.1:5173';
const outputDir = path.resolve(process.env.DEMO_OUTPUT ?? '../portfolio-assets');
const browserPath = process.env.CHROME_PATH;

await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  ...(browserPath ? { executablePath: browserPath } : {}),
});

const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: outputDir, size: { width: 1440, height: 1000 } },
});

const page = await context.newPage();

await page.route('**/api/**', async (route) => route.continue());
await page.route('http://localhost:8000/**', async (route) => {
  const url = new URL(route.request().url());

  if (url.pathname === '/') {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'healthy',
        database_loaded: true,
        llm_connected: true,
        device: 'cpu',
        embedding_model: 'paraphrase-multilingual-mpnet-base-v2',
        total_courses: 2,
        total_materials: 6,
      }),
    });
  }

  if (url.pathname === '/courses') {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'machine-learning',
          name: 'Machine Learning',
          description: 'Foundations of supervised and unsupervised learning.',
          category: 'Artificial Intelligence',
          materials_count: 4,
          created_at: '2026-10-19T10:00:00',
        },
        {
          id: 'data-science',
          name: 'Data Science',
          description: 'Practical data analysis and visualization.',
          category: 'Technology',
          materials_count: 2,
          created_at: '2026-10-19T10:05:00',
        },
      ]),
    });
  }

  if (url.pathname === '/stats') {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_courses: 2, total_materials: 6, total_chunks: 128 }),
    });
  }

  if (url.pathname === '/query') {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        answer: `## Core Types of Learning

| Type | Key idea | Typical output |
| --- | --- | --- |
| **Supervised Learning** | Learns from labeled examples | Regression or classification |
| **Unsupervised Learning** | Discovers structure without labels | Clusters, patterns, or embeddings |
| **Reinforcement Learning** | Learns through rewards and penalties | A policy for choosing actions |

The table is rendered with GitHub-Flavored Markdown and remains readable on smaller screens.`,
        sources: ['ML Course - Lecture 1.pdf', 'ML Course - Lecture 2.pdf'],
        processing_time: 1.24,
        num_chunks: 8,
      }),
    });
  }

  return route.continue();
});

await page.goto(baseUrl, { waitUntil: 'networkidle' });
await page.screenshot({
  path: path.join(outputDir, 'course-materials-dashboard.png'),
  fullPage: true,
});

const input = page.getByPlaceholder('Ask something about your courses...');
await input.fill('What are the core types of learning?');
await input.press('Enter');
await page.locator('.markdown-table-wrapper').waitFor();
await page.waitForTimeout(800);
await page.screenshot({
  path: path.join(outputDir, 'course-materials-markdown-table.png'),
  fullPage: true,
});

await context.close();
const recordedVideoPath = await page.video().path();
await browser.close();

if (recordedVideoPath) {
  const videoPath = path.join(outputDir, 'course-materials-demo.webm');
  await rename(recordedVideoPath, videoPath);
  console.log(`Video captured: ${videoPath}`);
}
console.log(`Screenshots captured in: ${outputDir}`);
