import {
  type Grip,
  GripOf,
  GripRegistry,
  Grok,
  createMultiAtomValueTap,
  applySharedProjectionSnapshot,
} from '@owebeeone/grip-core'
import type { SharedSessionLoadResponse, HttpGlialClient } from '@owebeeone/glial-net'

export interface ViewerSessionSummary {
  session_id: string
  title?: string
  last_modified_ms: number
}

export interface ViewerContextSummary {
  path: string
  drips: Array<{
    grip_id: string
    value: unknown
  }>
}

export interface ViewerTapSummary {
  tap_id: string
  tap_type: string
  home_path: string
  mode?: string
  role?: string
  provides: string[]
}

const viewerRegistry = new GripRegistry()
const gripOf = GripOf(viewerRegistry)

export const VIEWER_SESSIONS = gripOf<ViewerSessionSummary[]>('ViewerSessions', [])
export const VIEWER_SELECTED_SESSION = gripOf<string | null>('ViewerSelectedSession', null)
export const VIEWER_CONTEXTS = gripOf<ViewerContextSummary[]>('ViewerContexts', [])
export const VIEWER_TAPS = gripOf<ViewerTapSummary[]>('ViewerTaps', [])
export const VIEWER_LEASES = gripOf<Record<string, Record<string, unknown>>>('ViewerLeases', {})
export const VIEWER_ERROR = gripOf<string | null>('ViewerError', null)

export const viewerGrok = new Grok(viewerRegistry)
const viewerStateTap = createMultiAtomValueTap<any>({
  gripMap: new Map<any, any>([
    [VIEWER_SESSIONS, []],
    [VIEWER_SELECTED_SESSION, null],
    [VIEWER_CONTEXTS, []],
    [VIEWER_TAPS, []],
    [VIEWER_LEASES, {}],
    [VIEWER_ERROR, null],
  ]),
})
viewerGrok.registerTap(viewerStateTap)

let rawSharedGrok = new Grok(new GripRegistry())

function setViewerState<T>(grip: Grip<T>, value: T): void {
  viewerStateTap.set(grip, value)
}

export function setViewerError(message: string | null): void {
  setViewerState(VIEWER_ERROR, message)
}

export function selectViewerSession(sessionId: string | null): void {
  setViewerState(VIEWER_SELECTED_SESSION, sessionId)
}

export function getRawSharedGrok(): Grok {
  return rawSharedGrok
}

export function resetViewerRuntime(): void {
  rawSharedGrok = new Grok(new GripRegistry())
  setViewerState(VIEWER_SESSIONS, [])
  setViewerState(VIEWER_SELECTED_SESSION, null)
  setViewerState(VIEWER_CONTEXTS, [])
  setViewerState(VIEWER_TAPS, [])
  setViewerState(VIEWER_LEASES, {})
  setViewerState(VIEWER_ERROR, null)
}

export async function refreshViewerSessions(client: HttpGlialClient, userId: string): Promise<void> {
  const sessions = await client.listRemoteSessions(userId)
  setViewerState(VIEWER_SESSIONS, sessions)
}

export async function loadViewerSession(
  client: HttpGlialClient,
  userId: string,
  sessionId: string,
): Promise<void> {
  selectViewerSession(sessionId)
  const shared = await client.loadSharedSession(userId, sessionId)
  hydrateViewerSharedSession(shared)
}

export function hydrateViewerSharedSession(shared: SharedSessionLoadResponse): void {
  rawSharedGrok = new Grok(new GripRegistry())
  applySharedProjectionSnapshot(rawSharedGrok, shared.snapshot as never)

  const contexts = Object.values(shared.snapshot.contexts ?? {}).map((context) => ({
    path: String((context as Record<string, unknown>).path ?? ''),
    drips: Object.values(
      (((context as Record<string, unknown>).drips ?? {}) as Record<string, Record<string, unknown>>),
    ).map((drip) => ({
      grip_id: String(drip.grip_id ?? ''),
      value: drip.value,
    })),
  }))
  const taps = Object.values((shared.snapshot.taps ?? {}) as Record<string, Record<string, unknown>>).map((tap) => ({
    tap_id: String(tap.tap_id ?? ''),
    tap_type: String(tap.tap_type ?? ''),
    home_path: String(tap.home_path ?? ''),
    mode: typeof tap.mode === 'string' ? tap.mode : undefined,
    role: typeof tap.role === 'string' ? tap.role : undefined,
    provides: Array.isArray(tap.provides) ? tap.provides.map((value) => String(value)) : [],
  }))

  setViewerState(VIEWER_SELECTED_SESSION, shared.session_id)
  setViewerState(VIEWER_CONTEXTS, contexts)
  setViewerState(VIEWER_TAPS, taps)
  setViewerState(VIEWER_LEASES, shared.leases ?? {})
  setViewerState(VIEWER_ERROR, null)
}

export async function requestViewerLease(
  client: HttpGlialClient,
  userId: string,
  sessionId: string,
  tapId: string,
  replicaId: string,
  priority: number,
): Promise<void> {
  await client.requestTapLease(userId, sessionId, tapId, replicaId, priority)
  const shared = await client.loadSharedSession(userId, sessionId)
  hydrateViewerSharedSession(shared)
}

export async function updateViewerSharedValue(
  client: HttpGlialClient,
  userId: string,
  sessionId: string,
  path: string,
  gripId: string,
  value: unknown,
): Promise<void> {
  const updated = await client.updateSharedValue(userId, sessionId, {
    path,
    grip_id: gripId,
    value,
  })
  hydrateViewerSharedSession(updated)
}
