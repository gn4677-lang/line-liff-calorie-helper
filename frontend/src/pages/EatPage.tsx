import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../AppContext'
import { FullScreenSheet } from '../components/Sheets'
import type { EatFeedCandidate, FavoriteStore, GoldenOrder, SavedPlace } from '../types'

type LocationState = {
  mode: 'none' | 'saved_place' | 'manual' | 'geolocation'
  saved_place_id?: number
  query?: string
  lat?: number
  lng?: number
  label?: string
}

function sourceLabel(sourceType: string): string {
  switch (sourceType) {
    case 'golden_order':
      return '穩定選項'
    case 'favorite_food':
      return '常吃食物'
    case 'favorite_store':
      return '常去店家'
    case 'nearby_heuristic':
      return '附近候選'
    case 'external_nearby_result':
      return '外部找到'
    default:
      return '推薦'
  }
}

function formatTravel(candidate: EatFeedCandidate): string {
  const parts: string[] = []
  if (candidate.distance_meters != null) parts.push(`${candidate.distance_meters} m`)
  if (candidate.travel_minutes != null) parts.push(`${candidate.travel_minutes} 分鐘`)
  if (candidate.open_now != null) parts.push(candidate.open_now ? '營業中' : '已休息')
  return parts.join(' · ')
}

function inferMealTypeFromClock(): string {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 10) return 'breakfast'
  if (hour >= 10 && hour < 15) return 'lunch'
  if (hour >= 15 && hour < 18) return 'snack'
  return 'dinner'
}

function CandidateCard({
  candidate,
  emphasis,
  reason,
  expanded,
  onToggle,
}: {
  candidate: EatFeedCandidate
  emphasis: 'hero' | 'backup'
  reason: string
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <article className={`candidate-card-mobile ${emphasis === 'hero' ? 'candidate-card-mobile--hero' : ''}`}>
      <button className="candidate-card-mobile__button" type="button" onClick={onToggle}>
        <div className="candidate-card-mobile__topline">
          <span className="candidate-source">{sourceLabel(candidate.source_type)}</span>
          <span className="candidate-kcal">{candidate.kcal_low}-{candidate.kcal_high} kcal</span>
        </div>
        <strong className="candidate-title">{candidate.title}</strong>
        {candidate.store_name && candidate.store_name !== candidate.title ? (
          <span className="candidate-subtitle">{candidate.store_name}</span>
        ) : null}
        <p className="candidate-reason">{reason}</p>
      </button>
      {expanded ? (
        <div className="candidate-inline-detail">
          {candidate.reason_factors.slice(0, 3).map((item) => (
            <div key={item} className="detail-line">{item}</div>
          ))}
          {formatTravel(candidate) ? (
            <div className="detail-line detail-line--muted">{formatTravel(candidate)}</div>
          ) : null}
          {candidate.external_link ? (
            <a className="detail-link" href={candidate.external_link} target="_blank" rel="noreferrer">打開外部連結</a>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

function ExploreEntryRow({
  locationLabel,
  savedPlaces,
  favoriteStores,
  goldenOrders,
  onOpen,
}: {
  locationLabel: string
  savedPlaces: SavedPlace[]
  favoriteStores: FavoriteStore[]
  goldenOrders: GoldenOrder[]
  onOpen: () => void
}) {
  const bits: string[] = []
  if (locationLabel && locationLabel !== '不限地點') bits.push(locationLabel)
  if (savedPlaces.length) bits.push(`${savedPlaces.length} 個常用地點`)
  if (favoriteStores.length) bits.push(`${favoriteStores.length} 家常去店`)
  if (goldenOrders.length) bits.push(`${goldenOrders.length} 組穩定選項`)

  return (
    <section className="summary-card">
      <button className="summary-card__header" type="button" onClick={onOpen}>
        <div>
          <strong>更多選項與地點</strong>
          <span>{bits.length ? bits.join(' · ') : '補位置、管理常用店家，或查看更多候選。'}</span>
        </div>
        <span>開啟</span>
      </button>
    </section>
  )
}

function ExploreSheet({
  isOpen,
  onClose,
  locationState,
  locating,
  onClearLocation,
  onUseCurrentLocation,
  onApplyManualLocation,
  onSelectSavedPlace,
}: {
  isOpen: boolean
  onClose: () => void
  locationState: LocationState
  locating: boolean
  onClearLocation: () => void
  onUseCurrentLocation: () => void
  onApplyManualLocation: (query: string) => Promise<void>
  onSelectSavedPlace: (savedPlace: SavedPlace) => void
}) {
  const {
    eatFeed,
    savedPlaces,
    favoriteStores,
    goldenOrders,
    createSavedPlace,
    createFavoriteStore,
  } = useApp()
  const [manualQuery, setManualQuery] = useState(locationState.query ?? '')
  const [savedPlaceForm, setSavedPlaceForm] = useState({ label: '', address: '', is_default: false })
  const [favoriteStoreForm, setFavoriteStoreForm] = useState({ name: '', address: '', external_link: '' })
  const [savingPlace, setSavingPlace] = useState(false)
  const [savingStore, setSavingStore] = useState(false)

  useEffect(() => {
    setManualQuery(locationState.query ?? '')
  }, [locationState.query])

  async function handleSavePlace() {
    if (!savedPlaceForm.label || !savedPlaceForm.address) return
    setSavingPlace(true)
    try {
      await createSavedPlace(savedPlaceForm)
      setSavedPlaceForm({ label: '', address: '', is_default: false })
    } finally {
      setSavingPlace(false)
    }
  }

  async function handleSaveStore() {
    if (!favoriteStoreForm.name) return
    setSavingStore(true)
    try {
      await createFavoriteStore(favoriteStoreForm)
      setFavoriteStoreForm({ name: '', address: '', external_link: '' })
    } finally {
      setSavingStore(false)
    }
  }

  return (
    <FullScreenSheet isOpen={isOpen} onClose={onClose} title="更多選項">
      <div className="sheet-stack">
        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>地點上下文</h4>
            <span>{locationState.label || '目前沒有指定地點'}</span>
          </div>
          <div className="chip-row">
            <button className="chip-button" type="button" onClick={onUseCurrentLocation} disabled={locating}>
              {locating ? '定位中...' : '目前位置'}
            </button>
            {locationState.mode !== 'none' ? (
              <button className="chip-button" type="button" onClick={onClearLocation}>
                清除地點
              </button>
            ) : null}
          </div>
          <div className="inline-grid">
            <input
              className="input-field"
              placeholder="手動輸入地點，例如：信義區、南港軟體園區"
              value={manualQuery}
              onChange={(event) => setManualQuery(event.target.value)}
            />
            <button className="btn btn-primary" type="button" onClick={() => void onApplyManualLocation(manualQuery)} disabled={!manualQuery.trim()}>
              套用地點
            </button>
          </div>
          {savedPlaces.length ? (
            <div className="memory-pill-row memory-pill-row--spaced">
              {savedPlaces.map((place) => (
                <button key={place.id} className="memory-pill memory-pill--button" type="button" onClick={() => onSelectSavedPlace(place)}>
                  {place.label}
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>儲存常用地點</h4>
            <span>讓推薦更像你的日常路線</span>
          </div>
          <div className="inline-grid">
            <input
              className="input-field"
              placeholder="名稱，例如：公司、家裡、健身房"
              value={savedPlaceForm.label}
              onChange={(event) => setSavedPlaceForm((current) => ({ ...current, label: event.target.value }))}
            />
            <input
              className="input-field"
              placeholder="地址或區域"
              value={savedPlaceForm.address}
              onChange={(event) => setSavedPlaceForm((current) => ({ ...current, address: event.target.value }))}
            />
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={savedPlaceForm.is_default}
                onChange={(event) => setSavedPlaceForm((current) => ({ ...current, is_default: event.target.checked }))}
              />
              <span>設成預設地點</span>
            </label>
          </div>
          <button className="btn btn-primary" type="button" disabled={savingPlace || !savedPlaceForm.label || !savedPlaceForm.address} onClick={() => void handleSavePlace()}>
            {savingPlace ? '儲存中...' : '新增地點'}
          </button>
        </section>

        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>常去店家</h4>
            <span>{favoriteStores.length} 間</span>
          </div>
          {favoriteStores.length ? (
            <div className="sheet-list">
              {favoriteStores.map((store) => (
                <div key={store.id} className="explore-row">
                  <div>
                    <strong>{store.label || store.name}</strong>
                    <span>{store.address || `${store.usage_count} 次使用`}</span>
                  </div>
                  <span>{store.usage_count} 次</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-row empty-row--sheet">還沒有常去店家，先加一間之後推薦會更像你。</div>
          )}
          <div className="inline-grid inline-grid--tight">
            <input
              className="input-field"
              placeholder="店名"
              value={favoriteStoreForm.name}
              onChange={(event) => setFavoriteStoreForm((current) => ({ ...current, name: event.target.value }))}
            />
            <input
              className="input-field"
              placeholder="地址或備註"
              value={favoriteStoreForm.address}
              onChange={(event) => setFavoriteStoreForm((current) => ({ ...current, address: event.target.value }))}
            />
            <input
              className="input-field"
              placeholder="外部連結（選填）"
              value={favoriteStoreForm.external_link}
              onChange={(event) => setFavoriteStoreForm((current) => ({ ...current, external_link: event.target.value }))}
            />
          </div>
          <button className="btn btn-primary" type="button" disabled={savingStore || !favoriteStoreForm.name} onClick={() => void handleSaveStore()}>
            {savingStore ? '儲存中...' : '新增店家'}
          </button>
        </section>

        {goldenOrders.length ? (
          <section className="sheet-card">
            <div className="sheet-card__header">
              <h4>穩定選項</h4>
              <span>{goldenOrders.length} 筆</span>
            </div>
            <div className="sheet-list">
              {goldenOrders.map((item) => (
                <div key={item.id} className="explore-row">
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.store_name || '個人穩定選項'}</span>
                  </div>
                  <span>{item.kcal_low}-{item.kcal_high}</span>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {(eatFeed?.exploration_sections ?? []).map((section) => (
          <section key={section.key} className="sheet-card">
            <div className="sheet-card__header">
              <h4>{section.title}</h4>
              <span>{section.items.length} 筆</span>
            </div>
            <div className="sheet-list">
              {section.items.map((candidate) => (
                <div key={candidate.candidate_id} className="explore-row">
                  <div>
                    <strong>{candidate.title}</strong>
                    <span>{candidate.kcal_low}-{candidate.kcal_high} kcal</span>
                  </div>
                  <span>{sourceLabel(candidate.source_type)}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </FullScreenSheet>
  )
}

export default function EatPage() {
  const {
    auth,
    eatFeed,
    favoriteStores,
    goldenOrders,
    refreshEatFeed,
    savedPlaces,
    setMessage,
    summary,
  } = useApp()
  const [selectedChipId, setSelectedChipId] = useState<string | null>(null)
  const [expandedCandidateId, setExpandedCandidateId] = useState<string | null>(null)
  const [exploreOpen, setExploreOpen] = useState(false)
  const [locationState, setLocationState] = useState<LocationState | null>(null)
  const [locating, setLocating] = useState(false)

  const defaultSavedPlace = useMemo(
    () => savedPlaces.find((place) => place.is_default) ?? (savedPlaces.length === 1 ? savedPlaces[0] : null),
    [savedPlaces],
  )

  const activeLocationState = useMemo<LocationState>(() => {
    if (locationState) return locationState
    if (defaultSavedPlace) {
      return {
        mode: 'saved_place',
        saved_place_id: defaultSavedPlace.id,
        label: defaultSavedPlace.label,
      }
    }
    return { mode: 'none' }
  }, [defaultSavedPlace, locationState])

  const locationPayload = useMemo(
    () => ({
      location_mode: activeLocationState.mode,
      saved_place_id: activeLocationState.saved_place_id,
      lat: activeLocationState.lat,
      lng: activeLocationState.lng,
      query: activeLocationState.query,
      label: activeLocationState.label,
    }),
    [
      activeLocationState.label,
      activeLocationState.lat,
      activeLocationState.lng,
      activeLocationState.mode,
      activeLocationState.query,
      activeLocationState.saved_place_id,
    ],
  )

  useEffect(() => {
    if (auth.status !== 'ready') return
    void refreshEatFeed({
      meal_type: inferMealTypeFromClock(),
      location_mode: locationPayload.location_mode,
      saved_place_id: locationPayload.saved_place_id,
      lat: locationPayload.lat,
      lng: locationPayload.lng,
      query: locationPayload.query,
      selected_chip_id: selectedChipId,
      explore_mode: exploreOpen,
    })
  }, [auth.status, exploreOpen, locationPayload, refreshEatFeed, selectedChipId])

  const backupCandidates = useMemo(() => eatFeed?.backup_picks ?? [], [eatFeed])
  const locationLabel = locationPayload.label || eatFeed?.location_context_used || '不限地點'

  if (auth.status !== 'ready' || !summary) {
    return <div className="page-container"><div className="page-skeleton" /></div>
  }

  async function handleUseCurrentLocation() {
    if (!navigator.geolocation) {
      setMessage('這個裝置不支援定位。')
      return
    }

    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocationState({
          mode: 'geolocation',
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          label: '目前位置',
        })
        setLocating(false)
      },
      () => {
        setMessage('無法取得定位，先試試手動輸入地點。')
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 8000 },
    )
  }

  async function handleApplyManualLocation(query: string) {
    const value = query.trim()
    if (!value) return
    setLocationState({
      mode: 'manual',
      query: value,
      label: value,
    })
  }

  function handleSelectSavedPlace(savedPlace: SavedPlace) {
    setLocationState({
      mode: 'saved_place',
      saved_place_id: savedPlace.id,
      label: savedPlace.label,
    })
  }

  function clearLocation() {
    setLocationState({ mode: 'none' })
  }

  return (
    <div className="page-container" id="page-eat">
      <section className="hero-summary-row">
        <div>
          <span>今天還剩</span>
          <strong>{summary.remaining_kcal} kcal</strong>
          <span className="hero-summary-row__meta">{locationLabel}</span>
        </div>
      </section>

      {eatFeed?.top_pick ? (
        <CandidateCard
          candidate={eatFeed.top_pick}
          emphasis="hero"
          reason={eatFeed.hero_reason || eatFeed.top_pick.reason_factors[0] || '系統先替你挑了一個最穩的選項。'}
          expanded={expandedCandidateId === eatFeed.top_pick.candidate_id}
          onToggle={() => setExpandedCandidateId((current) => (current === eatFeed.top_pick!.candidate_id ? null : eatFeed.top_pick!.candidate_id))}
        />
      ) : (
        <section className="candidate-card-mobile candidate-card-mobile--hero">
          <p className="candidate-reason">這個情境下還沒有夠好的主推，先補一下位置或需求。</p>
        </section>
      )}

      {eatFeed?.smart_chips?.length ? (
        <div className="smart-chip-rail">
          {eatFeed.smart_chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              className={`smart-chip ${selectedChipId === chip.id ? 'smart-chip--active' : ''}`}
              onClick={() => setSelectedChipId((current) => (current === chip.id ? null : chip.id))}
            >
              {chip.label}
            </button>
          ))}
        </div>
      ) : null}

      {backupCandidates.length ? (
        <section className="backup-stack">
          {backupCandidates.map((candidate) => (
            <CandidateCard
              key={candidate.candidate_id}
              candidate={candidate}
              emphasis="backup"
              reason={candidate.reason_factors[0] || '備選'}
              expanded={expandedCandidateId === candidate.candidate_id}
              onToggle={() => setExpandedCandidateId((current) => (current === candidate.candidate_id ? null : candidate.candidate_id))}
            />
          ))}
        </section>
      ) : null}

      <ExploreEntryRow
        locationLabel={locationLabel}
        savedPlaces={savedPlaces}
        favoriteStores={favoriteStores}
        goldenOrders={goldenOrders}
        onOpen={() => setExploreOpen(true)}
      />

      <ExploreSheet
        isOpen={exploreOpen}
        onClose={() => setExploreOpen(false)}
        locationState={activeLocationState}
        locating={locating}
        onClearLocation={clearLocation}
        onUseCurrentLocation={() => void handleUseCurrentLocation()}
        onApplyManualLocation={handleApplyManualLocation}
        onSelectSavedPlace={handleSelectSavedPlace}
      />
    </div>
  )
}
