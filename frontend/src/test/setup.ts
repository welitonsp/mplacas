import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// `test.globals: false` em vitest.config.ts desliga o registro automático de
// `afterEach` que @testing-library/react faz por padrão — sem isso, o DOM de um
// teste vaza para o próximo `render()` no mesmo arquivo (consultas `queryByText`
// que verificam ausência passam a encontrar elementos do teste anterior).
afterEach(cleanup)
