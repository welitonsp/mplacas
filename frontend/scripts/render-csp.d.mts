// Declarações para `render-csp.mjs`. O script é JavaScript puro de propósito:
// roda via `node` no passo de build, sem depender de compilação. O teste em
// `src/test/renderCsp.test.ts` é TypeScript e precisa destes tipos.
export declare const LEGACY_PLACEHOLDER: string
export declare const EXPECTED_CONNECT_SRC: string
export declare function assertSameOriginCsp(headers: string): void
export declare function assertNoLegacyApiUrl(env: Record<string, string | undefined>): void
