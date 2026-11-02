import { FormEvent, useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Check, CheckCircle2, CircleAlert, Loader2 } from 'lucide-react'
import { confirmFirstPlant, previewFirstPlant } from '../lib/api'
import { parseConnectPreview, parseFirstConnection, type ConnectPreview } from '../lib/dashboard/onboarding-contracts'
import { brandLabel, providerAccountErrorMessage } from '../lib/dashboard/provider-account-contracts'
import { usePlant } from '../contexts/PlantContext'
import { useModuleTitle } from '../hooks/useModuleTitle'
import { DASHBOARD_OVERVIEW_PATH } from '../routes'
import { BrandLoginForm, INPUT_CLASS, PRIMARY_BUTTON, SECONDARY_BUTTON, type BrandLogin } from './BrandLoginForm'
import { Card } from './Card'

// Assistente de primeiro acesso (ADR-096). Três passos:
// 1. Conectar — marca + usuário/senha ou token do app;
// 2. Lendo sua usina — o servidor confere a conta e lê a usina na marca, sem
//    salvar nada (a tela mostra cada etapa);
// 3. Revisar e salvar — a usina já montada, cada campo com a origem ("Veio da
//    marca"/"Estimado"), tudo editável, e um único "Salvar usina".
// Entre o passo 1 e o 3 a senha não fica no navegador: o servidor devolve um
// bilhete cifrado que só ele abre (vale 15 min).

type Step = 'connect' | 'reading' | 'review' | 'done'

const STEP_LABELS: Array<{ key: Exclude<Step, 'done'>; label: string }> = [
  { key: 'connect', label: 'Conectar' },
  { key: 'reading', label: 'Ler a usina' },
  { key: 'review', label: 'Revisar e salvar' },
]

const DIRECTIONS = [
  { degrees: '0', label: 'Norte' },
  { degrees: '45', label: 'Nordeste' },
  { degrees: '90', label: 'Leste' },
  { degrees: '135', label: 'Sudeste' },
  { degrees: '180', label: 'Sul' },
  { degrees: '225', label: 'Sudoeste' },
  { degrees: '270', label: 'Oeste' },
  { degrees: '315', label: 'Noroeste' },
]

const TECHNOLOGIES = [
  { value: 'MONOCRYSTALLINE_SILICON', label: 'Monocristalino' },
  { value: 'POLYCRYSTALLINE_SILICON', label: 'Policristalino' },
  { value: 'THIN_FILM', label: 'Filme fino' },
  { value: 'OTHER', label: 'Outro' },
]

const READING_STEP_MS = 1100

function readingSteps(brand: string): string[] {
  return [
    `Conectando à ${brand}`,
    'Encontrando sua usina',
    'Lendo potência e localização',
    'Calculando a posição dos painéis',
  ]
}

function trimNumber(value: string | null): string {
  if (value == null) return ''
  const number = Number(value)
  return Number.isFinite(number) ? String(number) : value
}

function StepIndicator({ step }: { step: Step }) {
  const activeIndex = step === 'done' ? STEP_LABELS.length : STEP_LABELS.findIndex((item) => item.key === step)
  return (
    <ol
      className="flex flex-wrap items-center gap-2 text-xs font-semibold sm:gap-3"
      aria-label={`Etapas do cadastro: passo ${Math.min(activeIndex + 1, STEP_LABELS.length)} de ${STEP_LABELS.length}`}
    >
      {STEP_LABELS.map((item, index) => {
        const done = index < activeIndex
        const current = index === activeIndex
        return (
          <li key={item.key} className="flex items-center gap-2" aria-current={current ? 'step' : undefined}>
            <span
              aria-hidden="true"
              className={`flex h-6 w-6 items-center justify-center rounded-full ${
                done
                  ? 'bg-[var(--color-success)] text-[var(--color-on-brand)]'
                  : current
                    ? 'bg-[var(--color-brand-primary)] text-[var(--color-on-brand)]'
                    : 'bg-[var(--color-gray-100)] text-[var(--color-text-secondary)]'
              }`}
            >
              {done ? <Check className="h-3.5 w-3.5" /> : index + 1}
            </span>
            <span className={current ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'}>
              {item.label}
              {done && <span className="sr-only"> (feito)</span>}
            </span>
            {index < STEP_LABELS.length - 1 && (
              <span aria-hidden="true" className="hidden h-px w-6 bg-[var(--color-border)] sm:block" />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function ReadingView({ brand, finished }: { brand: string; finished: boolean }) {
  const steps = readingSteps(brand)
  const [index, setIndex] = useState(0)
  const headingRef = useRef<HTMLHeadingElement>(null)

  // O botão que iniciou a leitura some: o foco vai para o título deste passo.
  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  useEffect(() => {
    if (finished) {
      setIndex(steps.length)
      return
    }
    if (index >= steps.length - 1) return
    const timer = setTimeout(() => setIndex((value) => value + 1), READING_STEP_MS)
    return () => clearTimeout(timer)
  }, [index, finished, steps.length])

  return (
    <Card className="sm:p-6">
      <h2 ref={headingRef} tabIndex={-1} className="font-display text-xl font-semibold text-[var(--color-text-primary)] focus:outline-none">
        Lendo sua usina
      </h2>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
        O sistema está acessando a {brand} com a sua conta. Nada é salvo antes da sua revisão.
      </p>
      <ul className="mt-5 space-y-3">
        {steps.map((label, position) => {
          const done = position < index
          const current = position === index
          return (
            <li key={label} className="flex items-center gap-3 text-sm">
              <span aria-hidden="true" className="flex h-6 w-6 items-center justify-center">
                {done ? (
                  <CheckCircle2 className="h-5 w-5 text-[var(--color-success)]" />
                ) : current ? (
                  <Loader2 className="h-5 w-5 animate-spin text-[var(--color-brand-primary)] motion-reduce:animate-none" />
                ) : (
                  <span className="h-2 w-2 rounded-full bg-[var(--color-gray-300)]" />
                )}
              </span>
              <span className={done || current ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'}>
                {label}
                {done ? <span className="sr-only"> (feito)</span> : current ? '…' : ''}
              </span>
            </li>
          )
        })}
      </ul>
      <p role="status" aria-live="polite" className="sr-only">
        {index < steps.length ? `${steps[index]}…` : 'Leitura concluída.'}
      </p>
    </Card>
  )
}

function OriginBadge({ origin, brand, edited }: { origin: string | undefined; brand: string; edited?: boolean }) {
  if (edited) {
    return (
      <span className="ml-2 rounded-full bg-[var(--color-gray-100)] px-2 py-0.5 text-xs font-semibold text-[var(--color-text-secondary)]">
        Informado por você
      </span>
    )
  }
  if (origin === 'BRAND') {
    return (
      <span className="ml-2 rounded-full bg-[var(--color-success-light)] px-2 py-0.5 text-xs font-semibold text-[var(--color-success-text)]">
        Veio da {brand}
      </span>
    )
  }
  if (origin === 'ESTIMATE') {
    return (
      <span className="ml-2 rounded-full bg-[var(--color-warning-light)] px-2 py-0.5 text-xs font-semibold text-[var(--color-warning-text)]">
        Estimado — confira
      </span>
    )
  }
  return null
}

interface ReviewValues {
  name: string
  installedPowerKwp: string
  latitude: string
  longitude: string
  arrayTiltDegrees: string
  arrayAzimuthDegrees: string
  moduleTechnology: string
}

function ReviewForm({
  preview,
  onBack,
  onSaved,
}: {
  preview: ConnectPreview
  onBack: (message?: string) => void
  onSaved: (result: { plantName: string; devicesFound: number | null; estimated: boolean }) => void
}) {
  const ids = useId()
  const { reload: reloadPlants } = usePlant()
  const brand = brandLabel(preview.provider)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [values, setValues] = useState<ReviewValues>({
    name: preview.plant.name,
    installedPowerKwp: trimNumber(preview.plant.installedPowerKwp),
    latitude: trimNumber(preview.plant.latitude),
    longitude: trimNumber(preview.plant.longitude),
    arrayTiltDegrees: trimNumber(preview.plant.arrayTiltDegrees),
    arrayAzimuthDegrees: trimNumber(preview.plant.arrayAzimuthDegrees),
    moduleTechnology: preview.plant.moduleTechnology ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  const set = (key: keyof ReviewValues) => (event: { target: { value: string } }) =>
    setValues((current) => ({ ...current, [key]: event.target.value }))

  const origin = (key: string) => preview.origins[key]
  const initial = useRef(values).current
  // Campo que o cliente mudou deixa de ser "da marca"/"estimado": é dele.
  const edited = (...keys: Array<keyof ReviewValues>) =>
    keys.some((key) => values[key].trim() !== initial[key].trim())
  // O que a MARCA não informou (pelo rascunho, não pelo que o cliente apagou).
  const missing = [
    !preview.plant.installedPowerKwp && 'a potência dos painéis',
    (!preview.plant.latitude || !preview.plant.longitude) && 'a localização',
  ].filter(Boolean)
  const expiresAt = new Date(preview.expiresAt)
  const expiresLabel = Number.isNaN(expiresAt.getTime())
    ? null
    : expiresAt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  const knownDirection = DIRECTIONS.some((item) => item.degrees === values.arrayAzimuthDegrees)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!values.name.trim()) {
      setError('Dê um nome para a usina.')
      return
    }
    if (Boolean(values.latitude.trim()) !== Boolean(values.longitude.trim())) {
      setError('Informe latitude e longitude juntas, ou deixe as duas em branco.')
      return
    }
    const tilt = Number(values.arrayTiltDegrees.replace(',', '.'))
    if (values.arrayTiltDegrees.trim() && (!Number.isFinite(tilt) || tilt < 0 || tilt > 90)) {
      setError('A inclinação vai de 0 a 90 graus.')
      return
    }
    const decimal = (text: string) => (text.trim() === '' ? null : text.trim().replace(',', '.'))
    setSaving(true)
    try {
      const response = await confirmFirstPlant(preview.ticket, {
        name: values.name.trim(),
        installed_power_kwp: decimal(values.installedPowerKwp),
        latitude: decimal(values.latitude),
        longitude: decimal(values.longitude),
        array_tilt_degrees: decimal(values.arrayTiltDegrees),
        array_azimuth_degrees: decimal(values.arrayAzimuthDegrees),
        module_technology: values.moduleTechnology || null,
      })
      if (response.status === 422) {
        const detail = await response
          .clone()
          .json()
          .then((body: { detail?: unknown }) => body?.detail)
          .catch(() => undefined)
        if (detail === 'connect_ticket_invalid') {
          onBack(await providerAccountErrorMessage(response, preview.provider))
          return
        }
        setError('Confira os valores: algum número está fora do esperado.')
        return
      }
      if (!response.ok) {
        if (response.status === 409) {
          const detail = await response
            .clone()
            .json()
            .then((body: { detail?: unknown }) => body?.detail)
            .catch(() => undefined)
          if (detail === 'plant_already_exists') reloadPlants()
        }
        setError(await providerAccountErrorMessage(response, preview.provider))
        return
      }
      const saved = parseFirstConnection(await response.json())
      onSaved({
        plantName: saved.plantName,
        devicesFound: saved.devicesFound,
        estimated: Object.values(saved.autoFilled).includes('ESTIMATE'),
      })
    } catch {
      setError('Não foi possível salvar agora. Tente novamente.')
    } finally {
      setSaving(false)
    }
  }

  const label = 'mb-1 flex flex-wrap items-center text-[13px] font-semibold text-[var(--color-text-primary)]'
  return (
    <Card className="sm:p-6">
      <form onSubmit={handleSubmit} noValidate className="space-y-5" aria-labelledby={`${ids}-title`}>
        <div>
          <h2
            id={`${ids}-title`}
            ref={headingRef}
            tabIndex={-1}
            className="font-display text-xl font-semibold text-[var(--color-text-primary)] focus:outline-none"
          >
            {preview.devicesFound === 0 ? 'Conta conectada, mas sem usina' : 'Encontramos sua usina'}
          </h2>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            {preview.devicesFound === 0
              ? `A conta conectou, mas a ${brand} não mostra nenhuma usina nela. Confira se é a conta certa antes de salvar.`
              : `Confira os dados lidos na ${brand}. Corrija o que precisar — o que você mudar passa a ser informado por você.`}
          </p>
          {expiresLabel && (
            <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
              Esta leitura vale até {expiresLabel}. Depois disso, é só conectar de novo.
            </p>
          )}
        </div>

        <div>
          <label htmlFor={`${ids}-name`} className={label}>
            Nome da usina <OriginBadge origin={origin('name')} brand={brand} edited={edited('name')} />
          </label>
          <input id={`${ids}-name`} value={values.name} onChange={set('name')} maxLength={120} className={INPUT_CLASS} />
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor={`${ids}-kwp`} className={label}>
              Potência dos painéis (kWp){' '}
              <OriginBadge origin={origin('dc_capacity_kwp')} brand={brand} edited={edited('installedPowerKwp')} />
            </label>
            <input id={`${ids}-kwp`} inputMode="decimal" value={values.installedPowerKwp} onChange={set('installedPowerKwp')} className={INPUT_CLASS} />
          </div>
          <fieldset>
            <legend className={label}>
              Localização{' '}
              <OriginBadge origin={origin('location')} brand={brand} edited={edited('latitude', 'longitude')} />
            </legend>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor={`${ids}-lat`} className="mb-1 block text-xs text-[var(--color-text-secondary)]">
                  Latitude
                </label>
                <input id={`${ids}-lat`} inputMode="decimal" value={values.latitude} onChange={set('latitude')} className={INPUT_CLASS} />
              </div>
              <div>
                <label htmlFor={`${ids}-lon`} className="mb-1 block text-xs text-[var(--color-text-secondary)]">
                  Longitude
                </label>
                <input id={`${ids}-lon`} inputMode="decimal" value={values.longitude} onChange={set('longitude')} className={INPUT_CLASS} />
              </div>
            </div>
            {preview.plant.city && (
              <p className="mt-1 text-xs text-[var(--color-text-secondary)]">Cidade informada pela {brand}: {preview.plant.city}</p>
            )}
          </fieldset>
          <div>
            <label htmlFor={`${ids}-tilt`} className={label}>
              Inclinação dos painéis (graus){' '}
              <OriginBadge origin={origin('array_tilt_degrees')} brand={brand} edited={edited('arrayTiltDegrees')} />
            </label>
            <input id={`${ids}-tilt`} inputMode="decimal" value={values.arrayTiltDegrees} onChange={set('arrayTiltDegrees')} className={INPUT_CLASS} />
          </div>
          <div>
            <label htmlFor={`${ids}-azimuth`} className={label}>
              Direção dos painéis{' '}
              <OriginBadge origin={origin('array_azimuth_degrees')} brand={brand} edited={edited('arrayAzimuthDegrees')} />
            </label>
            <select id={`${ids}-azimuth`} value={values.arrayAzimuthDegrees} onChange={set('arrayAzimuthDegrees')} className={INPUT_CLASS}>
              <option value="">Não sei</option>
              {!knownDirection && values.arrayAzimuthDegrees && (
                <option value={values.arrayAzimuthDegrees}>Outra ({values.arrayAzimuthDegrees}°)</option>
              )}
              {DIRECTIONS.map((item) => (
                <option key={item.degrees} value={item.degrees}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={`${ids}-tech`} className={label}>
              Tipo de painel{' '}
              <OriginBadge origin={origin('module_technology')} brand={brand} edited={edited('moduleTechnology')} />
            </label>
            <select id={`${ids}-tech`} value={values.moduleTechnology} onChange={set('moduleTechnology')} className={INPUT_CLASS}>
              <option value="">Não sei</option>
              {TECHNOLOGIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {missing.length > 0 && (
          <p className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-2 text-sm text-[var(--color-text-secondary)]">
            A {brand} não informou {missing.join(' nem ')}. Você pode salvar assim e completar depois em Minha usina — sem
            isso o sistema ainda não calcula a produção esperada.
          </p>
        )}
        {error && (
          <div role="alert" className="rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] px-3 py-2 text-sm text-[var(--color-danger-text)]">
            {error}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className={PRIMARY_BUTTON} disabled={saving} aria-busy={saving}>
            {saving ? 'Salvando...' : 'Salvar usina'}
          </button>
          <button type="button" className={SECONDARY_BUTTON} disabled={saving} onClick={() => onBack()}>
            Voltar e trocar a conta
          </button>
        </div>
      </form>
    </Card>
  )
}

export function FirstConnectionPanel() {
  const navigate = useNavigate()
  const { reload } = usePlant()
  const titleRef = useModuleTitle('Cadastrar minha usina')
  const [step, setStep] = useState<Step>('connect')
  const [brand, setBrand] = useState('fabricante')
  const [finished, setFinished] = useState(false)
  const [preview, setPreview] = useState<ConnectPreview | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [saved, setSaved] = useState<{ plantName: string; devicesFound: number | null; estimated: boolean } | null>(
    null,
  )
  const doneRef = useRef<HTMLHeadingElement>(null)
  const connectRef = useRef<HTMLDivElement>(null)
  const [focusConnect, setFocusConnect] = useState(false)

  useEffect(() => {
    if (step === 'done') doneRef.current?.focus()
    // Voltou ao passo 1 (erro, "Voltar", leitura vencida): foco no início dele.
    if (step === 'connect' && focusConnect) {
      connectRef.current?.focus()
      setFocusConnect(false)
    }
  }, [step, focusConnect])

  async function read(credentials: BrandLogin): Promise<string | null> {
    setNotice(null)
    setBrand(brandLabel(credentials.provider))
    setFinished(false)
    setStep('reading')
    const response = await previewFirstPlant(credentials).catch(() => null)
    if (!response) {
      setStep('connect')
      setFocusConnect(true)
      return 'Não foi possível concluir agora. Tente novamente.'
    }
    if (!response.ok) {
      if (response.status === 409) {
        const detail = await response
          .clone()
          .json()
          .then((body: { detail?: unknown }) => body?.detail)
          .catch(() => undefined)
        if (detail === 'plant_already_exists') reload()
      }
      setStep('connect')
      setFocusConnect(true)
      return providerAccountErrorMessage(response, credentials.provider)
    }
    const parsed = parseConnectPreview(await response.json())
    setFinished(true)
    // Um instante para a tela mostrar tudo concluído antes da revisão.
    await new Promise((resolve) => setTimeout(resolve, 500))
    setPreview(parsed)
    setStep('review')
    return null
  }

  return (
    <section aria-labelledby="first-connection-heading" className="mx-auto max-w-2xl space-y-5">
      <div className="space-y-3">
        <h1
          id="first-connection-heading"
          ref={titleRef}
          tabIndex={-1}
          className="font-display text-2xl font-semibold text-[var(--color-text-primary)] focus:outline-none"
        >
          Cadastrar minha usina
        </h1>
        <StepIndicator step={step} />
      </div>

      {notice && (
        <div role="alert" className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] px-3 py-2 text-sm text-[var(--color-warning-text)]">
          {notice}
        </div>
      )}

      {/* O formulário fica montado (só escondido) durante a leitura: se a
          marca recusar, o cliente volta com a marca e o usuário preenchidos. */}
      <div hidden={step !== 'connect'} ref={connectRef} tabIndex={-1} className="focus:outline-none">
        <p className="mb-3 text-sm leading-6 text-[var(--color-text-secondary)]">
          Escolha a marca do inversor e use o mesmo acesso do aplicativo do celular. O sistema lê os dados da sua usina na
          marca e mostra tudo para você conferir antes de salvar.
        </p>
        <Card className="sm:p-6">
          <BrandLoginForm ariaLabel="Conectar a usina" submitLabel="Ler minha usina" onSubmit={read} />
        </Card>
      </div>

      {step === 'reading' && <ReadingView brand={brand} finished={finished} />}

      {step === 'review' && preview && (
        <ReviewForm
          preview={preview}
          onBack={(message) => {
            setPreview(null)
            setNotice(message ?? null)
            setStep('connect')
            setFocusConnect(true)
          }}
          onSaved={(result) => {
            setPreview(null)
            setSaved(result)
            setStep('done')
          }}
        />
      )}

      {step === 'done' && saved && (
        <Card className="sm:p-6">
          <div className="flex items-start gap-3">
            {saved.devicesFound === 0 ? (
              <CircleAlert aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-[var(--color-warning)]" />
            ) : (
              <CheckCircle2 aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-[var(--color-success)]" />
            )}
            <div className="space-y-3">
              <h2 ref={doneRef} tabIndex={-1} className="font-display text-xl font-semibold text-[var(--color-text-primary)] focus:outline-none">
                {saved.devicesFound === 0
                  ? `Usina “${saved.plantName}” salva, mas confira a conta`
                  : `Usina “${saved.plantName}” salva!`}
              </h2>
              <p className="text-sm text-[var(--color-text-secondary)]" role="status">
                {saved.devicesFound === 0
                  ? 'A conta conectada não mostra nenhuma usina, então ainda não há produção para ler. Em Minha usina dá para trocar a conta.'
                  : 'A primeira leitura da produção acontece na próxima coleta, de madrugada.'}
                {saved.estimated && ' Os dados estimados podem ser conferidos a qualquer momento em Minha usina.'}
              </p>
              <button
                type="button"
                className={PRIMARY_BUTTON}
                onClick={() => {
                  reload()
                  navigate(DASHBOARD_OVERVIEW_PATH)
                }}
              >
                Ir para o painel
              </button>
            </div>
          </div>
        </Card>
      )}
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

