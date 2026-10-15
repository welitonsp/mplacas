// Matriz de captura visual (ADR-077): mesmas telas de `screenshots.spec.ts`
// em desktop, notebook e celular, nos dois temas. Uso:
//   npx playwright test -c playwright.matriz.config.ts
// As imagens saem em `e2e/capturas/<projeto>/`.
//
// `PW_CHROMIUM_PATH` aponta para um Chromium já instalado quando o ambiente
// não pode baixar navegadores (ex.: sandbox de agente). Chrome e Edge usam o
// mesmo motor (Chromium), então esta matriz cobre os dois. Firefox e Safari
// (WebKit) entram como projetos extras quando os navegadores estão instalados.
import { defineConfig, devices } from '@playwright/test'

import base from './playwright.config'

const chromium = process.env.PW_CHROMIUM_PATH
  ? { launchOptions: { executablePath: process.env.PW_CHROMIUM_PATH } }
  : {}

const desktop = { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, ...chromium }
const notebook = { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 720 }, ...chromium }
const tablet = { ...devices['Desktop Chrome'], viewport: { width: 820, height: 1180 }, hasTouch: true, ...chromium }
const celular = { ...devices['Pixel 7'], ...chromium }
const celularPequeno = { ...devices['Pixel 7'], viewport: { width: 360, height: 740 }, ...chromium }

const extras = process.env.PW_TODOS_NAVEGADORES
  ? [
      { name: 'firefox-claro', use: { ...devices['Desktop Firefox'], viewport: { width: 1440, height: 900 }, colorScheme: 'light' as const } },
      { name: 'safari-claro', use: { ...devices['Desktop Safari'], viewport: { width: 1440, height: 900 }, colorScheme: 'light' as const } },
      { name: 'iphone-escuro', use: { ...devices['iPhone 14'], colorScheme: 'dark' as const } },
    ]
  : []

export default defineConfig({
  ...base,
  testMatch: /(screenshots|overflow)\.spec\.ts/,
  projects: [
    { name: 'desktop-claro', use: { ...desktop, colorScheme: 'light' } },
    { name: 'desktop-escuro', use: { ...desktop, colorScheme: 'dark' } },
    { name: 'notebook-claro', use: { ...notebook, colorScheme: 'light' } },
    { name: 'tablet-escuro', use: { ...tablet, colorScheme: 'dark' } },
    { name: 'mobile-claro', use: { ...celular, colorScheme: 'light' } },
    { name: 'mobile-escuro', use: { ...celular, colorScheme: 'dark' } },
    { name: 'celular-360-claro', use: { ...celularPequeno, colorScheme: 'light' } },
    ...extras,
  ],
})
