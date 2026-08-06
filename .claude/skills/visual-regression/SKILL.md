---
name: visual-regression
description: Use ao avaliar necessidade de captura visual/screenshot do Mplacas para validar uma mudança de UI — o projeto não tem ferramenta de regressão visual automatizada hoje; declare a limitação em vez de afirmar validação visual que não ocorreu.
---

# Visual Regression — Mplacas

## Finalidade
Ser honesto sobre a ausência de ferramenta de regressão visual automatizada no projeto, e definir o que fazer sem ela.

## Estado real
- Não há Percy/Chromatic/Playwright de captura visual configurado no projeto até o momento em que esta skill foi escrita — confirme se isso mudou antes de assumir.
- Validação visual, quando necessária, depende de ferramenta de navegador disponível na sessão (ex: screenshot manual) ou é declarada como não verificada.

## Procedimento
1. Antes de afirmar "validei visualmente", confirme que realmente há uma ferramenta de captura disponível nesta sessão.
2. Se não houver, entregue uma checklist manual precisa (viewports a checar: 360/768/1024/1440/1920px) em vez de fingir que a validação ocorreu.
3. Para mudança de layout grande, prefira dividir em etapas pequenas revisáveis via diff de código (mais confiável que "parece certo" sem ferramenta visual).

## Anti-patterns
- Afirmar "testei visualmente em todos os breakpoints" sem ter rodado nada.
- Pedir para o usuário confiar cegamente numa mudança de CSS grande sem checklist de verificação.

## Checklist
- [ ] Ferramenta de captura confirmada disponível, ou limitação declarada
- [ ] Checklist manual de viewports entregue quando não há ferramenta
