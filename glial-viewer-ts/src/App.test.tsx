import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GripProvider } from '@owebeeone/grip-react'
import App from './App'
import { resetViewerRuntime, viewerGrok } from './viewer_runtime'
import { HttpGlialClient } from '@owebeeone/glial-net'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('Glial viewer UI', () => {
  afterEach(() => {
    cleanup()
    resetViewerRuntime()
  })

  it('renders shared sessions, negotiates primary, and sends shared value updates', async () => {
    let countValue = 5
    let leaseRecord: Record<string, unknown> = {}

    function sharedSessionResponse() {
      return {
        session_id: 'shared-a',
        title: 'Shared A',
        snapshot: {
          session_id: 'shared-a',
          contexts: {
            'main-home': {
              path: 'main-home',
              name: 'main-home',
              children: [],
              drips: {
                'app:Count': {
                  grip_id: 'app:Count',
                  name: 'Count',
                  value: countValue,
                  taps: [
                    {
                      tap_id: 'tap-count',
                      tap_type: 'AtomValueTap',
                      mode: 'replicated',
                      role: 'primary',
                      provides: ['app:Count'],
                    },
                  ],
                },
              },
            },
          },
          taps: {
            'tap-count': {
              tap_id: 'tap-count',
              tap_type: 'AtomValueTap',
              home_path: 'main-home',
              mode: 'replicated',
              role: 'primary',
              provides: ['app:Count'],
            },
          },
        },
        leases: leaseRecord,
        last_modified_ms: 1,
      }
    }

    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/remote-sessions?user_id=demo-user') && method === 'GET') {
        return jsonResponse([
          { session_id: 'shared-a', title: 'Shared A', last_modified_ms: 1 },
        ])
      }
      if (url.endsWith('/shared-sessions/shared-a?user_id=demo-user') && method === 'GET') {
        return jsonResponse(sharedSessionResponse())
      }
      if (url.endsWith('/shared-sessions/shared-a/leases/tap-count?user_id=demo-user') && method === 'POST') {
        leaseRecord = {
          'tap-count': {
            tap_id: 'tap-count',
            primary_replica_id: 'viewer-ui',
            priority: 50,
            granted_ms: 1,
          },
        }
        return jsonResponse({
          tap_id: 'tap-count',
          primary_replica_id: 'viewer-ui',
          priority: 50,
          granted_ms: 1,
          granted: true,
        })
      }
      if (url.endsWith('/shared-sessions/shared-a/values?user_id=demo-user') && method === 'POST') {
        const body = JSON.parse(String(init?.body ?? '{}')) as { value?: unknown }
        countValue = Number(body.value)
        return jsonResponse(sharedSessionResponse())
      }
      throw new Error(`Unhandled fetch: ${method} ${url}`)
    })

    const client = new HttpGlialClient({ baseUrl: 'http://glial.test', fetchImpl: fetchMock })
    render(
      <GripProvider grok={viewerGrok} context={viewerGrok.mainPresentationContext}>
        <App client={client} userId="demo-user" />
      </GripProvider>,
    )

    await waitFor(() => expect(screen.getByText('Shared A')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('tap-count')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('app:Count')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('5')).toBeTruthy())

    fireEvent.click(screen.getByText('Request Primary'))
    await waitFor(() => expect(screen.getByText(/viewer-ui/)).toBeTruthy())

    fireEvent.change(screen.getByLabelText('grip-id'), { target: { value: 'app:Count' } })
    fireEvent.change(screen.getByLabelText('json-value'), { target: { value: '8' } })
    fireEvent.click(screen.getByText('Send Update'))

    await waitFor(() => expect(screen.getByText('8')).toBeTruthy())
  })

  it('refreshes the selected shared session and updates rendered drip values', async () => {
    let loadCount = 0

    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/remote-sessions?user_id=demo-user') && method === 'GET') {
        return jsonResponse([
          { session_id: 'shared-a', title: 'Shared A', last_modified_ms: 1 },
        ])
      }
      if (url.endsWith('/shared-sessions/shared-a?user_id=demo-user') && method === 'GET') {
        loadCount += 1
        return jsonResponse({
          session_id: 'shared-a',
          title: 'Shared A',
          snapshot: {
            session_id: 'shared-a',
            contexts: {
              'main-home': {
                path: 'main-home',
                name: 'main-home',
                children: [],
                drips: {
                  'app:Count': {
                    grip_id: 'app:Count',
                    name: 'Count',
                    value: loadCount > 1 ? 8 : 5,
                    taps: [],
                  },
                },
              },
            },
            taps: {},
          },
          leases: {},
          last_modified_ms: loadCount,
        })
      }
      throw new Error(`Unhandled fetch: ${method} ${url}`)
    })

    const client = new HttpGlialClient({ baseUrl: 'http://glial.test', fetchImpl: fetchMock })
    render(
      <GripProvider grok={viewerGrok} context={viewerGrok.mainPresentationContext}>
        <App client={client} userId="demo-user" />
      </GripProvider>,
    )

    await waitFor(() => expect(screen.getByText('5')).toBeTruthy())
    await new Promise((resolve) => setTimeout(resolve, 850))
    await waitFor(() => expect(screen.getByText('8')).toBeTruthy())
  }, 7000)
})
