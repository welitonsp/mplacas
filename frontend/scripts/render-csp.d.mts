// Declarações para `render-csp.mjs`. O script é JavaScript puro de propósito:
// roda via `node` no passo de build, sem depender de compilação. O teste em
// `src/test/renderCsp.test.ts` é TypeScript e precisa destes tipos.
export declare const PLACEHOLDER: string
export declare function apiOrigin(rawUrl: string | undefined): string
export declare function renderHeaders(template: string, rawUrl: string | undefined): string
