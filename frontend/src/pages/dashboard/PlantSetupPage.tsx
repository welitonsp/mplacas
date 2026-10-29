import { FormEvent, ReactNode, useState } from 'react'
import { Link } from 'react-router'
import { CheckCircle2, Circle } from 'lucide-react'
import {
  fetchPlantSetup,
  updateFinancialConfiguration,
  updatePlantLocation,
  updateTechnicalConfiguration,
  type TechnicalConfigurationUpdatePayload,
} from '../../lib/api'
import {
  parsePlantSetup,
  type ModuleTechnology,
  type PlantSetup,
  type PlantSetupItemKey,
} from '../../lib/dashboard/plant-setup-contracts'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { DASHBOARD_FINANCIAL_PATH } from '../../routes'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/EmptyState'
import { LoadingAnnouncement } from '../../components/LoadingAnnouncement'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { PageHeader } from '../../components/PageHeader'
import { ProviderConnectionSection } from '../../components/ProviderConnectionSection'
import { RetryableError } from '../../components/RetryableError'
import { SectionTitle } from '../../components/SectionTitle'

// "Minha usina" — onde o próprio cliente informa os dados da usina, sem
// depender de suporte (o sistema será vendido a outros donos de usina).
//
// O checklist vem pronto do backend (`GET /plants/{id}/setup`): a regra de
// "item feito" não é decidida aqui. Cada item diz o que libera no sistema,
// para o dono entender por que vale preencher. Os formulários usam as rotas
// de escrita que já existiam (técnica, localização, investimento); salvar
// recarrega o checklist.

const ITEM_COPY: Record<PlantSetupItemKey, { title: string; unlocks: string; anchor: string }> = {
  LOCATION: {
    title: 'Localização da usina',
    unlocks: 'Clima e sol do local, base da produção esperada.',
    anchor: 'localizacao',
  },
  DC_CAPACITY: {
    title: 'Potência das placas (kWp)',
    unlocks: 'Produção esperada e rendimento por kWp.',
    anchor: 'instalacao',
  },
  COMMISSIONED_ON: {
    title: 'Mês em que a usina foi ligada',
    unlocks: 'Retorno do investimento e quantos meses de histórico esperar.',
    anchor: 'instalacao',
  },
  ORIENTATION: {
    title: 'Inclinação e direção das placas',
    unlocks: 'Quanto sol chega de fato nas placas.',
    anchor: 'instalacao',
  },
  MODULE_TECHNOLOGY: {
    title: 'Tecnologia das placas',
    unlocks: 'Ajuste da produção esperada pela temperatura.',
    anchor: 'instalacao',
  },
  INVESTMENT: {
    title: 'Valor investido',
    unlocks: 'Retorno do investimento (ROI) e tempo para se pagar.',
    anchor: 'investimento',
  },
  CONFIRMED_BILL: {
    title: 'Primeira fatura confirmada',
    unlocks: 'Economia real na conta de luz.',
    anchor: 'faturas',
  },
}

const TECHNOLOGY_OPTIONS: ReadonlyArray<{ value: ModuleTechnology; label: string }> = [
  { value: 'MONOCRYSTALLINE_SILICON', label: 'Monocristalino (o mais comum hoje)' },
  { value: 'POLYCRYSTALLINE_SILICON', label: 'Policristalino' },
  { value: 'THIN_FILM', label: 'Filme fino' },
  { value: 'OTHER', label: 'Outra / não sei' },
]

// Azimute medido a partir do Norte, no sentido horário (0° = Norte, 90° =
// Leste), a mesma convenção de `photovoltaic/poa.py`. No Brasil, o ideal é
// virar as placas para o Norte.
const DIRECTION_OPTIONS: ReadonlyArray<{ degrees: string; label: string }> = [
  { degrees: '0', label: 'Norte (o ideal no Brasil)' },
  { degrees: '45', label: 'Nordeste' },
  { degrees: '90', label: 'Leste' },
  { degrees: '135', label: 'Sudeste' },
  { degrees: '180', label: 'Sul' },
  { degrees: '225', label: 'Sudoeste' },
  { degrees: '270', label: 'Oeste' },
  { degrees: '315', label: 'Noroeste' },
]
const CUSTOM_DIRECTION = 'custom'

// `min-h-[44px]`: os campos tinham 41 px (auditoria visual, item 15).
const INPUT_CLASS =
  'min-h-[44px] w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder-[var(--color-gray-500)] transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] disabled:opacity-50 motion-reduce:transition-none'

const PRIMARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-semibold text-[var(--color-on-brand)] shadow-sm transition-colors duration-200 hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

const SECONDARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-200 hover:bg-[var(--color-surface-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

type Feedback = { tone: 'success' | 'error'; message: string } | null

// Aceita vírgula decimal ("4,4") e devolve o texto que o backend espera
// ("4.4"); `null` para vazio, `undefined` para inválido.
function normalizeDecimal(raw: string): string | null | undefined {
  const trimmed = raw.trim().replace(/\s/g, '')
  if (trimmed === '') return null
  const normalized = trimmed.includes(',') ? trimmed.replace(/\./g, '').replace(',', '.') : trimmed
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return undefined
  return normalized
}

// "Mudou?" sem a armadilha de `Number(null) === 0`: um valor novo 0 (Norte,
// placa deitada) contra "nada salvo" é mudança, e precisa ser enviado.
function differs(next: string, saved: string | null): boolean {
  return saved == null || Number(next) !== Number(saved)
}

function toInput(value: string | null): string {
  if (value == null) return ''
  const numeric = Number(value)
  return Number.isFinite(numeric) ? String(numeric).replace('.', ',') : value
}

async function saveErrorMessage(response: Response): Promise<string> {
  if (response.status === 403) return 'Seu perfil não tem permissão para alterar os dados da usina.'
  if (response.status === 404) return 'Usina não encontrada.'
  if (response.status === 422) return 'Algum valor está fora do permitido. Revise os campos e tente de novo.'
  return 'Não foi possível salvar agora. Tente novamente.'
}

function Field({
  id,
  label,
  help,
  children,
}: {
  id: string
  label: string
  help?: string
  children: ReactNode
}) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1 block text-[13px] font-semibold text-[var(--color-text-primary)]">
        {label}
      </label>
      {children}
      {help && (
        <p id={`${id}-help`} className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">
          {help}
        </p>
      )}
    </div>
  )
}

function FeedbackLine({ feedback }: { feedback: Feedback }) {
  if (!feedback) return null
  const className =
    feedback.tone === 'success'
      ? 'border-[var(--color-success)]/30 bg-[var(--color-success-light)] text-[var(--color-success-text)]'
      : 'border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] text-[var(--color-danger-text)]'
  return (
    <div role={feedback.tone === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-3 py-2 text-sm ${className}`}>
      {feedback.message}
    </div>
  )
}

function SetupChecklist({ setup }: { setup: PlantSetup }) {
  const percent = setup.total > 0 ? Math.round((setup.completed / setup.total) * 100) : 0
  const complete = setup.completed === setup.total
  return (
    <Card className="sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">Cadastro da usina</p>
          <p className="mt-1 font-display text-2xl font-semibold tabular-nums text-[var(--color-text-primary)]">
            {setup.completed} de {setup.total} itens informados
          </p>
        </div>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {complete ? 'Tudo pronto: o sistema tem o que precisa.' : 'Cada item libera uma parte do sistema.'}
        </p>
      </div>
      <div
        className="mt-4 h-2 w-full overflow-hidden rounded-full bg-[var(--color-chart-track)]"
        role="progressbar"
        aria-label="Progresso do cadastro"
        aria-valuemin={0}
        aria-valuemax={setup.total}
        aria-valuenow={setup.completed}
      >
        <div className="h-full rounded-full bg-[var(--color-success)]" style={{ width: `${percent}%` }} />
      </div>

      <ul className="mt-5 divide-y divide-[var(--color-border)]" aria-label="Itens do cadastro">
        {setup.items.map((item) => {
          const copy = ITEM_COPY[item.key]
          const Icon = item.done ? CheckCircle2 : Circle
          return (
            <li key={item.key} className="flex items-start gap-3 py-3">
              <Icon
                aria-hidden="true"
                className={`mt-0.5 h-5 w-5 shrink-0 ${
                  item.done ? 'text-[var(--color-success)]' : 'text-[var(--color-gray-400)]'
                }`}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">
                  {copy.title}
                  <span className="sr-only">{item.done ? ': informado' : ': pendente'}</span>
                </p>
                <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">Libera: {copy.unlocks}</p>
              </div>
              {!item.done && (
                <a
                  href={`#${copy.anchor}`}
                  className="inline-flex min-h-[44px] shrink-0 items-center rounded-md px-3 text-[13px] font-semibold text-[var(--color-brand-primary)] underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
                >
                  Informar
                </a>
              )}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

function InstallationForm({ setup, onSaved }: { setup: PlantSetup; onSaved: () => void }) {
  const initialDirection =
    setup.arrayAzimuthDegrees == null
      ? ''
      : (DIRECTION_OPTIONS.find((option) => Number(option.degrees) === Number(setup.arrayAzimuthDegrees))
          ?.degrees ?? CUSTOM_DIRECTION)
  const [month, setMonth] = useState(setup.commissionedOn ? setup.commissionedOn.slice(0, 7) : '')
  const [dcKwp, setDcKwp] = useState(toInput(setup.dcCapacityKwp))
  const [acKw, setAcKw] = useState(toInput(setup.acCapacityKw))
  const [technology, setTechnology] = useState<string>(setup.moduleTechnology ?? '')
  const [tilt, setTilt] = useState(toInput(setup.arrayTiltDegrees))
  const [direction, setDirection] = useState(initialDirection)
  const [customAzimuth, setCustomAzimuth] = useState(
    initialDirection === CUSTOM_DIRECTION ? toInput(setup.arrayAzimuthDegrees) : '',
  )
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFeedback(null)
    const payload: TechnicalConfigurationUpdatePayload = {}

    if (month) {
      if (!/^\d{4}-\d{2}$/.test(month)) {
        setFeedback({ tone: 'error', message: 'Informe o mês de ligação no formato mês/ano.' })
        return
      }
      const now = new Date()
      const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
      if (month > current) {
        setFeedback({ tone: 'error', message: 'O mês de ligação não pode estar no futuro.' })
        return
      }
      // Só envia se mudou de mês: preserva um dia já gravado (ex.: dia 15).
      if (month !== (setup.commissionedOn ?? '').slice(0, 7)) payload.commissioned_on = `${month}-01`
    }

    const numberFields: Array<[string, string, keyof TechnicalConfigurationUpdatePayload, string | null]> = [
      ['Potência das placas', dcKwp, 'dc_capacity_kwp', setup.dcCapacityKwp],
      ['Potência do inversor', acKw, 'ac_capacity_kw', setup.acCapacityKw],
      ['Inclinação', tilt, 'array_tilt_degrees', setup.arrayTiltDegrees],
    ]
    for (const [label, raw, key, original] of numberFields) {
      const value = normalizeDecimal(raw)
      if (value === undefined) {
        setFeedback({ tone: 'error', message: `${label}: use só números, por exemplo 4,4.` })
        return
      }
      if (value !== null && differs(value, original)) payload[key] = value
    }

    let azimuth: string | null | undefined = null
    if (direction === CUSTOM_DIRECTION) azimuth = normalizeDecimal(customAzimuth)
    else if (direction !== '') azimuth = direction
    if (azimuth === undefined || (azimuth !== null && (Number(azimuth) < 0 || Number(azimuth) >= 360))) {
      setFeedback({ tone: 'error', message: 'Direção em graus: use um número de 0 a 359 (0 = Norte, 90 = Leste).' })
      return
    }
    if (azimuth !== null && differs(azimuth, setup.arrayAzimuthDegrees)) {
      payload.array_azimuth_degrees = azimuth
    }
    if (technology !== '' && technology !== setup.moduleTechnology) payload.module_technology = technology

    if (Object.keys(payload).length === 0) {
      setFeedback({ tone: 'success', message: 'Nada mudou desde o último salvamento.' })
      return
    }

    setSaving(true)
    try {
      const response = await updateTechnicalConfiguration(setup.plantId, payload)
      if (!response.ok) {
        setFeedback({ tone: 'error', message: await saveErrorMessage(response) })
        return
      }
      setFeedback({ tone: 'success', message: 'Dados da instalação salvos.' })
      onSaved()
    } catch {
      setFeedback({ tone: 'error', message: 'Não foi possível salvar agora. Tente novamente.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section id="instalacao" aria-labelledby="instalacao-heading" className="scroll-mt-24">
      <SectionTitle as="h2" id="instalacao-heading">
        Instalação
      </SectionTitle>
      <Card className="sm:p-6">
        <form onSubmit={handleSubmit} noValidate className="space-y-5" aria-label="Dados da instalação">
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <Field
              id="setup-commissioned"
              label="Mês em que a usina foi ligada"
              help="O mês da primeira geração ou da liberação pela distribuidora."
            >
              <input
                id="setup-commissioned"
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                disabled={saving}
                placeholder="2025-09"
                aria-describedby="setup-commissioned-help"
                className={INPUT_CLASS}
              />
            </Field>
            <Field
              id="setup-dc"
              label="Potência das placas (kWp)"
              help="Soma de todas as placas. Ex.: 8 placas de 550 W = 4,4 kWp."
            >
              <input
                id="setup-dc"
                type="text"
                inputMode="decimal"
                value={dcKwp}
                onChange={(e) => setDcKwp(e.target.value)}
                disabled={saving}
                placeholder="Ex.: 4,4"
                aria-describedby="setup-dc-help"
                className={INPUT_CLASS}
              />
            </Field>
            <Field
              id="setup-ac"
              label="Potência do inversor (kW, opcional)"
              help="Está na etiqueta ou no manual do inversor."
            >
              <input
                id="setup-ac"
                type="text"
                inputMode="decimal"
                value={acKw}
                onChange={(e) => setAcKw(e.target.value)}
                disabled={saving}
                placeholder="Ex.: 3"
                aria-describedby="setup-ac-help"
                className={INPUT_CLASS}
              />
            </Field>
            <Field id="setup-tech" label="Tecnologia das placas" help="Se não souber, escolha monocristalino.">
              <select
                id="setup-tech"
                value={technology}
                onChange={(e) => setTechnology(e.target.value)}
                disabled={saving}
                aria-describedby="setup-tech-help"
                className={INPUT_CLASS}
              >
                <option value="">Selecione</option>
                {TECHNOLOGY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              id="setup-tilt"
              label="Inclinação das placas (graus)"
              help="Telhado comum fica entre 10° e 20°. Placa deitada = 0°."
            >
              <input
                id="setup-tilt"
                type="text"
                inputMode="decimal"
                value={tilt}
                onChange={(e) => setTilt(e.target.value)}
                disabled={saving}
                placeholder="Ex.: 15"
                aria-describedby="setup-tilt-help"
                className={INPUT_CLASS}
              />
            </Field>
            <Field
              id="setup-direction"
              label="Para onde as placas estão viradas"
              help="A direção para a qual a face da placa aponta."
            >
              <select
                id="setup-direction"
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
                disabled={saving}
                aria-describedby="setup-direction-help"
                className={INPUT_CLASS}
              >
                <option value="">Selecione</option>
                {DIRECTION_OPTIONS.map((option) => (
                  <option key={option.degrees} value={option.degrees}>
                    {option.label}
                  </option>
                ))}
                <option value={CUSTOM_DIRECTION}>Outro ângulo (graus)</option>
              </select>
            </Field>
            {direction === CUSTOM_DIRECTION && (
              <Field
                id="setup-azimuth"
                label="Ângulo da direção (graus)"
                help="0 = Norte, 90 = Leste, 180 = Sul, 270 = Oeste."
              >
                <input
                  id="setup-azimuth"
                  type="text"
                  inputMode="decimal"
                  value={customAzimuth}
                  onChange={(e) => setCustomAzimuth(e.target.value)}
                  disabled={saving}
                  aria-describedby="setup-azimuth-help"
                  className={INPUT_CLASS}
                />
              </Field>
            )}
          </div>
          <FeedbackLine feedback={feedback} />
          <button type="submit" className={PRIMARY_BUTTON} disabled={saving} aria-busy={saving}>
            {saving ? 'Salvando...' : 'Salvar instalação'}
          </button>
          <LoadingAnnouncement active={saving} message="Salvando dados da instalação, aguarde." />
        </form>
      </Card>
    </section>
  )
}

function LocationForm({ setup, onSaved }: { setup: PlantSetup; onSaved: () => void }) {
  const [latitude, setLatitude] = useState(toInput(setup.latitude))
  const [longitude, setLongitude] = useState(toInput(setup.longitude))
  const [saving, setSaving] = useState(false)
  const [locating, setLocating] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)
  const geolocationAvailable = typeof navigator !== 'undefined' && 'geolocation' in navigator

  function useDeviceLocation() {
    setFeedback(null)
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude.toFixed(5).replace('.', ','))
        setLongitude(position.coords.longitude.toFixed(5).replace('.', ','))
        setLocating(false)
        setFeedback({ tone: 'success', message: 'Localização preenchida. Confira e salve.' })
      },
      () => {
        setLocating(false)
        setFeedback({
          tone: 'error',
          message: 'Não foi possível obter a localização. Permita o acesso no navegador ou digite os números.',
        })
      },
      { enableHighAccuracy: true, timeout: 15000 },
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFeedback(null)
    const lat = normalizeDecimal(latitude)
    const lon = normalizeDecimal(longitude)
    if (lat == null || lon == null) {
      setFeedback({ tone: 'error', message: 'Informe a latitude e a longitude, por exemplo -17,74 e -48,62.' })
      return
    }
    if (Math.abs(Number(lat)) > 90 || Math.abs(Number(lon)) > 180) {
      setFeedback({ tone: 'error', message: 'Latitude vai de -90 a 90 e longitude de -180 a 180.' })
      return
    }
    setSaving(true)
    try {
      const response = await updatePlantLocation(setup.plantId, { latitude: lat, longitude: lon })
      if (!response.ok) {
        setFeedback({ tone: 'error', message: await saveErrorMessage(response) })
        return
      }
      setFeedback({ tone: 'success', message: 'Localização salva. O clima do local passa a ser coletado.' })
      onSaved()
    } catch {
      setFeedback({ tone: 'error', message: 'Não foi possível salvar agora. Tente novamente.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section id="localizacao" aria-labelledby="localizacao-heading" className="scroll-mt-24">
      <SectionTitle as="h2" id="localizacao-heading">
        Localização
      </SectionTitle>
      <Card className="sm:p-6">
        <form onSubmit={handleSubmit} noValidate className="space-y-5" aria-label="Localização da usina">
          <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
            Se estiver na usina agora, use a localização do aparelho. Se não, abra o Google Maps, toque e segure sobre
            o telhado e copie os dois números que aparecem.
          </p>
          {geolocationAvailable && (
            <button
              type="button"
              className={SECONDARY_BUTTON}
              onClick={useDeviceLocation}
              disabled={saving || locating}
              aria-busy={locating}
            >
              {locating ? 'Obtendo localização...' : 'Usar a localização deste aparelho'}
            </button>
          )}
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field id="setup-lat" label="Latitude" help="No Brasil, quase sempre negativa. Ex.: -17,74.">
              <input
                id="setup-lat"
                type="text"
                inputMode="decimal"
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                disabled={saving}
                aria-describedby="setup-lat-help"
                className={INPUT_CLASS}
              />
            </Field>
            <Field id="setup-lon" label="Longitude" help="No Brasil, sempre negativa. Ex.: -48,62.">
              <input
                id="setup-lon"
                type="text"
                inputMode="decimal"
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                disabled={saving}
                aria-describedby="setup-lon-help"
                className={INPUT_CLASS}
              />
            </Field>
          </div>
          <FeedbackLine feedback={feedback} />
          <button type="submit" className={PRIMARY_BUTTON} disabled={saving} aria-busy={saving}>
            {saving ? 'Salvando...' : 'Salvar localização'}
          </button>
          <LoadingAnnouncement active={saving} message="Salvando localização, aguarde." />
        </form>
      </Card>
    </section>
  )
}

function InvestmentForm({ setup, onSaved }: { setup: PlantSetup; onSaved: () => void }) {
  const [amount, setAmount] = useState(
    setup.investmentAmountBrl == null
      ? ''
      : Number(setup.investmentAmountBrl).toLocaleString('pt-BR', { minimumFractionDigits: 2 }),
  )
  const [recordedOn, setRecordedOn] = useState(setup.investmentRecordedOn ?? '')
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFeedback(null)
    const value = normalizeDecimal(amount.replace(/^R\$\s*/, ''))
    if (value == null || Number(value) <= 0) {
      setFeedback({ tone: 'error', message: 'Informe o valor investido, maior que zero. Ex.: 11.200,00.' })
      return
    }
    const payload: { investment_amount_brl?: string; investment_recorded_on?: string | null } = {}
    if (differs(value, setup.investmentAmountBrl)) payload.investment_amount_brl = Number(value).toFixed(2)
    if ((recordedOn || null) !== setup.investmentRecordedOn) payload.investment_recorded_on = recordedOn || null
    if (Object.keys(payload).length === 0) {
      setFeedback({ tone: 'success', message: 'Nada mudou desde o último salvamento.' })
      return
    }
    setSaving(true)
    try {
      const response = await updateFinancialConfiguration(setup.plantId, payload)
      if (!response.ok) {
        setFeedback({ tone: 'error', message: await saveErrorMessage(response) })
        return
      }
      setFeedback({ tone: 'success', message: 'Investimento salvo.' })
      onSaved()
    } catch {
      setFeedback({ tone: 'error', message: 'Não foi possível salvar agora. Tente novamente.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section id="investimento" aria-labelledby="investimento-heading" className="scroll-mt-24">
      <SectionTitle as="h2" id="investimento-heading">
        Investimento
      </SectionTitle>
      <Card className="sm:p-6">
        <form onSubmit={handleSubmit} noValidate className="space-y-5" aria-label="Investimento na usina">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field
              id="setup-amount"
              label="Valor total investido (R$)"
              help="Tudo o que foi pago: placas, inversor, instalação, projeto e homologação."
            >
              <input
                id="setup-amount"
                type="text"
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                disabled={saving}
                placeholder="Ex.: 11.200,00"
                aria-describedby="setup-amount-help"
                className={INPUT_CLASS}
              />
            </Field>
            <Field id="setup-paid-on" label="Data do pagamento (opcional)" help="Usada só como referência.">
              <input
                id="setup-paid-on"
                type="date"
                value={recordedOn}
                onChange={(e) => setRecordedOn(e.target.value)}
                disabled={saving}
                aria-describedby="setup-paid-on-help"
                className={INPUT_CLASS}
              />
            </Field>
          </div>
          <FeedbackLine feedback={feedback} />
          <button type="submit" className={PRIMARY_BUTTON} disabled={saving} aria-busy={saving}>
            {saving ? 'Salvando...' : 'Salvar investimento'}
          </button>
          <LoadingAnnouncement active={saving} message="Salvando investimento, aguarde." />
        </form>
      </Card>
    </section>
  )
}

function BillsStatus({ setup }: { setup: PlantSetup }) {
  return (
    <section id="faturas" aria-labelledby="faturas-heading" className="scroll-mt-24">
      <SectionTitle as="h2" id="faturas-heading">
        Faturas de energia
      </SectionTitle>
      <Card className="sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-[var(--color-text-primary)]">
              {setup.confirmedBills === 1 ? '1 fatura confirmada' : `${setup.confirmedBills} faturas confirmadas`}
              {setup.pendingBills > 0 &&
                ` · ${setup.pendingBills === 1 ? '1 aguardando' : `${setup.pendingBills} aguardando`} conferência`}
            </p>
            <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
              Importe a fatura da distribuidora em PDF, todo mês. É dela que sai a economia real.
            </p>
          </div>
          <Link to={DASHBOARD_FINANCIAL_PATH} className={SECONDARY_BUTTON}>
            Importar ou conferir faturas
          </Link>
        </div>
      </Card>
    </section>
  )
}

export function PlantSetupPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  const headingRef = useModuleTitle('Minha usina')
  const setup = usePlantResource({
    plantId,
    fetcher: fetchPlantSetup,
    parse: parsePlantSetup,
    errorMessage: 'Erro ao buscar os dados da usina.',
  })

  if (plantsLoading) return <MetricCardSkeletonGrid />
  if (plantsError) {
    return <RetryableError message={plantsError} onRetry={() => window.location.reload()} className="mb-6" />
  }
  if (!plantId || plants.length === 0) {
    return (
      <EmptyState
        eyebrow="Configuração inicial"
        title="Nenhuma usina cadastrada"
        description="Nenhuma usina cadastrada para esta conta ainda. Quando uma usina for vinculada, os dados dela aparecem aqui."
        tone="brand"
      />
    )
  }

  const data = setup.data
  return (
    <>
      <PageHeader
        eyebrow="Cadastro"
        title="Minha usina"
        description={
          data
            ? `Informe os dados de ${data.name}. Cada item preenchido libera uma parte do sistema.`
            : 'Informe os dados da sua usina. Cada item preenchido libera uma parte do sistema.'
        }
        headingRef={headingRef}
      />
      {setup.error && <RetryableError message={setup.error} onRetry={setup.refetch} className="mb-6" />}
      {!data && !setup.error && <MetricCardSkeletonGrid />}
      {data && (
        // Os formulários guardam o que o usuário digita; ao trocar de usina
        // recomeçam dos dados da usina nova (`key`). Depois de salvar, ficam
        // como estão (o texto digitado já é o que foi gravado) e só o
        // checklist é recarregado.
        <div className="space-y-6" key={data.plantId}>
          <SetupChecklist setup={data} />
          <ProviderConnectionSection plantId={data.plantId} />
          <InstallationForm setup={data} onSaved={setup.refetch} />
          <LocationForm setup={data} onSaved={setup.refetch} />
          <InvestmentForm setup={data} onSaved={setup.refetch} />
          <BillsStatus setup={data} />
        </div>
      )}
    </>
  )
}
