---
name: information-architecture
description: Use ao decidir a ordem/hierarquia de informação de uma tela do Mplacas — qual dado aparece primeiro, o que fica atrás de um clique, como agrupar cards relacionados. Aplica a lógica de três camadas já estabelecida (Executiva → Energética/Financeira → Técnica).
---

# Information Architecture — Mplacas

## Finalidade
Definir a ordem e o agrupamento de informação numa tela, de forma que responda primeiro à pergunta mais urgente do usuário.

## Quando usar
- Ao reorganizar a ordem de seções de uma página.
- Ao decidir se um dado fica visível por padrão ou atrás de "ver mais"/seção colapsável.

## As três camadas do dashboard (já estabelecidas, não redesenhar do zero)
1. **Executiva**: "Minha usina está bem?" — saúde, status, diagnóstico urgente.
2. **Energética e financeira**: "O que produzi, consumi e economizei?" — histórico, fluxo, custo, economia, ROI.
3. **Técnica**: "Por que o desempenho mudou?" — PR, yield, disponibilidade, degradação, perdas.

## Procedimento
1. Ao adicionar um dado novo à tela, primeiro classifique em qual das três camadas ele pertence — não misture dado técnico no topo executivo.
2. Dentro de uma camada, ordene por urgência: diagnóstico crítico > estado normal > detalhe.
3. Uma seção só fica colapsada por padrão se o conteúdo dela for genuinamente secundário para a decisão imediata — verifique a decisão do usuário registrada no momento (o padrão de "técnico colapsado" já mudou pelo menos uma vez neste projeto, então confira o estado atual antes de assumir).
4. Nunca esconda um diagnóstico crítico dentro de uma seção colapsada — isso é regra dura, não preferência.
5. Evite "parede de cards" do mesmo tamanho/peso — cards de dado mais importante devem ter mais destaque visual (tamanho, posição), não competir igualmente com um card secundário.

## Anti-patterns
- Colocar dado técnico denso antes do status executivo.
- Esconder alerta crítico atrás de um clique.
- Tratar todos os cards com o mesmo peso visual independente da importância.

## Checklist
- [ ] Dado classificado na camada correta
- [ ] Diagnóstico crítico nunca escondido
- [ ] Hierarquia visual reflete importância real
