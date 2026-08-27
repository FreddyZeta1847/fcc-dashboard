/*
 * PricingEditor.tsx
 * Settings page's pricing config editor. Two parts: (1) a read-only view
 * of every currently-configured (provider, model) price pair — the 3
 * Anthropic tiers from `config.anthropic` plus everything nested under
 * `config.providers` — and (2) a small add/edit form.
 *
 * `PUT /pricing` (usePutPricing) REPLACES THE WHOLE DOCUMENT — there is no
 * partial-update endpoint. Submitting the form therefore always builds a
 * full clone of the current usePricing() data with only the one edited
 * pair changed, never a document containing just that pair, or every other
 * provider's prices would be silently deleted on write (see BACKEND--api).
 *
 * Save is two-step (this project's confirm-before-write rule,
 * FRONTEND--security): clicking "Save" only stages the pending pair and
 * opens the shared ConfirmDialog; usePutPricing().mutate is called only
 * from the dialog's "Confirm" click. Dismissing the dialog discards the
 * staged pair without writing anything.
 *
 * PROVIDER/MODEL ARE PICKED, NOT TYPED. Pricing is looked up by an exact
 * (provider, downstream_model) string match on the backend, and a miss is
 * silent — the request is counted as unpriced and dropped from savings with
 * no error anywhere. The strings are also not guessable: FCC's config says
 * `nvidia_nim/deepseek-ai/...`, but the stored provider is `NIM`. So the form
 * offers what FCC itself reports (useFccCatalog), and the provider option's
 * value is the catalog's `log_tag` — the exact string the collector will later
 * write — never `provider_id` or `display_name`, which would look right and
 * silently never match.
 *
 * Manual entry stays available behind a toggle, and engages automatically when
 * FCC is unreachable: the dashboard can stop FCC itself via /control/stop, so
 * a Settings page that only worked while FCC ran would be a trap.
 *
 * A (provider, model) pair that has no price entry anywhere in the config
 * renders as "unknown" (never blank or $0). Nothing this component
 * currently displays can actually be in that state — every row it builds
 * comes from a key that exists in the config, so a lookup always succeeds
 * — but `formatPrice` is written to hold for a future caller (e.g. a table
 * page joining live request data against pricing) that can feed it an
 * unconfigured pair.
 *
 * `validatePricingForm` gates handleSaveClick before it ever reaches the
 * pending-confirm state. This is not cosmetic input hygiene: `Number('')`
 * evaluates to `0`, not `NaN`, so an unvalidated blank price field would
 * stage (and, on Confirm, persist) a real `$0` price entry. On the backend
 * (`pricing.py`), `lookup_price` only returns `None` for a pair entirely
 * absent from the config — a pair present with `0` is `not None`, so
 * `compute_savings` treats it as priced rather than unknown, and the full
 * Anthropic-equivalent cost gets silently counted as "savings" forever for
 * every request routed through that pair. Blocking blank/negative/non-numeric
 * input here is what keeps a slipped keystroke from becoming a permanent,
 * silent accounting error on the read path.
 */
import { useId, useState } from 'react'
import { usePricing } from '../hooks/usePricing'
import { useFccCatalog } from '../hooks/useFccCatalog'
import { usePutPricing } from '../hooks/usePricingMutations'
import type { FccCatalogResponse, PriceEntry, PricingConfig } from '../api/types'
import { Card } from './Card'
import { Skeleton } from './Skeleton'
import { ConfirmDialog } from './ConfirmDialog'

interface PricingRow {
  provider: string
  model: string
  entry: PriceEntry | undefined
}

/*
 * Why a pair may not correspond to anything FCC reports. Deliberately
 * distinguishes "we checked and it is missing" from "we could not check":
 * absence of evidence is not evidence of a stale row, and flagging a
 * perfectly good row because FCC happens to be stopped would train the user
 * to ignore the warning.
 */
type PairStatus = 'ok' | 'unchecked' | 'unknown-provider' | 'unknown-model'

function buildRows(config: PricingConfig): PricingRow[] {
  const rows: PricingRow[] = []
  for (const [model, entry] of Object.entries(config.anthropic)) {
    rows.push({ provider: 'anthropic', model, entry })
  }
  for (const [provider, models] of Object.entries(config.providers)) {
    for (const [model, entry] of Object.entries(models)) {
      rows.push({ provider, model, entry })
    }
  }
  return rows
}

function pairStatus(
  catalog: FccCatalogResponse | undefined,
  provider: string,
  model: string,
): PairStatus {
  if (!catalog || !catalog.available) {
    return 'unchecked'
  }
  // Anthropic tiers are the gateway-side billing reference, not an FCC
  // provider — FCC never reports them, so they are not checkable here.
  if (provider === 'anthropic') {
    return 'unchecked'
  }
  const match = catalog.providers.find((candidate) => candidate.log_tag === provider)
  if (!match) {
    return 'unknown-provider'
  }
  // An empty model list means FCC's model cache is not warm yet, not that the
  // provider serves nothing. Treat it as "cannot check".
  if (match.models.length === 0) {
    return 'unchecked'
  }
  return match.models.includes(model) ? 'ok' : 'unknown-model'
}

function pairStatusHint(status: PairStatus): string | null {
  if (status === 'unknown-provider') {
    return 'FCC does not currently report a provider with this name. Requests may never match this price.'
  }
  if (status === 'unknown-model') {
    return 'FCC reports this provider but not this model. Requests may never match this price.'
  }
  return null
}

function formatPrice(value: number | undefined): string {
  return value === undefined ? 'unknown' : `$${value}`
}

function validatePricingForm(
  provider: string,
  model: string,
  inputPrice: string,
  outputPrice: string,
): string | null {
  if (provider.trim() === '') {
    return 'Provider is required.'
  }
  if (model.trim() === '') {
    return 'Model is required.'
  }
  if (inputPrice.trim() === '' || !Number.isFinite(Number(inputPrice)) || Number(inputPrice) < 0) {
    return 'Input price must be a non-negative number.'
  }
  if (outputPrice.trim() === '' || !Number.isFinite(Number(outputPrice)) || Number(outputPrice) < 0) {
    return 'Output price must be a non-negative number.'
  }
  return null
}

function withPairMerged(
  config: PricingConfig,
  provider: string,
  model: string,
  entry: PriceEntry,
): PricingConfig {
  if (provider === 'anthropic') {
    return { ...config, anthropic: { ...config.anthropic, [model]: entry } }
  }
  return {
    ...config,
    providers: {
      ...config.providers,
      [provider]: { ...config.providers[provider], [model]: entry },
    },
  }
}

const inputStyle: React.CSSProperties = {
  font: 'inherit',
  fontSize: 13,
  padding: '8px 11px',
  borderRadius: 9,
  border: '1px solid var(--border2)',
  background: 'var(--card2)',
  color: 'var(--text)',
  outline: 'none',
  boxSizing: 'border-box',
  width: '100%',
}

const labelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 5,
  fontSize: 11.5,
  fontWeight: 700,
  color: 'var(--faint)',
}

const toggleStyle: React.CSSProperties = {
  font: 'inherit',
  fontSize: 12,
  fontWeight: 700,
  padding: '4px 10px',
  borderRadius: 8,
  border: '1px solid var(--border2)',
  background: 'transparent',
  color: 'var(--muted)',
  cursor: 'pointer',
}

export function PricingEditor() {
  const { data, isLoading, isError } = usePricing()
  const { data: catalog } = useFccCatalog()
  const putPricing = usePutPricing()

  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [inputPrice, setInputPrice] = useState('')
  const [outputPrice, setOutputPrice] = useState('')
  const [pendingConfirm, setPendingConfirm] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [manualRequested, setManualRequested] = useState(false)

  const providerId = useId()
  const modelId = useId()
  const inputPriceId = useId()
  const outputPriceId = useId()

  if (isError) {
    return (
      <Card accent="red">
        <p style={{ color: 'var(--red)' }}>Couldn't load pricing config.</p>
      </Card>
    )
  }
  if (isLoading || !data) {
    return (
      <Card style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Skeleton width="60%" height={14} />
        <Skeleton width="70%" height={14} delay={0.15} />
        <Skeleton width="55%" height={14} delay={0.3} />
      </Card>
    )
  }

  const rows = buildRows(data)

  // Derived rather than synced into state with an effect: the pickers are
  // usable only when FCC actually returned providers, and manual entry is
  // whatever the user asked for OR the forced fallback.
  const pickersUsable = catalog?.available === true && catalog.providers.length > 0
  const manualEntry = manualRequested || !pickersUsable
  const selectedProvider = catalog?.providers.find((p) => p.log_tag === provider)
  const modelOptions = selectedProvider?.models ?? []

  function handleProviderPicked(nextProvider: string) {
    setProvider(nextProvider)
    // The model list is provider-scoped, so a stale selection from the
    // previous provider would be a silently wrong pair.
    setModel('')
  }

  function handleToggleManual() {
    setManualRequested((current) => !current)
    setProvider('')
    setModel('')
    setValidationError(null)
  }

  function handleSaveClick() {
    const error = validatePricingForm(provider, model, inputPrice, outputPrice)
    if (error) {
      setValidationError(error)
      return
    }
    setValidationError(null)
    setPendingConfirm(true)
  }

  function handleCancelClick() {
    setPendingConfirm(false)
  }

  function handleConfirmClick() {
    if (!data) {
      return
    }
    const entry: PriceEntry = {
      input_per_million: Number(inputPrice),
      output_per_million: Number(outputPrice),
    }
    const nextConfig = withPairMerged(data, provider, model, entry)
    putPricing.mutate(nextConfig, {
      onSuccess: () => {
        setProvider('')
        setModel('')
        setInputPrice('')
        setOutputPrice('')
        setPendingConfirm(false)
      },
    })
  }

  return (
    <Card accent="green">
      <h2 style={{ fontSize: 16, fontWeight: 800, marginBottom: 4 }}>Pricing</h2>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
        Cost per million tokens, used to compute savings. Missing prices show as unknown.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 150px 150px', gap: 8, padding: '6px 10px', fontSize: 11, fontWeight: 800, letterSpacing: '.07em', textTransform: 'uppercase', color: 'var(--faint)' }}>
        <span>Provider</span>
        <span>Model</span>
        <span style={{ textAlign: 'right' }}>Input / MTok</span>
        <span style={{ textAlign: 'right' }}>Output / MTok</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', marginBottom: 20 }}>
        {rows.map((row) => {
          const status = pairStatus(catalog, row.provider, row.model)
          const hint = pairStatusHint(status)
          return (
            <div
              key={`${row.provider}:${row.model}`}
              style={{ display: 'grid', gridTemplateColumns: '140px 1fr 150px 150px', gap: 8, alignItems: 'center', padding: '9px 10px', borderTop: '1px solid var(--border)' }}
            >
              <span style={{ fontWeight: 700 }}>
                {row.provider}
                {hint && (
                  <span
                    role="img"
                    aria-label="Not reported by FCC"
                    title={hint}
                    style={{ marginLeft: 6, color: 'var(--amber)', cursor: 'help' }}
                  >
                    ⚠
                  </span>
                )}
              </span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, color: 'var(--muted)' }}>{row.model}</span>
              <span style={{ textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, fontStyle: row.entry?.input_per_million === undefined ? 'italic' : 'normal', color: row.entry?.input_per_million === undefined ? 'var(--faint)' : 'var(--text)' }}>
                {formatPrice(row.entry?.input_per_million)}
              </span>
              <span style={{ textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, fontStyle: row.entry?.output_per_million === undefined ? 'italic' : 'normal', color: row.entry?.output_per_million === undefined ? 'var(--faint)' : 'var(--text)' }}>
                {formatPrice(row.entry?.output_per_million)}
              </span>
            </div>
          )
        })}
      </div>

      <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 14, padding: '18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, gap: 12 }}>
          <h3 style={{ fontSize: 13, fontWeight: 800 }}>Add or edit a price pair</h3>
          {pickersUsable && (
            <button type="button" onClick={handleToggleManual} style={toggleStyle}>
              {manualRequested ? 'Choose from FCC' : 'Enter manually'}
            </button>
          )}
        </div>

        {!pickersUsable && (
          <p style={{ fontSize: 12.5, color: 'var(--amber)', marginBottom: 12 }}>
            {catalog?.error ?? 'Could not read FCC’s configured models.'} Falling back to manual entry.
          </p>
        )}

        <form
          style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr 1fr 1fr auto', gap: 10, alignItems: 'end' }}
          onSubmit={(event) => event.preventDefault()}
        >
          <label htmlFor={providerId} style={labelStyle}>
            Provider
            {manualEntry ? (
              <input id={providerId} type="text" value={provider} onChange={(event) => setProvider(event.target.value)} style={inputStyle} placeholder="groq" />
            ) : (
              <select
                id={providerId}
                value={provider}
                onChange={(event) => handleProviderPicked(event.target.value)}
                style={inputStyle}
              >
                <option value="">Select a provider…</option>
                {catalog?.providers.map((candidate) => (
                  /* value is log_tag — the string the collector stores. */
                  <option key={candidate.provider_id} value={candidate.log_tag}>
                    {candidate.display_name} ({candidate.log_tag})
                  </option>
                ))}
              </select>
            )}
          </label>
          <label htmlFor={modelId} style={labelStyle}>
            Model
            {manualEntry ? (
              <input id={modelId} type="text" value={model} onChange={(event) => setModel(event.target.value)} style={inputStyle} placeholder="llama-3.3-70b" />
            ) : (
              <select
                id={modelId}
                value={model}
                onChange={(event) => setModel(event.target.value)}
                style={inputStyle}
                disabled={!selectedProvider}
              >
                <option value="">
                  {!selectedProvider
                    ? 'Select a provider first'
                    : modelOptions.length === 0
                      ? 'No models discovered yet'
                      : 'Select a model…'}
                </option>
                {modelOptions.map((candidate) => (
                  <option key={candidate} value={candidate}>
                    {candidate}
                  </option>
                ))}
              </select>
            )}
          </label>
          <label htmlFor={inputPriceId} style={labelStyle}>
            Input $/MTok
            <input id={inputPriceId} type="number" value={inputPrice} onChange={(event) => setInputPrice(event.target.value)} style={inputStyle} placeholder="0.59" />
          </label>
          <label htmlFor={outputPriceId} style={labelStyle}>
            Output $/MTok
            <input id={outputPriceId} type="number" value={outputPrice} onChange={(event) => setOutputPrice(event.target.value)} style={inputStyle} placeholder="0.79" />
          </label>
          <button
            type="button"
            onClick={handleSaveClick}
            style={{ font: 'inherit', fontSize: 13, fontWeight: 800, padding: '9px 18px', borderRadius: 9, border: 'none', background: 'var(--green)', color: '#0c1410', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Save price
          </button>
        </form>
        {validationError && (
          <p role="alert" style={{ marginTop: 12, fontSize: 13, color: 'var(--red)' }}>
            {validationError}
          </p>
        )}
      </div>

      {pendingConfirm && (
        <ConfirmDialog
          title="Save this price?"
          body={`${provider} / ${model} will be set to $${inputPrice} in, $${outputPrice} out per MTok. This immediately affects how savings are calculated.`}
          confirmLabel="Save price"
          confirmColor="var(--green)"
          onConfirm={handleConfirmClick}
          onCancel={handleCancelClick}
        />
      )}
    </Card>
  )
}
