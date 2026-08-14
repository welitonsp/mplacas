import { afterEach, describe, expect, it, vi } from 'vitest'
import { safeStorage } from './storage'

// Achado A-04 da auditoria v6. O cenário não é hipotético: navegador em modo
// restrito, cota esgotada e bloqueio de armazenamento em contexto embutido
// fazem a API de `localStorage` LANÇAR, não devolver vazio.
//
// O ponto mais perigoso era `main.tsx`, que apagava uma credencial legada FORA
// do `try` do bootstrap — uma exceção ali derrubava o app antes do root
// renderizar, quando nem a tela de erro existe. O usuário via página em branco
// por causa de uma limpeza de higiene que nem precisava dar certo.
function stubThrowingStorage() {
  const boom = () => {
    throw new DOMException('acesso negado', 'SecurityError')
  }
  Object.defineProperty(window, 'localStorage', {
    value: { getItem: boom, setItem: boom, removeItem: boom },
    configurable: true,
    writable: true,
  })
}

describe('safeStorage — armazenamento indisponível não derruba a aplicação', () => {
  const original = Object.getOwnPropertyDescriptor(window, 'localStorage')

  afterEach(() => {
    if (original) Object.defineProperty(window, 'localStorage', original)
    vi.restoreAllMocks()
  })

  it('leitura devolve null em vez de lançar', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    stubThrowingStorage()

    expect(() => safeStorage.get('qualquer')).not.toThrow()
    expect(safeStorage.get('qualquer')).toBeNull()
  })

  // `null` é o MESMO contrato de "chave inexistente", que todo consumidor já
  // trata — por isso a degradação não exige ramo novo em nenhum chamador.
  it('leitura indisponível é indistinguível de chave ausente para o consumidor', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const ausente = safeStorage.get('chave-que-nao-existe')
    stubThrowingStorage()

    expect(safeStorage.get('chave-que-nao-existe')).toBe(ausente)
  })

  it('gravação e remoção devolvem false em vez de lançar', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    stubThrowingStorage()

    expect(() => safeStorage.set('k', 'v')).not.toThrow()
    expect(safeStorage.set('k', 'v')).toBe(false)
    expect(() => safeStorage.remove('k')).not.toThrow()
    expect(safeStorage.remove('k')).toBe(false)
  })

  it('registra aviso para não esconder navegador mal configurado de quem depura', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    stubThrowingStorage()

    safeStorage.get('k')

    expect(warn).toHaveBeenCalled()
  })

  it('funciona normalmente quando o armazenamento está disponível', () => {
    expect(safeStorage.set('mplacas-teste', 'valor')).toBe(true)
    expect(safeStorage.get('mplacas-teste')).toBe('valor')
    expect(safeStorage.remove('mplacas-teste')).toBe(true)
    expect(safeStorage.get('mplacas-teste')).toBeNull()
  })
})
