import { describe, expect, it } from 'vitest'
import { normalizeMeasurement, normalizeMoneyBrl } from './decimal'

describe('normalizeMoneyBrl (reais, pt-BR)', () => {
  it.each([
    ['15.000', '15000'],
    ['11.200', '11200'],
    ['1.500', '1500'],
    ['1.234', '1234'],
    ['1.500.000', '1500000'],
    ['11.200,00', '11200.00'],
    ['1.500,5', '1500.5'],
    ['1500,50', '1500.50'],
    ['1500', '1500'],
    ['0', '0'],
    ['1500.50', '1500.50'],
    ['12.5', '12.5'],
    ['0.500', '0.500'],
    ['R$ 2.300', '2300'],
    ['r$2.300,10', '2300.10'],
    [' 15 000 ', '15000'],
    ['', null],
    ['   ', null],
    ['R$', null],
    ['1.5,00', undefined],
    ['1.50.000', undefined],
    ['1,5,0', undefined],
    ['1500,', undefined],
    ['-15.000', undefined],
    ['abc', undefined],
    ['15.', undefined],
  ])('"%s" vira %j', (typed, expected) => {
    expect(normalizeMoneyBrl(typed)).toBe(expected)
  })
})

describe('normalizeMeasurement (kWp, graus, coordenadas)', () => {
  it.each([
    ['4,4', '4.4'],
    ['4.4', '4.4'],
    ['4.400', '4.400'],
    ['1.234,5', '1234.5'],
    ['-17,74', '-17.74'],
    ['-48.62', '-48.62'],
    ['15', '15'],
    ['', null],
    ['  ', null],
    ['abc', undefined],
    ['1,2,3', undefined],
  ])('"%s" vira %j', (typed, expected) => {
    expect(normalizeMeasurement(typed)).toBe(expected)
  })
})
