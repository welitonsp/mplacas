import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { stubMatchMediaMatches } from '../../test/matchMedia'
import { useChartEntrance } from './useChartEntrance'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useChartEntrance', () => {
  it('começa em false na montagem e vira true pouco depois (animação de entrada)', async () => {
    const { result } = renderHook(() => useChartEntrance())

    expect(result.current).toBe(false)

    await waitFor(() => {
      expect(result.current).toBe(true)
    })
  })

  it('prefers-reduced-motion: reduce começa já em true — sem estado "vazio" nem transição', () => {
    stubMatchMediaMatches(true)

    const { result } = renderHook(() => useChartEntrance())

    expect(result.current).toBe(true)
  })

  it('depois de "entered" virar true, uma re-renderização (equivalente a um refetch) nunca volta a false', async () => {
    const { result, rerender } = renderHook(() => useChartEntrance())

    await waitFor(() => {
      expect(result.current).toBe(true)
    })

    rerender()
    rerender()

    expect(result.current).toBe(true)
  })
})
