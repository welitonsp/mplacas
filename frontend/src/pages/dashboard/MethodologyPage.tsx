import type { ReactNode } from 'react'
import { Card } from '../../components/Card'
import { PageHeader } from '../../components/PageHeader'
import { SectionTitle } from '../../components/SectionTitle'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { DASHBOARD_FINANCIAL_PATH } from '../../routes'

// "Como calculamos" (ADR-086): cada número que o MPlacas mostra, de onde vem e
// a regra (ou norma) por trás. Texto fixo, sem dado da usina — é a memória de
// cálculo que dá segurança a cliente e investidor. Precisa acompanhar o motor:
// mudou a fórmula (ADR-080/084/085), muda aqui.

function Rule({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-t border-[var(--color-border)] py-4 first:border-t-0 first:pt-0 last:pb-0">
      <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</h3>
      <div className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{children}</div>
    </div>
  )
}

function Formula({ children }: { children: ReactNode }) {
  return (
    <p className="my-2 rounded-lg bg-[var(--color-gray-50)] px-3 py-2 font-mono text-[13px] leading-6 text-[var(--color-text-primary)]">
      {children}
    </p>
  )
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="mb-6" aria-labelledby={id}>
      <SectionTitle as="h2" id={id}>
        {title}
      </SectionTitle>
      <Card className="sm:p-6">{children}</Card>
    </section>
  )
}

export function MethodologyPage() {
  const headingRef = useModuleTitle('Como calculamos')
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="Dinheiro"
        title="Como calculamos"
        description="De onde vem cada número e qual regra está por trás dele."
        headingRef={headingRef}
        backLink={{ to: DASHBOARD_FINANCIAL_PATH, label: 'Voltar para Dinheiro' }}
      />

      <Section id="fontes" title="De onde vem cada número">
        <Rule title="Produção das placas">
          Leitura diária do inversor, pelo portal do fabricante. Dia sem leitura é estimado pelo sol daquele dia
          (dado de clima modelado, não medido na usina) multiplicado pelo rendimento da própria usina nos dias com
          leitura, e aparece marcado como estimado. Se faltar histórico ou dado de clima, o dia não é estimado e o
          ciclo avisa quantos dias ficaram sem leitura. Num ciclo com dia sem leitura, a produção não fica abaixo do
          que o medidor da distribuidora registrou como enviado à rede. Num ciclo completo, se o medidor registrar
          mais de 5% acima do inversor, aparece como envio impossível.
        </Rule>
        <Rule title="Consumo, envio à rede, créditos e saldo">
          Da fatura da distribuidora que você confirmou: consumo da rede, leitura do medidor de geração, energia
          compensada, saldo de créditos, Fio B, bandeira e iluminação pública.
        </Rule>
        <Rule title="Tarifa cheia">
          Tarifa homologada pela ANEEL (TUSD + TE) para a classe tarifária lida da fatura (faturas importadas antes dessa leitura usam a classe presumida, e a tela avisa). As tarifas vêm toda semana da base aberta de tarifas da ANEEL, para todas as
          distribuidoras, nas classes B1 residencial, B2 rural e B3 (comercial, industrial e poder público). Na
          Equatorial Goiás, por exemplo, são as Resoluções Homologatórias REH 3.407/2024 e REH 3.544/2025. Tarifa
          branca, baixa renda e subclasses com desconto próprio ainda não são importadas. Quando o
          reajuste cai no meio do ciclo, a tarifa é dividida por dia, como a distribuidora faz. O sistema usa o
          preço da própria fatura, e avisa que a economia pode estar subestimada, quando algum dia do ciclo não tem
          tarifa cadastrada, quando a fatura não traz o preço sem impostos ou quando a tarifa cheia calculada fica
          abaixo do preço da fatura (sinal de cadastro ou classe errados).
        </Rule>
        <Rule title="Impostos">
          O fator de impostos (ICMS, PIS e COFINS) é tirado da própria fatura de cada mês: preço com impostos ÷
          preço sem impostos da linha de consumo. Nenhuma alíquota é presumida.
        </Rule>
      </Section>

      <Section id="placas-distribuidora" title="Placas × distribuidora">
        <Rule title="O que o medidor da distribuidora mede">
          O medidor fica no padrão de entrada e registra o que entra da rede e o que sai para ela. Da produção das
          placas, ele só vê a parte que sai para a rede: a energia que a casa consome na hora em que as placas
          produzem nunca passa por ele. Por isso a fatura mostra menos do que o inversor.
        </Rule>
        <Rule title="O que ficou na casa">
          <Formula>casa = produção do inversor − enviado à rede (medidor)</Formula>É uma estimativa: depende da
          precisão do inversor e dos dias estimados. Por isso aparece sempre marcada como estimada.
        </Rule>
      </Section>

      <Section id="conferencia" title="Conferência da distribuidora">
        <Rule title="Todo kWh registrado tem de virar crédito">
          <Formula>registrado pelo medidor + saldo anterior = créditos usados + saldo novo</Formula>
          Se sobrar crédito sem destino, o ciclo mostra créditos sem explicação. Só é tratado como forte indício de
          prejuízo quando a fatura confirma que 100% da geração é da sua unidade (rateio). Se foi usado mais
          crédito do que havia, a conta não fecha para nenhum lado e o ciclo fica sem conferência. Sem a leitura do
          medidor ou sem a fatura do mês anterior, também fica sem conferência — nunca "sem prejuízo" por
          omissão.
        </Rule>
        <Rule title="Crédito vencido">
          Pela Lei 14.300/2022, o crédito vale 60 meses. Se a fatura anterior avisou um saldo a vencer e ele não foi
          usado no ciclo, ele aparece como vencido, não como prejuízo.
        </Rule>
        <Rule title="Envio impossível">
          O medidor não pode registrar mais envio à rede do que o inversor produziu. Acima de 5% de folga (precisão
          do inversor), algo está errado — um dos medidores ou o recorte de datas. Confira primeiro se as datas do ciclo batem; se
          baterem, vale pedir aferição. Não roda
          em ciclo com dias de produção estimados.
        </Rule>
        <Rule title="Fora do padrão">
          Se a parte da produção que vai para a rede ficar mais de 20 pontos abaixo da mediana dos seus ciclos
          anteriores (pelo menos 3), aparece uma suspeita. Pode ser o medidor ou mais consumo durante o dia. Não
          roda em ciclo com dias de produção estimados.
        </Rule>
        <Rule title="Valor dos créditos faltando">
          <Formula>valor de 1 kWh = tarifa cheia com impostos + bandeira − Fio B</Formula>
          Um kWh compensado evita a tarifa cheia, mas ainda paga o Fio B. O valor em reais só aparece quando há
          tarifa cheia homologada e Fio B na fatura, e quando a fatura refeita com esses preços fica a até R$ 5 da
          fatura real. Fora disso, fica só em kWh.
        </Rule>
        <Rule title="Valor do saldo de créditos">
          O valor do saldo guardado, mostrado em Dinheiro, é uma referência mais simples: tarifa da conta “sem a
          usina” menos o Fio B do ciclo, sem somar a bandeira. Sem Fio B na fatura, usa a tarifa inteira.
        </Rule>
      </Section>

      <Section id="economia" title="Economia do ciclo">
        <Rule title="A conta sem a usina">
          <Formula>
            consumo total = comprado da rede + consumido direto das placas
            <br />
            sem a usina = consumo total × (tarifa cheia com impostos + bandeira) + iluminação pública − créditos
            externos
          </Formula>
          A bandeira entra quando aparece na fatura: sem as placas, todo o consumo pagaria a bandeira.
        </Rule>
        <Rule title="A economia">
          <Formula>economia = conta sem a usina − valor pago na fatura</Formula>
          Créditos que não vêm das placas (compensação por falta de luz e Bônus de Itaipu) ficam fora da economia.
        </Rule>
        <Rule title="O que já vem cobrado na fatura">
          O Fio B (Lei 14.300/2022, Art. 27: para quem pediu a conexão a partir de 2023, parcela crescente de 15% em
          2023 a 90% em 2028) e o custo de disponibilidade (REN 1.000/2021) entram na economia como a distribuidora cobrou:
          o sistema não recalcula esses valores nem os inventa. Na conferência do modelo, o Fio B é refeito com a
          tarifa de Fio B impressa na própria fatura.
        </Rule>
        <Rule title="Conferência do modelo">
          Quando a fatura traz o Fio B e houve consumo da rede, o sistema refaz a fatura com essas regras e compara
          com o valor cobrado. O que sobra aparece como diferença — por exemplo a parcela retroativa do Fio B ou o
          custo de disponibilidade, que o modelo não refaz — e nunca é escondido. Sem esses dados, a conferência do
          modelo aparece como indisponível.
        </Rule>
      </Section>

      <Section id="ampliacao" title="Vale a pena ampliar a usina?">
        <Rule title="A falta no ano">
          <Formula>falta = Σ consumo da rede − Σ envio registrado pelo medidor (12 ciclos seguidos)</Formula>
          O crédito vale 60 meses, por isso a conta é do ano inteiro. Não usamos os créditos usados: quando o saldo
          guardado está acabando, eles escondem a falta que vai continuar. O mínimo faturável da ligação (30, 50 ou 100
          kWh) não é descontado: pela Lei 14.300 (art. 16, §1º) ele só pesa quando o consumo da rede fica abaixo dele.
          Diferença de até 5% do consumo da rede no ano conta como equilíbrio. Exige rateio de 100% da geração na
          própria unidade.
        </Rule>
        <Rule title="Quando não recomendamos">
          Faltando fatura, leitura do medidor ou rateio de 100%, a análise fica indisponível. Com os dados completos:
          ciclo com créditos faltando ou envio à rede impossível nos 12 meses, ou produção muito abaixo do esperado nos
          últimos 3: primeiro resolva a usina. Sobra no ano: ampliar só aumentaria a sobra.
        </Rule>
        <Rule title="Tamanho e inversor">
          <Formula>ampliação (kWp) = falta no ano ÷ rendimento anual medido da usina (kWh por kWp)</Formula>
          Arredondada para cima em 0,1 kWp. Rendimento só de meses sem dia estimado ou provisório (pelo menos 10),
          contando os dias do ciclo como a fatura (do primeiro ao último, inclusive). Vale para placas na mesma direção e inclinação das
          atuais. No inversor, placas ÷ potência do inversor até 1,30 cabe; até 1,50 depende do manual; acima disso,
          outro inversor. Com microinversores, a ampliação soma microinversores.
        </Rule>
        <Rule title="Valor da energia nova">
          <Formula>valor de 1 kWh no ano = tarifa cheia com impostos − Fio B pleno × parcela do ano</Formula>A parte
          ampliada pedida agora segue a regra nova da Lei 14.300 (art. 26, §2º, III): paga 60% do Fio B em 2026, 75%
          em 2027 e 90% em 2028 (art. 27). De 2029 em diante vale o art. 17, ainda sem regra da ANEEL: usamos Fio B
          integral como cenário. O Fio B pleno sai da fatura (Fio B do ciclo ÷ parcela do ano), por isso o valor em
          reais só aparece para usinas ligadas a partir de 2024 com Fio B na fatura e quando a fatura refeita fecha
          com a real. Bandeira fica de fora; sem reajuste de tarifa.
          <Formula>economia por mês = falta no ano ÷ 12 × valor de 1 kWh no ano</Formula>
        </Rule>
        <Rule title="Em quanto tempo a ampliação se paga">
          Com o valor total da proposta que você informar (placas, inversor, instalação e homologação), o retorno segue
          o mesmo fluxo mensal do painel do investidor: a tarifa reajustada pelo IPCA dos últimos 12 meses, perda de
          0,5% ao ano das placas, manutenção de 0,5% da proposta ao ano, troca do inversor no ano 12 (15% da proposta,
          só quando ela inclui inversor novo) e o Fio B da parte nova subindo ano a ano, a partir da parcela do ano
          corrente. Sem bandeira tarifária e contando a partir de hoje, sem o tempo de instalação e homologação — por
          isso o prazo real tende a ser um pouco maior. Mostramos também o prazo sem nenhum reajuste da tarifa e o prazo
          contando o que o mesmo dinheiro renderia no CDI, líquido de IR. Se a ampliação precisar de inversor novo e a
          proposta não incluir, o retorno não é calculado.
        </Rule>
      </Section>

      <Section id="limites" title="Limites">
        <Rule title="Estimado nunca aparece como medido">
          Valores que dependem de estimativa (casa, dias sem leitura, economia) aparecem marcados. Quando falta um
          dado, a tela diz o motivo e não mostra zero. Limitação conhecida: um dia em que só parte dos inversores
          reportou entra como lido e pode ficar abaixo do real.
        </Rule>
        <Rule title="Não é parecer jurídico ou contábil">
          É uma conferência técnica com as regras públicas. Se encontrar divergência, procure a ouvidoria da
          distribuidora e, sem solução, a ANEEL (telefone 167).
        </Rule>
      </Section>
    </div>
  )
}
