/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ValidationRunPlansAdmin } from './GxRunPlansAdmin'

const applicationSettingsMock = {
  apiBaseUrl: 'http://api.local',
  assistanceRequestMode: 'email' as 'email' | 'itsm',
  assistanceRequestEmailAddress: 'prototype@jaccloud.nl',
  assistanceRequestItsmSystem: '',
  assistanceRequestItsmEndpointUrl: '',
}

vi.mock('./GxSuiteScopePickerModal', () => ({
  GxSuiteScopePickerModal: ({ isOpen, onClose, onSelect }: any) => {
    if (!isOpen) {
      return null
    }

    return (
      <div>
        <button
          type="button"
          onClick={() => {
            onSelect({
              kind: 'data_object_version',
              dataObjectId: 'object-orders',
              dataObjectName: 'Orders',
              dataObjectVersionId: 'dov-777',
            })
          }}
        >
          Pick Orders scope
        </button>
        <button type="button" onClick={onClose}>Close scope picker</button>
      </div>
    )
  },
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => ({
    applicationSettings: applicationSettingsMock,
  }),
}))

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => ({
    currentWorkspaceId: 'retail-banking',
    user: {
      workspaceRoles: [{ workspaceId: 'retail-banking', role: 'admin' }],
    },
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))


const buildJsonResponse = (body: any, ok = true, status = ok ? 200 : 500) => ({
  ok,
  status,
  json: async () => body,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
})

describe('ValidationRunPlansAdmin', () => {
  let validationFailureResponse: { status: number; body: any } | null = null
  let supportTicketResponse: { status: number; body: any } | null = null

  beforeEach(() => {
    cleanup()
    validationFailureResponse = null
    supportTicketResponse = null
    applicationSettingsMock.apiBaseUrl = 'http://api.local'
    applicationSettingsMock.assistanceRequestMode = 'email'
    applicationSettingsMock.assistanceRequestEmailAddress = 'prototype@jaccloud.nl'
    applicationSettingsMock.assistanceRequestItsmSystem = ''
    applicationSettingsMock.assistanceRequestItsmEndpointUrl = ''
    let plans: any[] = []
    let versionCounter = 1
    let runCounter = 400

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = String(init?.method || 'GET').toUpperCase()

      if (url.includes('/gx/suites?dataObjectVersionId=dov-777')) {
        return buildJsonResponse([
          {
            suite_id: 'gx_suite_8f40b9ea',
            suite_version: 3,
            artifact_version: 'v1',
            assignment_scope: {
              data_object_id: 'object-orders',
              dataset_id: 'dataset-orders',
              data_product_id: 'odcs.dp.orders',
            },
            resolved_execution_scope: {
              data_object_version_ids: ['dov-777'],
            },
            compiled_from: {
              rule_ids: ['rule-1'],
              compiler_version: 'compiler-42',
              generated_at: '2026-04-10T07:00:00Z',
            },
            execution_contract: {
              engine_target: 'pyspark',
              execution_shape: 'join_pair',
            },
          },
        ])
      }

      if (url.includes('/run-plans?workspaceId=retail-banking') && method === 'GET') {
        return buildJsonResponse(plans)
      }

      if (url.endsWith('/run-plans') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        const planId = 'run-plan-1'
        const versionId = `run-plan-version-${versionCounter}`
        versionCounter += 1
        const created = {
          run_plan_id: planId,
          workspace_id: body.workspace_id,
          planning_mode: 'single_suite',
          status: 'draft',
          current_active_version_id: null,
          pending_version_id: versionId,
          pending_version_governance_state: 'draft',
          activated_by: null,
          activated_at: null,
          last_dispatched_run_id: null,
          transition_events: [
            {
              id: 'run-plan-1-event-1',
              run_plan_id: planId,
              run_plan_version_id: versionId,
              action: 'created',
              from_state: null,
              to_state: 'draft',
              actor_id: 'user-admin',
              correlation_id: 'corr-plan-1',
              effective_from: null,
              details: {
                planning_mode: 'single_suite',
                workspace_id: body.workspace_id,
              },
              occurred_at: '2026-04-10T08:00:00Z',
            },
          ],
          created_at: '2026-04-10T08:00:00Z',
          updated_at: '2026-04-10T08:00:00Z',
          versions: [
            {
              run_plan_version_id: versionId,
              run_plan_id: planId,
              governance_state: 'draft',
              gx_suite_selection: {
                selection_mode: 'single_suite',
                suite_id: body.suite_id,
                suite_version: body.suite_version,
              },
              suite_id: body.suite_id,
              suite_version: body.suite_version,
              schedule_definition: {
                scheduled_at: body.scheduled_at,
              },
              validation_status: 'not_requested',
              review_status: null,
              supersedes_version_id: null,
              created_at: '2026-04-10T08:00:00Z',
            },
          ],
        }
        plans = [created]
        return buildJsonResponse(created, true, 201)
      }

      if (url.endsWith('/versions') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        const versionId = `run-plan-version-${versionCounter}`
        versionCounter += 1
        const updated = {
          ...plans[0],
          updated_at: '2026-04-10T08:03:00Z',
          pending_version_id: versionId,
          pending_version_governance_state: 'draft',
          transition_events: [
            ...plans[0].transition_events,
            {
              id: 'run-plan-1-event-2',
              run_plan_id: 'run-plan-1',
              run_plan_version_id: versionId,
              action: 'version_created',
              from_state: null,
              to_state: 'draft',
              actor_id: 'user-admin',
              correlation_id: 'corr-plan-1',
              effective_from: null,
              details: {
                supersedes_version_id: plans[0].versions[plans[0].versions.length - 1].run_plan_version_id,
              },
              occurred_at: '2026-04-10T08:03:00Z',
            },
          ],
          versions: [
            ...plans[0].versions,
            {
              run_plan_version_id: versionId,
              run_plan_id: 'run-plan-1',
              governance_state: 'draft',
              gx_suite_selection: {
                selection_mode: body.planning_mode || 'single_suite',
                suite_id: body.suite_id,
                suite_version: body.suite_version,
              },
              suite_id: body.suite_id,
              suite_version: body.suite_version,
              schedule_definition: {
                scheduled_at: body.scheduled_at,
              },
              validation_status: 'not_requested',
              review_status: null,
              supersedes_version_id: plans[0].versions[plans[0].versions.length - 1].run_plan_version_id,
              created_at: '2026-04-10T08:03:00Z',
            },
          ],
        }
        plans = [updated]
        return buildJsonResponse(updated, true, 201)
      }

      if (url.includes('/governance-state') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        const versionId = url.split('/versions/')[1].split('/governance-state')[0]
        const targetState = body.target_state
        const updatedPlan = {
          ...plans[0],
          status: targetState,
          pending_version_id: versionId,
          pending_version_governance_state: targetState,
          transition_events: [
            ...plans[0].transition_events,
            {
              id: `run-plan-1-event-${plans[0].transition_events.length + 1}`,
              run_plan_id: 'run-plan-1',
              run_plan_version_id: versionId,
              action: 'transitioned',
              from_state: plans[0].versions.find((version: any) => version.run_plan_version_id === versionId)?.governance_state || 'draft',
              to_state: targetState,
              actor_id: 'user-admin',
              correlation_id: 'corr-plan-1',
              effective_from: null,
              details: {
                target_state: targetState,
              },
              occurred_at: '2026-04-10T08:04:00Z',
            },
          ],
          versions: plans[0].versions.map((version: any) => version.run_plan_version_id === versionId
            ? {
                ...version,
                governance_state: targetState,
                validation_status: targetState === 'pending_validation' ? 'pending' : targetState === 'validation_failed' ? 'failed' : 'passed',
                review_status: targetState === 'pending_review' ? 'pending' : targetState === 'approved_pending_activation' ? 'approved' : version.review_status,
              }
            : version),
        }
        plans = [updatedPlan]
        return buildJsonResponse(updatedPlan)
      }

      if (url.includes('/validate') && method === 'POST') {
        if (validationFailureResponse) {
          return buildJsonResponse(validationFailureResponse.body, false, validationFailureResponse.status)
        }

        const versionId = url.split('/versions/')[1].split('/validate')[0]
        const updatedPlan = {
          ...plans[0],
          status: 'pending_review',
          pending_version_id: versionId,
          pending_version_governance_state: 'pending_review',
          transition_events: [
            ...plans[0].transition_events,
            {
              id: `run-plan-1-event-${plans[0].transition_events.length + 1}`,
              run_plan_id: 'run-plan-1',
              run_plan_version_id: versionId,
              action: 'validated',
              from_state: plans[0].versions.find((version: any) => version.run_plan_version_id === versionId)?.governance_state || 'draft',
              to_state: 'pending_review',
              actor_id: 'user-admin',
              correlation_id: 'corr-plan-1',
              effective_from: null,
              details: {
                validation_status: 'passed',
              },
              occurred_at: '2026-04-10T08:04:00Z',
            },
          ],
          versions: plans[0].versions.map((version: any) => version.run_plan_version_id === versionId
            ? {
                ...version,
                governance_state: 'pending_review',
                validation_status: 'passed',
                review_status: 'pending',
              }
            : version),
        }
        plans = [updatedPlan]
        return buildJsonResponse({
          plan: updatedPlan,
          validation_status: 'passed',
          message: `Validation passed for run plan version '${versionId}'. Review is now pending.`,
          diagnostics: [],
        })
      }

      if (supportTicketResponse && url.includes('/system/v1/support/requests') && method === 'POST') {
        return buildJsonResponse(supportTicketResponse.body, supportTicketResponse.status < 400, supportTicketResponse.status)
      }

      if (url === applicationSettingsMock.assistanceRequestItsmEndpointUrl && method === 'POST') {
        return buildJsonResponse(supportTicketResponse?.body || { ticket_number: 'OST-1234' }, true, supportTicketResponse?.status || 201)
      }

      if (url.includes('/activate') && method === 'POST') {
        runCounter += 1
        const versionId = url.split('/versions/')[1].split('/activate')[0]
        const updatedPlan = {
          ...plans[0],
          status: 'active',
          current_active_version_id: versionId,
          pending_version_id: null,
          pending_version_governance_state: null,
          transition_events: [
            ...plans[0].transition_events,
            {
              id: `run-plan-1-event-${plans[0].transition_events.length + 1}`,
              run_plan_id: 'run-plan-1',
              run_plan_version_id: versionId,
              action: 'activated',
              from_state: 'approved_pending_activation',
              to_state: 'active',
              actor_id: 'user-admin',
              correlation_id: 'corr-plan-1',
              effective_from: null,
              details: {
                dispatched_run_id: `run-${runCounter}`,
              },
              occurred_at: '2026-04-10T08:05:00Z',
            },
          ],
          activated_by: 'user-admin',
          activated_at: '2026-04-10T08:05:00Z',
          last_dispatched_run_id: `run-${runCounter}`,
          updated_at: '2026-04-10T08:05:00Z',
          versions: plans[0].versions.map((version: any) => version.run_plan_version_id === versionId
            ? { ...version, governance_state: 'active' }
            : version),
        }
        plans = [updatedPlan]
        return buildJsonResponse({
          plan: updatedPlan,
          dispatch: {
            queue_message_id: `run-${runCounter}`,
            scheduled_at: updatedPlan.versions[updatedPlan.versions.length - 1].schedule_definition.scheduled_at,
            correlation_id: 'corr-plan-1',
          },
        }, true, 202)
      }

      return buildJsonResponse({ detail: 'Unexpected request' }, false, 404)
    })

    vi.stubGlobal('fetch', fetchMock)
  })

  it('creates, versions, and activates a validation run plan from the admin screen', async () => {
    const user = userEvent.setup()

    render(<ValidationRunPlansAdmin />)

    await user.click(screen.getByRole('button', { name: 'Browse data catalog' }))
    await user.click(await screen.findByRole('button', { name: 'Pick Orders scope' }))
    await user.click(screen.getByRole('button', { name: 'Load active validation suites' }))

    expect(await screen.findByText('Validation suite v3')).toBeTruthy()

    const scheduledAtInput = screen.getByLabelText('Scheduled time')
    await user.clear(scheduledAtInput)
    await user.type(scheduledAtInput, '2026-04-11T10:30')

    await user.click(screen.getByRole('button', { name: 'Create draft plan' }))
    expect(await screen.findByText('Draft run plan run-plan-1 created.')).toBeTruthy()
    expect(await screen.findByText('run-plan-1')).toBeTruthy()
    expect(await screen.findByText('Plan version 1')).toBeTruthy()
    expect(await screen.findByText('Transition history')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Create new branch version' }))
    expect(await screen.findByText(/Added draft version run-plan-version-2/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Validate version 2' }))
    expect(await screen.findByText("Validation passed for run plan version 'run-plan-version-2'. Review is now pending.")).toBeTruthy()

    await user.click(await screen.findByRole('button', { name: 'Approve version 2' }))
    expect(await screen.findByText('Updated run-plan-version-2 to approved_pending_activation.')).toBeTruthy()

    await user.click(await screen.findByRole('button', { name: 'Activate version 2' }))
    expect(await screen.findByText('Activated plan run-plan-1 as run run-401.')).toBeTruthy()
    expect(await screen.findByText(/Status:/)).toBeTruthy()

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const createPlanCall = fetchMock.mock.calls.find((call) => String(call[0]).endsWith('/run-plans') && call[1]?.method === 'POST')
    const createVersionCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/run-plans/run-plan-1/versions') && call[1]?.method === 'POST')

    expect(createPlanCall).toBeDefined()
    expect(createVersionCall).toBeDefined()

    expect(JSON.parse((createPlanCall?.[1] as RequestInit).body as string)).toMatchObject({
      workspace_id: 'retail-banking',
      suite_id: 'gx_suite_8f40b9ea',
      suite_version: 3,
      tag_ids: [],
    })
    expect(JSON.parse((createVersionCall?.[1] as RequestInit).body as string)).toMatchObject({
      planning_mode: 'single_suite',
      suite_id: 'gx_suite_8f40b9ea',
      suite_version: 3,
      tag_ids: [],
    })

    await waitFor(() => {
      expect(screen.getByText(/Status: /).textContent || '').toContain('active')
    })
  })

  it('creates and activates a grouped scope run plan from the admin screen', async () => {
    const user = userEvent.setup()

    render(<ValidationRunPlansAdmin />)

    await user.selectOptions(screen.getByLabelText('Plan mode'), 'grouped_scope')
    await user.click(screen.getByRole('button', { name: 'Browse data catalog' }))
    await user.click(await screen.findByRole('button', { name: 'Pick Orders scope' }))

    await user.click(screen.getByRole('button', { name: 'Create grouped draft plan' }))
    expect(await screen.findByText('Draft run plan run-plan-1 created.')).toBeTruthy()

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const createPlanCall = fetchMock.mock.calls.find((call) => String(call[0]).endsWith('/run-plans') && call[1]?.method === 'POST')
    expect(JSON.parse((createPlanCall?.[1] as RequestInit).body as string)).toMatchObject({
      planning_mode: 'grouped_scope',
      data_object_version_id: 'dov-777',
      tag_ids: [],
    })
  })

  it('offers operations assistance when validation fails', async () => {
    applicationSettingsMock.assistanceRequestMode = 'email'
    applicationSettingsMock.assistanceRequestEmailAddress = 'prototype@jaccloud.nl'
    validationFailureResponse = {
      status: 422,
      body: {
        detail: {
          message: "Validation failed for run plan version 'run-plan-version-2': GX run plan version contains an invalid execution contract snapshot required for validation",
        },
      },
    }

    supportTicketResponse = {
      status: 200,
      body: {
        reference_id: 'SUP-TESTEMAIL01',
        delivery_modes: ['email'],
        message: 'Sent email assistance request to prototype@jaccloud.nl. Reference ID: SUP-TESTEMAIL01',
        recipient_email: 'prototype@jaccloud.nl',
      },
    }

    const user = userEvent.setup()

    render(<ValidationRunPlansAdmin />)

    await user.click(screen.getByRole('button', { name: 'Browse data catalog' }))
    await user.click(await screen.findByRole('button', { name: 'Pick Orders scope' }))
    await user.click(screen.getByRole('button', { name: 'Load active validation suites' }))
    await user.click(screen.getByRole('button', { name: 'Create draft plan' }))
    await screen.findByText('Draft run plan run-plan-1 created.')

    await user.click(screen.getByRole('button', { name: 'Create new branch version' }))
    await screen.findByText(/Added draft version run-plan-version-2/)

    await user.click(screen.getByRole('button', { name: 'Validate version 2' }))

    expect(
      await screen.findByText(
        "Validation failed for run plan version 'run-plan-version-2': Validation run plan version contains an invalid execution contract snapshot required for validation"
      )
    ).toBeTruthy()

    const assistanceButton = await screen.findByRole('button', { name: 'Request assistance from operations team' })
    await user.click(assistanceButton)

    expect(await screen.findByText(/Sent email assistance request to prototype@jaccloud\.nl/)).toBeTruthy()
  })

  it('sends operations assistance to ITSM and reports the ticket number', async () => {
    applicationSettingsMock.assistanceRequestMode = 'itsm'
    applicationSettingsMock.assistanceRequestItsmSystem = 'HaloITSM'
    applicationSettingsMock.assistanceRequestItsmEndpointUrl = 'http://itsm.example.com/api/v1/tickets'

    validationFailureResponse = {
      status: 422,
      body: {
        detail: {
          message: "Validation failed for run plan version 'run-plan-version-2': GX run plan version contains an invalid execution contract snapshot required for validation",
        },
      },
    }

    supportTicketResponse = {
      status: 200,
      body: {
        reference_id: 'SUP-TEST123456',
        delivery_modes: ['itsm'],
        message: 'Assistance request sent to HaloITSM ticket HAL-4321.',
        ticket_number: 'HAL-4321',
        ticket_system: 'HaloITSM',
        ticket_url: 'http://itsm.example.com/tickets/HAL-4321',
      },
    }

    const user = userEvent.setup()

    render(<ValidationRunPlansAdmin />)

    await user.click(screen.getByRole('button', { name: 'Browse data catalog' }))
    await user.click(await screen.findByRole('button', { name: 'Pick Orders scope' }))
    await user.click(screen.getByRole('button', { name: 'Load active validation suites' }))
    await user.click(screen.getByRole('button', { name: 'Create draft plan' }))
    await screen.findByText('Draft run plan run-plan-1 created.')

    await user.click(screen.getByRole('button', { name: 'Create new branch version' }))
    await screen.findByText(/Added draft version run-plan-version-2/)

    await user.click(screen.getByRole('button', { name: 'Validate version 2' }))
    await screen.findByText(/Validation failed for run plan version 'run-plan-version-2'/)

    await user.click(screen.getByRole('button', { name: 'Request assistance from operations team' }))

    expect(await screen.findByText(/Assistance request sent to HaloITSM ticket HAL-4321\./)).toBeTruthy()
    expect(await screen.findByRole('button', { name: 'Open ticket' })).toBeTruthy()
    expect(screen.queryByText(/Validation failed for run plan version 'run-plan-version-2'/)).toBeNull()

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const supportCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/system/v1/support/requests'))
    expect(supportCall).toBeDefined()
    expect(JSON.parse((supportCall?.[1] as RequestInit).body as string)).toMatchObject({
      source: 'validation-run-plans-admin',
      title: 'Validation run plan assistance',
      message: expect.stringContaining('invalid execution contract snapshot required for validation'),
      workspace_id: 'retail-banking',
      diagnostics: [],
    })
  })
})