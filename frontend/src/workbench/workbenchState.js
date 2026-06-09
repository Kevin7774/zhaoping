export const INITIAL_WORKBENCH_STATE = {
  chatMessages: [
    {
      id: 'system-ready',
      role: 'assistant',
      text: '输入招聘、搜索、候选人或评估目标后，我会先推荐能力，确认后再执行。',
      createdAt: new Date().toISOString(),
    },
  ],
  suggestedCapabilities: [],
  activeRuns: [],
  artifacts: [],
  selectedWorkspace: 'workflow',
  apiErrors: [],
  pendingConfirmation: null,
}

function createId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function createArtifact(type, title, data, sourceCapabilityId) {
  return {
    id: createId(type),
    type,
    title,
    data,
    sourceCapabilityId,
    createdAt: new Date().toISOString(),
  }
}

export function createRun(capability, status = 'running') {
  return {
    id: createId('run'),
    capabilityId: capability.id,
    title: capability.title,
    status,
    startedAt: new Date().toISOString(),
  }
}

export function workbenchReducer(state, action) {
  switch (action.type) {
    case 'set_workspace':
      return {
        ...state,
        selectedWorkspace: action.workspace,
      }
    case 'add_user_message':
      return {
        ...state,
        chatMessages: [
          ...state.chatMessages,
          {
            id: createId('msg-user'),
            role: 'user',
            text: action.text,
            createdAt: new Date().toISOString(),
          },
        ],
      }
    case 'add_assistant_message':
      return {
        ...state,
        chatMessages: [
          ...state.chatMessages,
          {
            id: createId('msg-assistant'),
            role: 'assistant',
            text: action.text,
            capabilityId: action.capabilityId || null,
            createdAt: new Date().toISOString(),
          },
        ],
      }
    case 'set_suggestions':
      return {
        ...state,
        suggestedCapabilities: action.capabilities,
      }
    case 'set_pending_confirmation':
      return {
        ...state,
        pendingConfirmation: action.pendingConfirmation,
      }
    case 'clear_pending_confirmation':
      return {
        ...state,
        pendingConfirmation: null,
      }
    case 'start_run':
      return {
        ...state,
        activeRuns: [action.run, ...state.activeRuns],
      }
    case 'finish_run':
      return {
        ...state,
        activeRuns: state.activeRuns.map((run) =>
          run.id === action.runId
            ? {
                ...run,
                status: action.status,
                finishedAt: new Date().toISOString(),
              }
            : run,
        ),
      }
    case 'add_artifacts':
      return {
        ...state,
        artifacts: [...action.artifacts, ...state.artifacts],
      }
    case 'add_error':
      return {
        ...state,
        apiErrors: [
          {
            id: createId('api-error'),
            message: action.message,
            capabilityId: action.capabilityId || null,
            createdAt: new Date().toISOString(),
          },
          ...state.apiErrors,
        ],
      }
    case 'clear_errors':
      return {
        ...state,
        apiErrors: [],
      }
    default:
      return state
  }
}
