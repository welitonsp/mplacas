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
      <h3 className="text-[15px] font-semibold text-[var(--color-text-primary)]">{title}</h3>
      <div className="mt-1 text-[14px] leading-6 text-[var(--color-text-secondary)]">{children}</div>
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
          Leitura diária do inversor, pelo portal do fabricante. Dia sem leitura não vira zero: ele é estimado pela
          irradiação solar do dia e aparece marcado como estimado.
        </Rule>
        <Rule title="Consumo, envio à rede, créditos e saldo">
          Da fatura da distribuidora que você confirmou: consumo da rede, leitura do medidor de geração, energia
          compensada, saldo de créditos, Fio B, bandeira e iluminação pública.
        </Rule>
        <Rule title="Tarifa cheia">
          Tarifa homologada pela ANEEL para a sua distribuidora e classe (TUSD + TE). Na Equatorial Goiás, isso vem
          das Resoluções Homologatórias REH 3.407/2024 e REH 3.544/2025. Quando o reajuste cai no meio do ciclo, a
          tarifa é dividida por dia, como a distribuidora faz.
        </Rule>
        <Rule title="Impostos">
          ICMS, PIS e COFINS vêm da própria fatura de cada mês. Nenhuma alíquota é presumida.
        </Rule>
      </Section>

      <Section id="placas-distribuidora" title="Placas × distribuidora">
        <Rule title="O que o medidor da distribuidora mede">
          O medidor fica no padrão de entrada e só registra o que sai da casa para a rede. A energia que a casa
          consome na hora em que as placas produzem nunca passa por ele, por isso a fatura mostra menos do que o
          inversor.
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
          prejuízo quando a fatura confirma que 100% da geração é da sua unidade (rateio).
        </Rule>
        <Rule title="Crédito vencido">
          Pela Lei 14.300/2022, o crédito vale 60 meses. Se a fatura anterior avisou um saldo a vencer e ele não foi
          usado no ciclo, ele aparece como vencido, não como prejuízo.
        </Rule>
        <Rule title="Envio impossível">
          O medidor não pode registrar mais envio à rede do que o inversor produziu. Acima de 5% de folga (precisão
          do inversor), um dos dois medidores está errado e vale pedir aferição.
        </Rule>
        <Rule title="Fora do padrão">
          Se a parte da produção que vai para a rede cair mais de 20 pontos em relação ao seu histórico, aparece uma
          suspeita. Pode ser o medidor ou mais consumo durante o dia.
        </Rule>
        <Rule title="Valor de 1 kWh de crédito">
          <Formula>valor = tarifa cheia com impostos + bandeira − Fio B</Formula>
          Um kWh compensado evita a tarifa cheia, mas ainda paga o Fio B. O valor em reais só aparece quando a
          fatura refeita com esses preços fecha com a fatura real.
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
          O Fio B (Lei 14.300/2022, Art. 27: parcela crescente de 15% em 2023 a 90% em 2028) e o custo de
          disponibilidade (REN 1.000/2021) entram como a distribuidora cobrou. O sistema não recalcula esses valores
          e não os inventa.
        </Rule>
        <Rule title="Conferência do modelo">
          Todo mês o sistema refaz a fatura com essas regras e compara com o valor cobrado. O que sobra aparece como
          diferença, por exemplo a parcela retroativa do Fio B, e nunca é escondido.
        </Rule>
      </Section>

      <Section id="limites" title="Limites">
        <Rule title="Estimado nunca aparece como medido">
          Valores que dependem de estimativa (casa, dias sem leitura, economia) aparecem marcados. Quando falta um
          dado, a tela diz o motivo e não mostra zero.
        </Rule>
        <Rule title="Não é parecer jurídico ou contábil">
          É uma conferência técnica com as regras públicas. Se encontrar divergência, procure a ouvidoria da
          distribuidora e, sem solução, a ANEEL (telefone 167).
        </Rule>
      </Section>
    </div>
  )
}
