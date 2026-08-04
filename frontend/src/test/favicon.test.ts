import { describe, expect, it } from 'vitest'

// P2-10 na auditoria de UI/UX: `index.html` referenciava `/vite.svg`, que não
// existia em `public/` nem em `dist/` — favicon 404. Este teste confirma que
// (a) a referência ao arquivo inexistente foi removida e (b) o arquivo
// referenciado pelo `<link rel="icon">` existe de fato em `public/` (fonte
// copiada para `dist/` pelo Vite no build) — sem `node:fs`, usando
// `import.meta.glob` como o resto da suíte (ver `colorContrast.test.tsx`).
const indexHtmlSources = import.meta.glob('../../index.html', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const indexHtmlSource = Object.values(indexHtmlSources)[0]

const publicFiles = import.meta.glob('../../public/*', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, unknown>

describe('favicon (Etapa 1.6a)', () => {
  it('index.html existe e não referencia mais /vite.svg (inexistente)', () => {
    expect(indexHtmlSource).toBeDefined()
    expect(indexHtmlSource).not.toMatch(/vite\.svg/)
  })

  it('o <link rel="icon"> aponta para um arquivo que existe em public/', () => {
    const match = indexHtmlSource.match(/<link rel="icon"[^>]*href="\/([^"]+)"/)
    expect(match).not.toBeNull()

    const iconFileName = match![1]
    const matchingPublicFile = Object.keys(publicFiles).some((path) => path.endsWith(`/public/${iconFileName}`))
    expect(matchingPublicFile).toBe(true)
  })
})
