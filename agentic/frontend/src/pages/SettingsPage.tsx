import { useState } from 'react'

import { completeOnboarding, updatePreferences } from '../api'
import type { AuthHeaders, HomePayload, PrimaryGoal } from '../types'
import HomeScaffold from '../components/HomeScaffold'

type SettingsPageProps = {
  payload: HomePayload
  authHeaders: AuthHeaders
}

export default function SettingsPage({ payload, authHeaders }: SettingsPageProps) {
  const [goal, setGoal] = useState<PrimaryGoal>(payload.state.goal_state.primary_goal ?? 'consistency')
  const [constraintText, setConstraintText] = useState(payload.state.goal_state.constraints.join(', '))
  const [status, setStatus] = useState('')

  async function handleSavePreferences() {
    const constraints = constraintText
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean)
    await updatePreferences({ constraints }, authHeaders)
    setStatus('preferences saved via structured mutation')
  }

  async function handleCompleteOnboarding() {
    const constraints = constraintText
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean)
    await completeOnboarding(goal, constraints, authHeaders)
    setStatus('onboarding completed via structured mutation')
  }

  return (
    <HomeScaffold payload={payload}>
      <article className="panel settings-panel">
        <h2>Settings / Onboarding</h2>
        <label>
          Primary goal
          <select value={goal} onChange={(event) => setGoal(event.target.value as PrimaryGoal)}>
            <option value="weight_loss">weight_loss</option>
            <option value="maintenance">maintenance</option>
            <option value="muscle_gain">muscle_gain</option>
            <option value="consistency">consistency</option>
            <option value="event_preparation">event_preparation</option>
            <option value="symptom_management">symptom_management</option>
          </select>
        </label>
        <label>
          Constraints
          <input value={constraintText} onChange={(event) => setConstraintText(event.target.value)} />
        </label>
        <div className="button-row">
          <button onClick={() => void handleSavePreferences()}>Save Preferences</button>
          <button className="secondary" onClick={() => void handleCompleteOnboarding()}>
            Complete Onboarding
          </button>
        </div>
        {status ? <p className="status">{status}</p> : null}
      </article>
    </HomeScaffold>
  )
}
