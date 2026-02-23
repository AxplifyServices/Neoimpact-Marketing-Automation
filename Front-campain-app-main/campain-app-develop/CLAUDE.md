# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CampaignHub is a React-based SPA for marketing campaign management and automation. The application manages campaigns, models/templates, target audiences, contact center operations (CRC), and analytics dashboards.

**Stack:** React 19 + TypeScript + Vite + TailwindCSS + React Router + TanStack React Query

## Common Commands

```bash
# Development
npm run dev          # Start dev server with HMR (http://localhost:5173)

# Build & Preview
npm run build        # TypeScript compilation + Vite build → dist/
npm run preview      # Preview production build locally

# Code Quality
npm run lint         # Run ESLint
```

## Architecture Overview

### Application Structure

This is a component-based SPA with clear separation of concerns:

- **Pages** (`src/pages/`) - Route-level components for each main feature
- **Components** (`src/components/`) - Reusable UI components
  - `ui/` - Radix UI wrapper components (Button, Dialog, Select, etc.)
  - `custom/` - Application-specific components (CampaignGraph, WorkflowPreview, etc.)
  - `data-table/` - TanStack Table components for data grids
- **API Layer** (`src/lib/api/`) - Centralized API client and endpoint definitions
- **Types** (`src/types/`) - TypeScript type definitions
- **Hooks** (`src/hooks/`) - Custom React hooks
- **Context** (`src/context/`) - React Context providers (LoadingContext)

### Entry Point Flow

1. `index.html` → loads `src/main.tsx`
2. `main.tsx` → sets up QueryProvider + LoadingProvider → renders `App.tsx`
3. `App.tsx` → BrowserRouter with Sidebar + Routes

### API Client Architecture

The application uses a **custom API client pattern** that abstracts all backend communication:

**Key Files:**
- `src/lib/api/api-client.ts` - Core `ApiClient` class with request handling
- `src/lib/api/ApiRequest.ts` - `ApiRequest` interface and `ApiError` class
- `src/lib/api/definitions/*.api.ts` - API endpoint definitions (campaigns, modeles, cibles, dashboard, etc.)
- `src/lib/api/hooks/` - React Query wrapper hooks

**Data Flow:**
```
Page Component
    ↓
useApiQuery/useApiMutation hooks
    ↓
TanStack React Query (caching & state management)
    ↓
ApiClient instance (from useApiClient)
    ↓
Backend API (https://axplify-services.com/marketing_automation/api)
```

**Important Pattern:** All API calls are defined in `src/lib/api/definitions/*.api.ts` files as objects implementing the `ApiRequest` interface. Components never make direct fetch calls - they use the `useApiQuery` or `useApiMutation` hooks with these definitions.

Example:
```typescript
// In definitions/campaigns.api.ts
export const getCampaigns: ApiRequest = {
  url: '/campaigns',
  method: 'GET',
  useLoader: true
}

// In a component
const { data } = useApiQuery({ request: getCampaigns })
```

**Mutation Hooks — Two Patterns:**
```typescript
// Pattern 1: Dynamic request (variables determine the request)
useApiMutation<TData, TVariables>({ request: (vars) => ApiRequest })

// Pattern 2: Static pre-configured request
useApiMutationWithRequest<TData, TVariables>(request, options)
```

**React Query Defaults** (`src/lib/api/query-client.tsx`): All caching is disabled by default — `staleTime: 0`, `gcTime: 0`, `retry: false`, `refetchOnWindowFocus/Mount/Reconnect: false`. Data is always fetched fresh. Override per-query only when needed (e.g., `staleTime: 5 * 60 * 1000` for stable metadata).

**Authentication:** `ApiClient` uses a token getter callback pattern. Call `apiClient.setTokenGetter(() => token)` to register a token provider; the client calls it before each request and sets `Authorization: Bearer <token>`. No auth page exists in this app — token setup must happen externally.

### State Management

- **Server State:** TanStack React Query (automatic caching, refetching, synchronization)
- **Global UI State:** React Context (LoadingContext for global loading indicator)
- **Local State:** React hooks (useState, useReducer)

### Path Aliases

The project uses `@/` as an alias for `src/`:
```typescript
import { Button } from '@/components/ui/button'
import { useApiClient } from '@/lib/api/hooks/use-api-client'
```

## Key Features & Domains

The application manages 5 main domains:

1. **Campaigns** (`/campagnes`) - Create, pause, activate, cancel campaigns
2. **Models** (`/modeles`) - Campaign templates with workflow graphs
3. **Targets** (`/cibles`) - Target audience management (DB/FILE sources)
4. **CRC** (`/crc`) - Contact Response Center for queue management
5. **Dashboard** (`/dashboard`) - Analytics, KPIs, success rates, conversion funnels

## Environment Configuration

Environment variables are loaded from `.env.development` (dev) or `.env.production` (prod):

```env
VITE_API_BASE_URL=https://axplify-services.com/marketing_automation/api
VITE_AUTH_URL=https://axplify-services.com/marketing_automation/api
VITE_API_TIMEOUT=30000
VITE_ENABLE_MOCK_DATA=false  # Enable mock data for offline development
```

Access via `src/config/env.ts`:
```typescript
import { API_BASE_URL, ENABLE_MOCK_DATA } from '@/config/env'
```

## Important Patterns

### API Endpoint Definitions

All API endpoints are defined in `src/lib/api/definitions/` as `ApiRequest` objects:
- `campaigns.api.ts` - Campaign CRUD operations
- `modeles.api.ts` - Model/template operations
- `cibles.api.ts` - Target audience operations
- `dashboard.api.ts` - Dashboard & analytics
- `queues.api.ts` - Queue processing operations
- `batch.api.ts` - Batch operations
- `data.api.ts` - Data endpoints
- `meta.api.ts` - Metadata endpoints

### Component Composition

UI components follow a composition pattern using Radix UI primitives:
- `src/components/ui/` contains accessible Radix UI wrappers
- `src/components/custom/` builds complex features using ui components
- All components are TypeScript with strict typing

### Data Tables

The application uses TanStack Table for data grids with custom components in `src/components/data-table/`:
- Column sorting, filtering, pagination
- Bulk actions, faceted filters
- View options for column visibility

### Workflow Visualization

Campaign models are visualized using ReactFlow:
- `src/components/custom/WorkflowPreview.tsx` - Workflow graph visualization and editor
- Uses ELK.js for automatic graph layout

### Workflow Editor State (`src/hooks/useBlockManagement.ts`)

The workflow block editor has complex state with undo/redo:
- Maintains `history`/`future` stacks (max 100 each) for full undo/redo support
- Blocks form a DAG — each block can have multiple parents, each with separate condition lists
- Condition types: `days_since_last`, `flag_resultat`, `counter`, `client_filter`, `campaign_field`
- Objective blocks support AND/OR operators with numeric ranges or categorical values

### Form Handling

No form library is used. All forms use vanilla React:
- `useState` with object spreading for field updates
- Manual `validateForm()` functions returning `Record<string, string>` error maps
- File uploads handled by `src/components/custom/FileUpload.tsx` using the `xlsx` library for CSV/XLSX preview (first 5 rows shown before upload)

## Styling

- **TailwindCSS v4** with utility-first approach
- **Dark mode** support via class-based toggle
- **CSS Variables** for theming (defined in `src/index.css`)
- **Responsive design** with mobile-first breakpoints
- Use `cn()` utility from `@/lib/utils` for conditional classnames

## Docker Deployment

The application is containerized with a two-stage Docker build:
1. **Build stage:** Node.js 22-alpine → npm install + build
2. **Runtime stage:** Nginx-alpine → serves static files from `/usr/share/nginx/html`

Custom nginx configuration handles SPA routing (all routes → index.html).

## Testing & Debugging

- **No test framework is configured.** There are no test files or testing dependencies.
- **React Query DevTools** available in development mode
- **Source maps** enabled for debugging
- **Mock data** available via `VITE_ENABLE_MOCK_DATA=true` (see `src/lib/api/mock/`). Note: defaults to `true` in `src/config/env.ts` — set to `false` in `.env.development` to use the real API.

## Important Notes

- Never make direct fetch/axios calls - always use the API client pattern
- All API definitions should be in `src/lib/api/definitions/`
- Use the `useApiQuery` and `useApiMutation` hooks for data fetching
- File uploads use `FormData` and are handled by `ApiClient`
- The `ApiClient` automatically adds Bearer token authentication
- Global loading state is managed via `LoadingContext` and the `useLoader` flag in API requests
- `cn()` in `src/lib/utils.ts` wraps `clsx` + `tailwind-merge` — use it for all conditional classnames
- `src/lib/utils.ts` also contains `parseObjectif()`/`formatObjectifSummary()` for objective condition parsing — check these before writing custom objective logic
- TypeScript strict mode is **off** (`"strict": false` in `tsconfig.app.json`) — type coverage is partial throughout the codebase
