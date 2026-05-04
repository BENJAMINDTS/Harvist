# Dolibarr UI Configuration Design

**Date:** 2026-05-04  
**Author:** Carlitos6712  
**Status:** Approved

## Problem

Dolibarr URL and API key are only configurable via `.env`. Users must edit a file and restart the server. The UI has a `DolibarrConfig` form component already built, but it is blocked behind a "not configured" wall in `DolibarrPanel`. Additionally, 4 backend service helpers ignore Redis-stored credentials and only read from `.env`.

## Goal

Allow users to enter Dolibarr URL and API key through the web interface. After saving, the panel reloads automatically and shows all Dolibarr modules without a page refresh.

## Approach: Auto-redirect to config tab (Option A)

### Frontend — DolibarrPanel.tsx

**Current behavior:**  
When `!status?.configured`, renders a blocking wall with instructions to edit `.env`. The config tab is unreachable.

**New behavior:**

1. Remove the `if (!status?.configured) return <wall/>` block entirely.
2. Initialize `tab` state as `'config'` when status is not configured:
   ```ts
   const [tab, setTab] = useState<DolibarrTab>(status?.configured ? 'productos' : 'config')
   ```
   Since status is fetched async, initialize as `'productos'` and `useEffect` to switch to `'config'` when status loads unconfigured.
3. When `!configured`, disable all tabs except `'config'` (render them with `opacity-50 cursor-not-allowed pointer-events-none`).
4. Pass `onSaved` callback to `DolibarrConfig`:
   ```tsx
   {tab === 'config' && (
     <DolibarrConfig onSaved={handleConfigSaved} />
   )}
   ```
5. `handleConfigSaved` re-fetches status. If `configured`, unlocks all tabs and navigates to `'productos'`.

### Frontend — DolibarrConfig.tsx

1. Add optional prop `onSaved?: () => void`.
2. Call `onSaved?.()` after successful `POST /dolibarr/config`.
3. Remove the `setTimeout` that clears the success message (panel navigates away immediately).

### Backend — dolibarr.py

Convert 4 sync service helpers to async using `_get_dolibarr_credentials()` (Redis → `.env` fallback):

| Helper | Change |
|--------|--------|
| `_get_category_service()` | `async`, uses `_get_dolibarr_credentials()` |
| `_get_order_service()` | `async`, uses `_get_dolibarr_credentials()` |
| `_get_invoice_service()` | `async`, uses `_get_dolibarr_credentials()` |
| `_get_stock_service()` | `async`, uses `_get_dolibarr_credentials()` |

Pattern:
```python
async def _get_category_service() -> DolibarrCategoryService:
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED_MSG)
    return DolibarrCategoryService(client)
```

Migrate all endpoints calling the sync `_get_service()` (`get_product`, `create_product`, `update_product`, `delete_product`, `upload_image`, `sync_from_job`) to use the existing `_get_service_async()`.

All affected endpoints change from `def` to `async def` where needed, and add `await` to the helper call.

## Data flow

```
User opens Dolibarr tab (not configured)
  → DolibarrPanel fetches GET /dolibarr/status
  → status.configured = false
  → tab forced to 'config', other tabs disabled
  → DolibarrConfig renders

User enters URL + API key → clicks "Guardar"
  → POST /api/v1/dolibarr/config → saves to Redis
  → onSaved() fires
  → DolibarrPanel re-fetches GET /dolibarr/status
  → status.configured = true
  → all tabs unlocked, navigate to 'productos'
```

## What does NOT change

- `GET /api/v1/dolibarr/config` — no change
- `POST /api/v1/dolibarr/config` — no change
- `GET /api/v1/dolibarr/status` — no change
- `_get_dolibarr_credentials()` — no change
- `_get_service_async()` — no change
- Redis key `integration:dolibarr:config` — no change
- `.env` fallback behavior — preserved

## Files to change

| File | Change |
|------|--------|
| `frontend/src/components/dolibarr/DolibarrPanel.tsx` | Remove wall, add tab locking, pass `onSaved`, handle reload |
| `frontend/src/components/dolibarr/DolibarrConfig.tsx` | Add `onSaved` prop, call after save |
| `api/v1/endpoints/dolibarr.py` | Make 4 helpers async; migrate 6 endpoints to `_get_service_async()` |

## Out of scope

- Deleting/clearing stored credentials via UI
- Multi-environment config (dev/staging/prod)
- Odoo or WordPress config (separate future feature)
