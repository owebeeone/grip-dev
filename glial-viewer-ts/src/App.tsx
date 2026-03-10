import { useEffect, useState } from 'react'
import { useGrip } from '@owebeeone/grip-react'
import { HttpGlialClient } from '@owebeeone/glial-net'
import {
  VIEWER_CONTEXTS,
  VIEWER_ERROR,
  VIEWER_LEASES,
  VIEWER_SELECTED_SESSION,
  VIEWER_SESSIONS,
  VIEWER_TAPS,
  loadViewerSession,
  refreshViewerSessions,
  requestViewerLease,
  updateViewerSharedValue,
} from './viewer_runtime'

export interface ViewerAppProps {
  client?: HttpGlialClient
  userId?: string
}

export default function App(props: ViewerAppProps) {
  const sessions = useGrip(VIEWER_SESSIONS) ?? []
  const selectedSession = useGrip(VIEWER_SELECTED_SESSION)
  const contexts = useGrip(VIEWER_CONTEXTS) ?? []
  const taps = useGrip(VIEWER_TAPS) ?? []
  const leases = useGrip(VIEWER_LEASES) ?? {}
  const error = useGrip(VIEWER_ERROR)
  const [selectedContext, setSelectedContext] = useState('')
  const [gripId, setGripId] = useState('')
  const [jsonValue, setJsonValue] = useState('0')

  const client = props.client ?? new HttpGlialClient({ baseUrl: (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_GLIAL_BASE_URL ?? window.location.origin })
  const userId = props.userId ?? ((import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_GLIAL_USER_ID ?? 'demo-user')

  useEffect(() => {
    void refreshViewerSessions(client, userId)
  }, [client, userId])

  useEffect(() => {
    if (!selectedSession && sessions.length > 0) {
      void loadViewerSession(client, userId, sessions[0].session_id)
    }
  }, [client, selectedSession, sessions, userId])

  useEffect(() => {
    if (!selectedContext && contexts.length > 0) {
      setSelectedContext(contexts[0].path)
    }
  }, [contexts, selectedContext])

  useEffect(() => {
    if (!selectedSession) {
      return
    }
    const timer = window.setInterval(() => {
      void loadViewerSession(client, userId, selectedSession)
    }, 750)
    return () => window.clearInterval(timer)
  }, [client, selectedSession, userId])

  const activeContext = contexts.find((context) => context.path === selectedContext) ?? null

  return (
    <main style={{ display: 'grid', gap: 16, padding: 24, fontFamily: 'monospace' }}>
      <h1>Glial Viewer</h1>
      {error ? <div role="alert">{error}</div> : null}
      <section>
        <h2>Sessions</h2>
        <button onClick={() => void refreshViewerSessions(client, userId)}>Refresh</button>
        <ul>
          {sessions.map((session) => (
            <li key={session.session_id}>
              <button onClick={() => void loadViewerSession(client, userId, session.session_id)}>
                {session.title ?? session.session_id}
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Selected Session</h2>
        <div>{selectedSession ?? 'none'}</div>
      </section>
      <section>
        <h2>Contexts</h2>
        <ul>
          {contexts.map((context) => (
            <li key={context.path}>
              <button onClick={() => setSelectedContext(context.path)}>{context.path}</button>
              <span> ({context.drips.length} drips)</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Drips</h2>
        {activeContext ? (
          <ul>
            {activeContext.drips.map((drip) => (
              <li key={drip.grip_id}>
                <strong>{drip.grip_id}</strong>
                <pre>{JSON.stringify(drip.value, null, 2)}</pre>
              </li>
            ))}
          </ul>
        ) : (
          <div>No context selected</div>
        )}
      </section>
      <section>
        <h2>Taps</h2>
        <ul>
          {taps.map((tap) => (
            <li key={tap.tap_id}>
              <div>{tap.tap_id}</div>
              <div>{tap.tap_type} @ {tap.home_path}</div>
              <button
                onClick={() => {
                  if (selectedSession) {
                    void requestViewerLease(client, userId, selectedSession, tap.tap_id, 'viewer-ui', 50)
                  }
                }}
              >
                Request Primary
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Leases</h2>
        <pre>{JSON.stringify(leases, null, 2)}</pre>
      </section>
      <section>
        <h2>Set Shared Value</h2>
        <input aria-label="context-path" value={selectedContext} onChange={(event) => setSelectedContext(event.target.value)} placeholder="context path" />
        <input aria-label="grip-id" value={gripId} onChange={(event) => setGripId(event.target.value)} placeholder="grip id" />
        <input aria-label="json-value" value={jsonValue} onChange={(event) => setJsonValue(event.target.value)} placeholder="json value" />
        <button
          onClick={() => {
            if (!selectedSession || !selectedContext || !gripId) {
              return
            }
            void updateViewerSharedValue(client, userId, selectedSession, selectedContext, gripId, JSON.parse(jsonValue))
          }}
        >
          Send Update
        </button>
      </section>
    </main>
  )
}
