# ADR-037 - Acesso operacional de leitura escopado por usina

## Status

Aceito.

## Contexto

O ADR-031 separou as credenciais administrativas e de leitura, mas ambas continuaram com acesso a
todas as usinas. Esse modelo permite reduzir privilégios de escrita, porém não isola dados entre
operadores, clientes ou dashboards. O `plant_id` já delimita os dados nos contratos HTTP e a
fronteira de faturas confirmadas do ADR-036 oferece um ponto adicional para aplicar autorização.

Introduzir usuários, tenants, OIDC e concessões persistidas agora ampliaria excessivamente o escopo.
O passo intermediário precisa preservar as implantações atuais, falhar fechado quando configurado e
não revelar a existência de usinas fora do escopo.

## Decisão

1. Modelar `PlantScope` como valor imutável contendo um conjunto de UUIDs ou acesso irrestrito.
2. Fazer `OperationsPrincipal` carregar o escopo da credencial autenticada.
3. Configurar o escopo opcional da chave `READ` por
   `MPLACAS_OPERATIONS_READ_PLANT_IDS`, com UUIDs separados por vírgula.
4. Tratar a ausência da configuração como acesso irrestrito para preservar compatibilidade.
5. Rejeitar configuração vazia, UUID inválido ou escopo sem chave de leitura.
6. Verificar o `plant_id` antes de executar serviços nos endpoints de energia, explicações e
   relatórios. Acesso fora do escopo retorna `404` para não confirmar a existência da usina.
7. Propagar o escopo pela camada de inteligência e aplicá-lo novamente em
   `ConfirmedBillReadRepository`, estabelecendo defesa em profundidade na fronteira de dados.
8. Negar com `403` os endpoints globais `/operations/jobs` e `/operations/status` quando a
   credencial estiver restrita, pois seus registros ainda não possuem filtro seguro por usina.
9. Registrar somente o tipo e a quantidade do escopo nos logs, nunca os UUIDs autorizados nem a
   credencial.
10. Manter a chave administrativa irrestrita nesta fase. Escopos administrativos e múltiplas
    credenciais exigirão concessões persistidas ou identidade gerenciada.

## Consequências

### Positivas

- Uma chave de dashboard pode consultar somente as usinas explicitamente concedidas.
- Endpoints novos podem reutilizar `OperationsPrincipal.require_plant_access` e `PlantScope`.
- A fronteira de leitura de billing falha fechada mesmo se um chamador esquecer a verificação HTTP.
- Implantações sem a nova variável mantêm o contrato existente.
- Logs permitem auditar se a chamada usou escopo restrito sem divulgar a lista de usinas.

### Negativas

- Há somente uma chave `READ` configurável; escopos diferentes por usuário ainda não são possíveis.
- Status e histórico operacional globais ficam indisponíveis para uma chave restrita até que os
  registros tenham escopo por usina.
- Repositórios de outros domínios ainda dependem da verificação na fronteira HTTP; a defesa adicional
  desta fase cobre a leitura central de faturas confirmadas.
- A chave administrativa continua global e deve permanecer reservada a operadores confiáveis.

## Validação

A entrega deve permanecer coberta por:

- autenticação com escopo restrito e compatibilidade do administrador irrestrito;
- validação e resumo seguro da configuração;
- `404` para recursos de usina fora do escopo em todos os routers de leitura;
- `403` para status operacional global com credencial restrita;
- bloqueio adicional no repositório de faturas confirmadas;
- propagação do escopo até relatórios e inteligência;
- Ruff, Mypy e Pytest.
