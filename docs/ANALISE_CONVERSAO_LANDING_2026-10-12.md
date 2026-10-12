# Análise e evolução da landing MPlacas

**Data:** 12 de outubro de 2026

**Escopo:** landing pública (`/`), comunicação comercial, contato, metadados, compatibilidade com CSP e responsividade. A área autenticada e as regras de cálculo energético ficaram fora do escopo.

## Leitura executiva

O site já tinha uma identidade visual consistente, fotografias auto-hospedadas, demonstração do painel e diferenciais técnicos incomuns: rastreabilidade por métrica, diagnósticos determinísticos e tratamento explícito de dados incompletos. A oportunidade principal não era trocar o visual, mas traduzir esses atributos em valor reconhecível para o visitante e aproximá-lo do contato.

A página publicada respondeu HTTP 200 e informou uma CSP com `style-src 'self'` e `img-src 'self' data:`. No código versionado, os três fundos fotográficos eram aplicados por `style={{ backgroundImage: ... }}`. A implementação foi alinhada à CSP ao transferir as referências para o stylesheet local, sem ampliar permissões nem buscar imagens externas.

## O que dificultava a conversão

1. **A primeira mensagem era de marca, não uma dor do cliente.** “Energia medida. Decisão explicada.” é memorável, mas não deixa claro de imediato a pergunta que a plataforma ajuda a investigar.
2. **A proposta exigia familiaridade técnica.** Termos como telemetria, ciclo, snapshots e rastreabilidade apareciam antes de uma explicação direta do benefício.
3. **A ação de contato era genérica.** “Conhecer a plataforma” abria apenas um e-mail sem contexto que ajudasse a pessoa a iniciar a conversa.
4. **Havia alegações quantitativas fortes.** “100%” de rastreabilidade era mais amplo do que a evidência explicitada na página permitia assegurar.
5. **Objeções importantes ficavam sem resposta.** A landing não explicava o papel da IA nem como tratava lacunas ou a disponibilidade dos dados.
6. **O mockup sinalizava atualização real.** “Dados atualizados” podia sugerir uma conexão ao vivo apesar de os números serem ilustrativos.
7. **Metadados falavam em termos institucionais.** Título e descrição tinham espaço para comunicar melhor o uso principal também em prévias de compartilhamento.

## Evolução implementada

- Reescrita do hero em torno da relação entre produção solar e fatura: **“O que sua usina gera aparece na conta?”**
- Texto principal agora descreve, em linguagem direta, o cruzamento de dados do NEPViewer, clima e fatura Equatorial — sem prometer resultado ou causa além do que os dados permitem.
- CTAs coerentes (“Avaliar minha usina”) abrem um e-mail com assunto e campos opcionais para portal/inversor, cidade/UF e dúvida principal. A ação continua transparente: depende do aplicativo de e-mail do visitante; nenhum formulário ou envio automático foi simulado.
- Inclusão de FAQ nativo por `<details>`/`<summary>` sobre fontes de dados, cálculos e ausência de dados, antes da chamada final.
- Substituição da alegação “100%” por atributos observáveis: origem, unidade e período por métrica.
- Marcação mais evidente do painel como demonstração, com valores ilustrativos e sem indicação de atualização em tempo real.
- Fundos fotográficos movidos de atributos inline para CSS da própria origem, com teste de regressão em linha com a CSP publicada.
- Mais foco visível, relação explícita do botão de menu com a navegação e CTA do menu móvel alinhado ao objetivo.
- Atualização de `<title>`, descrição e metadados Open Graph para prévias compartilhadas.
- Novos testes de regressão para mensagem, canal de contato, FAQ, menu e imagens sob CSP.

## Limites e próximos passos recomendados

“10/10” não pode ser comprovado somente por uma alteração de código. Ainda faltam dados de conversão, fonte de tráfego, perfil prioritário do comprador e validação com visitantes reais. Para medir resultado após publicação, acompanhar pelo menos abertura do CTA, clique de contato e conversa iniciada; comparar a nova pergunta de entrada com a versão anterior. Se houver um canal preferido (WhatsApp, agenda ou CRM), integrar esse fluxo somente após confirmar os dados de contato e a ferramenta que a equipe de fato usa.

**Estado desta entrega:** alterações aplicadas apenas à cópia de trabalho deste sandbox. Nenhuma escrita, commit, deploy ou publicação foi feita no GitHub/Cloudflare.
