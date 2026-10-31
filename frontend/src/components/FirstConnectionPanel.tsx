import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { CheckCircle2, CircleAlert } from 'lucide-react'
import { connectFirstPlant } from '../lib/api'
import {
  AUTO_FILL_LABELS,
  parseFirstConnection,
  type FirstConnection,
} from '../lib/dashboard/onboarding-contracts'
import { brandLabel, providerAccountErrorMessage } from '../lib/dashboard/provider-account-contracts'
import { usePlant } from '../contexts/PlantContext'
import { useModuleTitle } from '../hooks/useModuleTitle'
import { DASHBOARD_SETUP_PATH } from '../routes'
import { BrandLoginForm, PRIMARY_BUTTON, type BrandLogin } from './BrandLoginForm'
import { Card } from './Card'

// Primeira conexão do cliente (ADR-093 § 7). A conta ainda não tem usina: o
// cliente escolhe a marca e digita o usuário e a senha do app do celular; o
// servidor confere, cria a usina e a preenche com o que a marca informa.
// Nenhum dado técnico é pedido aqui — o que for estimado aparece depois em
// "Minha usina" para conferir.

function FilledSummary({ result }: { result: FirstConnection }) {
  const entries = Object.entries(result.autoFilled).filter(([field]) => field in AUTO_FILL_LABELS)
  const fromBrand = entries.filter(([, origin]) => origin === 'BRAND')
  const estimated = entries.filter(([, origin]) => origin === 'ESTIMATE')
  return (
    <div className="space-y-3 text-sm text-[var(--color-text-primary)]">
      {fromBrand.length > 0 && (
        <div>
          <p className="font-semibold">Veio do aplicativo da marca</p>
          <ul className="mt-1 list-disc pl-5 text-[var(--color-text-secondary)]">
            {fromBrand.map(([field]) => (
              <li key={field}>{AUTO_FILL_LABELS[field]}</li>
            ))}
          </ul>
        </div>
      )}
      {estimated.length > 0 && (
        <div>
          <p className="font-semibold">Estimado pelo sistema — confira em Minha usina</p>
          <ul className="mt-1 list-disc pl-5 text-[var(--color-text-secondary)]">
            {estimated.map(([field]) => (
              <li key={field}>{AUTO_FILL_LABELS[field]}</li>
            ))}
          </ul>
        </div>
      )}
      {entries.length === 0 && (
        <p className="text-[var(--color-text-secondary)]">
          A marca não informou os dados técnicos da usina. Complete em Minha usina para o sistema calcular a
          produção esperada.
        </p>
      )}
    </div>
  )
}

export function FirstConnectionPanel() {
  const navigate = useNavigate()
  const { reload } = usePlant()
  const [result, setResult] = useState<FirstConnection | null>(null)
  const doneRef = useRef<HTMLHeadingElement>(null)
  const titleRef = useModuleTitle('Conecte sua usina')

  // Ao concluir, o formulário some: o foco vai para o título do resultado.
  useEffect(() => {
    if (result) doneRef.current?.focus()
  }, [result])

  async function submit(credentials: BrandLogin): Promise<string | null> {
    const response = await connectFirstPlant(credentials)
    if (!response.ok) {
      if (response.status === 409) {
        const detail = await response
          .clone()
          .json()
          .then((body: { detail?: unknown }) => body?.detail)
          .catch(() => undefined)
        // A usina já existe (outra aba, clique duplo): recarrega a lista e o
        // painel aparece — atualizar a página deslogaria (sessão só em memória).
        if (detail === 'plant_already_exists') reload()
      }
      return providerAccountErrorMessage(response, credentials.provider)
    }
    setResult(parseFirstConnection(await response.json()))
    return null
  }

  function goToPlant() {
    reload()
    navigate(DASHBOARD_SETUP_PATH)
  }

  return (
    <section aria-labelledby="first-connection-heading" className="mx-auto max-w-2xl space-y-5">
      {!result ? (
        <>
          <div>
            <h1
              id="first-connection-heading"
              ref={titleRef}
              tabIndex={-1}
              className="font-display text-2xl font-semibold text-[var(--color-text-primary)] focus:outline-none"
            >
              Conecte sua usina
            </h1>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
              Escolha a marca do inversor e use o mesmo usuário e senha do aplicativo do celular. O sistema
              confere a conta, cria a sua usina e preenche os dados que a marca informa.
            </p>
          </div>
          <Card className="sm:p-6">
            <BrandLoginForm
              ariaLabel="Conectar a usina"
              submitLabel="Conferir e criar minha usina"
              onSubmit={submit}
            />
          </Card>
        </>
      ) : (
        <Card className="sm:p-6">
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              {result.devicesFound === 0 ? (
                <CircleAlert aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-[var(--color-warning)]" />
              ) : (
                <CheckCircle2 aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-[var(--color-success)]" />
              )}
              <div>
                <h1
                  id="first-connection-heading"
                  ref={doneRef}
                  tabIndex={-1}
                  className="font-display text-xl font-semibold text-[var(--color-text-primary)] focus:outline-none"
                >
                  {result.devicesFound === 0
                    ? `A usina “${result.plantName}” foi criada, mas confira a conta`
                    : `Pronto! A usina “${result.plantName}” foi criada.`}
                </h1>
                <p className="mt-1 text-sm text-[var(--color-text-secondary)]" role="status">
                  {result.devicesFound === 0
                    ? `A conta foi conectada, mas não mostra nenhuma usina ou inversor. Confira se é a conta certa.`
                    : 'A primeira leitura da produção acontece na próxima coleta, de madrugada.'}
                </p>
              </div>
            </div>
            <FilledSummary result={result} />
            <button type="button" className={PRIMARY_BUTTON} onClick={goToPlant}>
              Ver minha usina
            </button>
          </div>
        </Card>
      )}
      <p className="text-xs leading-5 text-[var(--color-text-secondary)]">
        Marcas aceitas: {brandLabel('NEPVIEWER')} e {brandLabel('GROWATT')}.
      </p>
    </section>
  )
}

export function NoPlantReadOnly() {
  return (
    <section className="mx-auto max-w-2xl">
      <Card className="sm:p-6">
        <h1 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
          Nenhuma usina conectada ainda
        </h1>
        <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
          O administrador da conta precisa conectar a usina. Assim que isso acontecer, os dados aparecem aqui.
        </p>
      </Card>
    </section>
  )
}
