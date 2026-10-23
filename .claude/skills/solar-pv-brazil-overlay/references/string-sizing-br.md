# Dimensionamento de String — NBR 16690

## Fórmula

V_string,max = N_mod × Voc,STC × [1 + (βVoc / 100) × (T_min − 25)]

- **N_mod** = número de módulos em série
- **Voc,STC** = tensão de circuito aberto na STC (25 °C, 1000 W/m²)
- **βVoc** = coeficiente de temperatura de Voc (%/°C), valor do fabricante (negativo)
- **T_min** = temperatura mínima do local (INMET, por município), em °C

## Critério de aceitação

V_string,max ≤ V_inv,max (tensão máxima de entrada CC do inversor ou microinversor)

## Exemplo numérico (ilustrativo — use os dados reais do projeto)

- 10 módulos, Voc,STC = 41,2 V, βVoc = −0,29 %/°C, T_min = 5 °C (INMET)
- Fator = 1 + (−0,0029 × (5 − 25)) = 1 + 0,058 = 1,058
- Voc a frio = 41,2 × 1,058 = 43,59 V por módulo
- String = 10 × 43,59 = 435,9 V → verificar contra a tensão máxima do inversor

> Com microinversores (1 a 4 módulos por entrada), a string é curta e a tensão a frio quase
> nunca é o limite; o que costuma limitar é a corrente e a potência CA (clipping).
