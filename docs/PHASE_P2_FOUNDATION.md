# Fase P2 — Fundação operacional

## Escopo concluído

- Event Bus interno assíncrono e tipado;
- motores determinísticos de qualidade e anomalias;
- pontuação de confiabilidade dos dados;
- detecção de produção negativa, data futura e rendimento implausível;
- detecção de perda de comunicação, produção zero e baixa geração específica;
- Índice de Saúde da Usina com pesos e penalidades auditáveis;
- testes unitários dos motores e do Event Bus;
- ADRs para arquitetura orientada a eventos e IA apenas explicativa.

## Critérios de aceite

- nenhum cálculo depende de IA;
- percentuais são limitados ao intervalo de 0 a 100;
- anomalias críticas reduzem o índice de saúde;
- produção negativa é rejeitada;
- regras possuem testes determinísticos;
- nenhuma credencial ou dado pessoal é incluído no repositório.

## Próxima etapa

A persistência de jobs, métricas, endpoints e integração completa com a coleta serão tratadas em PR próprio para manter revisão, rollback e rastreabilidade simples.
