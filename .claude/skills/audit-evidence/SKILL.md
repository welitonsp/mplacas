---
name: audit-evidence
description: Use ao produzir qualquer relatório de auditoria (UI/UX, segurança, qualidade) do Mplacas — define o formato de evidência exigido (arquivo:linha, comando executado, output real) para toda afirmação, e a escala de severidade P0-P4 usada no projeto.
---

# Audit Evidence

## Finalidade
Padronizar como uma afirmação de auditoria vira evidência verificável, e como severidade é classificada — para relatórios comparáveis entre auditorias diferentes ao longo do tempo.

## Quando usar
- Ao escrever qualquer achado num relatório de auditoria (`docs/UI_UX_AUDIT_*.md`, `docs/CHECKLIST_REMEDIACAO_AUDITORIA.md` e equivalentes).
- Ao avaliar um achado de auditoria externa antes de agir sobre ele.

## Quando não usar
- Para o relatório de progresso de uma tarefa de implementação (isso é `definition-of-done`).

## Entradas necessárias
- Acesso de leitura ao código e, quando aplicável, a comandos executáveis (build, teste) para gerar evidência de execução real.

## Procedimento
1. Cada achado segue o formato: **Afirmação → Evidência → Impacto → Severidade → Solução proposta → Risco da correção**.
2. Evidência é sempre um de: `arquivo:linha` citado literalmente, output de comando rodado nesta sessão (nunca lembrado de sessão anterior sem reconfirmar), ou captura de tela quando for questão puramente visual (declare a limitação se não houver navegador disponível).
3. Severidade segue a escala já usada no projeto:
   - **P0**: bloqueia produção / risco de segurança ou vazamento de dado entre tenants.
   - **P1**: quebra funcional visível ou dado incorreto exibido ao usuário.
   - **P2**: problema real mas com contorno, ou que afeta poucos usuários/cenários.
   - **P3**: melhoria de qualidade sem quebra funcional.
   - **P4**: nice-to-have, cosmético.
4. Nunca misture "acho que" com achado confirmado — se não deu para confirmar, declare como hipótese, não afirmação.

## Critérios de saída
- Todo achado do relatório é rastreável até uma evidência concreta.
- Severidade justificada, não arbitrária.
- Zero achados fantasma (baseados só em relatório externo não reverificado — ver `repository-ground-truth`).

## Anti-patterns
- Atribuir P0 para problema cosmético para "chamar atenção".
- Citar número de linha de memória sem reconfirmar (arquivos mudam entre sessões).

## Checklist
- [ ] Toda afirmação tem evidência concreta
- [ ] Severidade segue a escala P0-P4 do projeto
- [ ] Hipóteses não confirmadas estão marcadas como tal
