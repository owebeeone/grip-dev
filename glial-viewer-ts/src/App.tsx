import { useEffect, useMemo, useRef, useState } from 'react'
import { useGrip } from '@owebeeone/grip-react'
import { HttpGlialClient } from '@owebeeone/glial-net'
import {
  hydrateViewerSharedSession,
  selectViewerSession,
  VIEWER_CONTEXTS,
  VIEWER_ERROR,
  VIEWER_LEASES,
  VIEWER_SELECTED_SESSION,
  VIEWER_SESSIONS,
  VIEWER_TAPS,
  loadViewerSession,
  refreshViewerSessions,
  requestViewerLease,
  setViewerError,
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

  const baseUrl =
    (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_GLIAL_BASE_URL ??
    window.location.origin
  const client = useMemo(
    () => props.client ?? new HttpGlialClient({ baseUrl }),
    [baseUrl, props.client],
  )
  const userId =
    props.userId ??
    ((import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_GLIAL_USER_ID ??
      'demo-user')
  const replicaIdRef = useRef(createReplicaId())

  useEffect(() => {
    void refreshViewerSessions(client, userId).catch((error) => {
      setViewerError(formatError(error))
    })
  }, [client, userId])

  useEffect(() => {
    if (!selectedSession && sessions.length > 0) {
      selectViewerSession(sessions[0].session_id)
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
    void loadViewerSession(client, userId, selectedSession).catch((error) => {
      setViewerError(formatError(error))
    })
    const subscription = client.subscribeSharedSession(
      userId,
      selectedSession,
      {
        onSnapshot: hydrateViewerSharedSession,
        onError: (error) => {
          setViewerError(formatError(error))
        },
      },
      replicaIdRef.current,
    )
    return () => subscription.close()
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
              <button onClick={() => selectViewerSession(session.session_id)}>
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
                    void requestViewerLease(
                      client,
                      userId,
                      selectedSession,
                      tap.tap_id,
                      replicaIdRef.current,
                      50,
                    )
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

function createReplicaId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `viewer-ui-${crypto.randomUUID()}`
  }
  return `viewer-ui-${Math.random().toString(36).slice(2, 10)}`
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
