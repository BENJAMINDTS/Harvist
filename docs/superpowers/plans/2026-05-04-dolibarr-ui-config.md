# Dolibarr UI Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users enter Dolibarr URL and API key via the web UI; panel auto-reloads on save without a page refresh.

**Architecture:** Frontend form already exists in `DolibarrConfig.tsx` and backend already stores config to Redis. Two problems to fix: (1) `DolibarrPanel` blocks the form with a wall when unconfigured; (2) four backend service helpers only read `.env`, ignoring Redis-stored credentials. Fix the wall, add an `onSaved` callback that triggers status re-fetch, and convert the four sync helpers to async so all endpoints read Redis first.

**Tech Stack:** FastAPI + asyncio (Python), React 18 + TypeScript + Tailwind CSS, Redis via `aioredis`, pytest + `TestClient`.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `api/v1/endpoints/dolibarr.py` | Modify | Convert 4 sync helpers to async; migrate 6 product endpoints to `_get_service_async()` |
| `tests/integration/test_dolibarr_categories_endpoints.py` | Modify | Add Redis-path test for categories |
| `tests/integration/test_dolibarr_orders_endpoints.py` | Modify | Add Redis-path test for orders |
| `tests/integration/test_dolibarr_invoices_endpoints.py` | Modify | Add Redis-path test for invoices |
| `tests/integration/test_dolibarr_stocks_endpoints.py` | Modify | Add Redis-path test for stocks |
| `frontend/src/components/dolibarr/DolibarrConfig.tsx` | Modify | Add optional `onSaved` prop; call it after save |
| `frontend/src/components/dolibarr/DolibarrPanel.tsx` | Modify | Remove wall; auto-switch to config tab; lock other tabs when unconfigured; reload on save |

---

## Task 1 — Write failing test: categories Redis-config path

**Files:**
- Modify: `tests/integration/test_dolibarr_categories_endpoints.py`

This test verifies that `list_categories` returns 200 when credentials come from Redis (not `.env`). The current sync helper ignores Redis, so it will return 503 — the test fails, confirming the gap.

- [ ] **Step 1: Add the test**

Open `tests/integration/test_dolibarr_categories_endpoints.py`. Add these imports at the top if not already present:

```python
from unittest.mock import MagicMock
```

Then add this test class at the end of the file:

```python
class TestRedisConfigPath:
    """Tests que verifican que las credenciales de Redis se usan cuando .env no tiene config."""

    def test_list_categories_uses_redis_config_when_env_not_set(self, client):
        """
        list_categories retorna 200 usando credenciales de Redis
        aunque .env no tenga DOLIBARR_URL ni DOLIBARR_API_KEY.
        """
        mock_svc = MagicMock()
        mock_svc.list_categories = AsyncMock(return_value=[])

        with patch(
            "api.v1.endpoints.dolibarr._get_dolibarr_credentials",
            new=AsyncMock(return_value=("https://dolibarr.test", "test-key")),
        ):
            with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                with patch(
                    "api.v1.endpoints.dolibarr.DolibarrCategoryService",
                    return_value=mock_svc,
                ):
                    response = client.get("/api/v1/dolibarr/categories")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
```

- [ ] **Step 2: Run the test and confirm it FAILS**

```bash
pytest tests/integration/test_dolibarr_categories_endpoints.py::TestRedisConfigPath -v
```

Expected: `FAILED` — current `_get_category_service` checks `settings.dolibarr_configured` synchronously and never calls `_get_dolibarr_credentials`, so it returns 503.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/integration/test_dolibarr_categories_endpoints.py
git commit -m "test: add failing test for categories Redis config path"
```

---

## Task 2 — Implement: convert `_get_category_service` to async

**Files:**
- Modify: `api/v1/endpoints/dolibarr.py`

- [ ] **Step 1: Replace the sync helper with an async version**

Find the function `_get_category_service` (around line 582). Replace the entire function:

```python
# BEFORE:
def _get_category_service() -> DolibarrCategoryService:
    settings = get_settings()
    if not settings.dolibarr_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    try:
        client = DolibarrClient(settings)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrCategoryService(client)

# AFTER:
async def _get_category_service() -> DolibarrCategoryService:
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrCategoryService(client)
```

- [ ] **Step 2: Add `await` to every call site of `_get_category_service`**

There are 9 callers in `dolibarr.py`. Each one looks like `svc = _get_category_service()`. Change all of them to `svc = await _get_category_service()`:

```python
# list_categories (~line 622):
svc = await _get_category_service()

# get_tree (~line 650):
svc = await _get_category_service()

# get_category (~line 672):
svc = await _get_category_service()

# create_category (~line 700):
svc = await _get_category_service()

# update_category (~line 737):
svc = await _get_category_service()

# delete_category (~line 760):
svc = await _get_category_service()

# assign_product (~line 782):
svc = await _get_category_service()

# remove_product (~line 805):
svc = await _get_category_service()

# list_products_in_category (~line 828):
svc = await _get_category_service()
```

- [ ] **Step 3: Run the new Redis-path test and confirm it PASSES**

```bash
pytest tests/integration/test_dolibarr_categories_endpoints.py::TestRedisConfigPath -v
```

Expected: `PASSED`

- [ ] **Step 4: Run the full categories test suite and confirm nothing broke**

```bash
pytest tests/integration/test_dolibarr_categories_endpoints.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add api/v1/endpoints/dolibarr.py
git commit -m "feat: convert _get_category_service to async with Redis config support"
```

---

## Task 3 — Write failing tests: orders, invoices, stocks Redis-config path

**Files:**
- Modify: `tests/integration/test_dolibarr_orders_endpoints.py`
- Modify: `tests/integration/test_dolibarr_invoices_endpoints.py`
- Modify: `tests/integration/test_dolibarr_stocks_endpoints.py`

- [ ] **Step 1: Add test to orders file**

Open `tests/integration/test_dolibarr_orders_endpoints.py`. Verify that `AsyncMock`, `MagicMock`, and `patch` are imported from `unittest.mock`. Add at the end of the file:

```python
class TestRedisConfigPath:
    """Tests que verifican que las credenciales de Redis se usan cuando .env no tiene config."""

    def test_list_orders_uses_redis_config_when_env_not_set(self, client):
        """
        list_orders retorna 200 usando credenciales de Redis
        aunque .env no tenga DOLIBARR_URL ni DOLIBARR_API_KEY.
        """
        mock_svc = MagicMock()
        mock_svc.list_orders = AsyncMock(return_value=[])

        with patch(
            "api.v1.endpoints.dolibarr._get_dolibarr_credentials",
            new=AsyncMock(return_value=("https://dolibarr.test", "test-key")),
        ):
            with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                with patch(
                    "api.v1.endpoints.dolibarr.DolibarrOrderService",
                    return_value=mock_svc,
                ):
                    response = client.get("/api/v1/dolibarr/orders")

        assert response.status_code == 200
        assert response.json()["items"] == []
```

- [ ] **Step 2: Add test to invoices file**

Open `tests/integration/test_dolibarr_invoices_endpoints.py`. Verify `AsyncMock`, `MagicMock`, `patch` are imported. Add at the end:

```python
class TestRedisConfigPath:
    """Tests que verifican que las credenciales de Redis se usan cuando .env no tiene config."""

    def test_list_invoices_uses_redis_config_when_env_not_set(self, client):
        """
        list_invoices retorna 200 usando credenciales de Redis
        aunque .env no tenga DOLIBARR_URL ni DOLIBARR_API_KEY.
        """
        mock_svc = MagicMock()
        mock_svc.list_invoices = AsyncMock(return_value=[])

        with patch(
            "api.v1.endpoints.dolibarr._get_dolibarr_credentials",
            new=AsyncMock(return_value=("https://dolibarr.test", "test-key")),
        ):
            with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                with patch(
                    "api.v1.endpoints.dolibarr.DolibarrInvoiceService",
                    return_value=mock_svc,
                ):
                    response = client.get("/api/v1/dolibarr/invoices")

        assert response.status_code == 200
        assert response.json()["items"] == []
```

- [ ] **Step 3: Add test to stocks file**

Open `tests/integration/test_dolibarr_stocks_endpoints.py`. Verify `AsyncMock`, `MagicMock`, `patch` are imported. Add at the end of the file (outside any existing class):

```python
class TestRedisConfigPath:
    """Tests que verifican que las credenciales de Redis se usan cuando .env no tiene config."""

    def test_list_warehouses_uses_redis_config_when_env_not_set(self, client):
        """
        list_warehouses retorna 200 usando credenciales de Redis
        aunque .env no tenga DOLIBARR_URL ni DOLIBARR_API_KEY.
        """
        mock_svc = MagicMock()
        mock_svc.list_warehouses = AsyncMock(return_value=[])

        with patch(
            "api.v1.endpoints.dolibarr._get_dolibarr_credentials",
            new=AsyncMock(return_value=("https://dolibarr.test", "test-key")),
        ):
            with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                with patch(
                    "api.v1.endpoints.dolibarr.DolibarrStockService",
                    return_value=mock_svc,
                ):
                    response = client.get("/api/v1/dolibarr/stocks/warehouses")

        assert response.status_code == 200
        assert response.json()["items"] == []
```

Note: if `test_dolibarr_stocks_endpoints.py` uses `AsyncClient` (httpx) instead of `TestClient`, its `client` fixture may be named differently. Check the fixture name and adjust the parameter accordingly.

- [ ] **Step 4: Run all three new tests and confirm they FAIL**

```bash
pytest tests/integration/test_dolibarr_orders_endpoints.py::TestRedisConfigPath tests/integration/test_dolibarr_invoices_endpoints.py::TestRedisConfigPath tests/integration/test_dolibarr_stocks_endpoints.py::TestRedisConfigPath -v
```

Expected: all three `FAILED` (sync helpers ignore Redis, return 503)

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/integration/test_dolibarr_orders_endpoints.py tests/integration/test_dolibarr_invoices_endpoints.py tests/integration/test_dolibarr_stocks_endpoints.py
git commit -m "test: add failing tests for orders/invoices/stocks Redis config path"
```

---

## Task 4 — Implement: convert `_get_order_service`, `_get_invoice_service`, `_get_stock_service` to async

**Files:**
- Modify: `api/v1/endpoints/dolibarr.py`

- [ ] **Step 1: Replace `_get_order_service`**

Find `def _get_order_service()` (around line 1157). Replace the entire function:

```python
async def _get_order_service() -> DolibarrOrderService:
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrOrderService(client)
```

Add `await` to every call site of `_get_order_service` (6 callers: `list_orders`, `get_order`, `create_order`, `add_order_line`, `update_order_status`, `delete_order`):

```python
svc = await _get_order_service()
```

- [ ] **Step 2: Replace `_get_invoice_service`**

Find `def _get_invoice_service()` (around line 1407). Replace:

```python
async def _get_invoice_service() -> DolibarrInvoiceService:
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrInvoiceService(client)
```

Add `await` to every call site of `_get_invoice_service` (8 callers: `list_invoices`, `get_invoice`, `create_invoice`, `add_invoice_line`, `validate_invoice`, `send_invoice_by_email`, `mark_invoice_as_paid`, `delete_invoice`):

```python
svc = await _get_invoice_service()
```

- [ ] **Step 3: Replace `_get_stock_service`**

Find `def _get_stock_service()` (around line 1755). Replace:

```python
async def _get_stock_service() -> DolibarrStockService:
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrStockService(client)
```

Add `await` to every call site of `_get_stock_service` (6 callers: `list_warehouses`, `get_warehouse`, `get_product_stock`, `list_movements`, `add_movement`, `transfer_stock`):

```python
svc = await _get_stock_service()
```

- [ ] **Step 4: Run the three new Redis-path tests — confirm they PASS**

```bash
pytest tests/integration/test_dolibarr_orders_endpoints.py::TestRedisConfigPath tests/integration/test_dolibarr_invoices_endpoints.py::TestRedisConfigPath tests/integration/test_dolibarr_stocks_endpoints.py::TestRedisConfigPath -v
```

Expected: all three `PASSED`

- [ ] **Step 5: Run the full suites for orders, invoices, stocks — confirm nothing broke**

```bash
pytest tests/integration/test_dolibarr_orders_endpoints.py tests/integration/test_dolibarr_invoices_endpoints.py tests/integration/test_dolibarr_stocks_endpoints.py -v
```

Expected: all `PASSED`

- [ ] **Step 6: Commit**

```bash
git add api/v1/endpoints/dolibarr.py
git commit -m "feat: convert order/invoice/stock service helpers to async with Redis config support"
```

---

## Task 5 — Migrate sync product endpoints to `_get_service_async()`

**Files:**
- Modify: `api/v1/endpoints/dolibarr.py`

Six product endpoints still call the sync `_get_service()`: `get_product`, `create_product`, `update_product`, `delete_product`, `upload_image`, `sync_from_job`.

- [ ] **Step 1: Replace `svc = _get_service()` with `svc = await _get_service_async()` in all six endpoints**

In `get_product` (~line 403):
```python
svc = await _get_service_async()
```

In `create_product` (~line 430):
```python
svc = await _get_service_async()
```

In `update_product` (~line 455):
```python
svc = await _get_service_async()
```

In `delete_product` (~line 477):
```python
svc = await _get_service_async()
```

In `upload_image` (~line 499):
```python
svc = await _get_service_async()
```

In `sync_from_job` (~line 549):
```python
svc = await _get_service_async()
```

- [ ] **Step 2: Run all product endpoint tests**

```bash
pytest tests/integration/test_dolibarr_products_endpoints.py -v
```

Expected: all `PASSED`. If any fail because they mock `_get_service` instead of `_get_service_async`, update those specific test patches from `"api.v1.endpoints.dolibarr._get_service"` to `"api.v1.endpoints.dolibarr._get_service_async"`.

- [ ] **Step 3: Run the full Dolibarr test suite**

```bash
pytest tests/integration/test_dolibarr_products_endpoints.py tests/integration/test_dolibarr_categories_endpoints.py tests/integration/test_dolibarr_orders_endpoints.py tests/integration/test_dolibarr_invoices_endpoints.py tests/integration/test_dolibarr_stocks_endpoints.py tests/integration/test_dolibarr_thirdparties_endpoints.py tests/integration/test_dolibarr_status.py -v
```

Expected: all `PASSED`

- [ ] **Step 4: Commit**

```bash
git add api/v1/endpoints/dolibarr.py
git commit -m "feat: migrate product endpoints to _get_service_async for Redis config support"
```

---

## Task 6 — Update `DolibarrConfig.tsx`: add `onSaved` prop

**Files:**
- Modify: `frontend/src/components/dolibarr/DolibarrConfig.tsx`

- [ ] **Step 1: Add `onSaved` to the Props interface**

Find the `Props` interface (line 16–18). Replace it:

```typescript
interface Props {
  className?: string
  onSaved?: () => void
}
```

- [ ] **Step 2: Destructure `onSaved` from props**

Find line 20:
```typescript
export default function DolibarrConfig({ className = '' }: Props) {
```
Replace with:
```typescript
export default function DolibarrConfig({ className = '', onSaved }: Props) {
```

- [ ] **Step 3: Call `onSaved` after a successful save and remove the setTimeout**

Find the `handleSave` function. The current success block is:

```typescript
if (res.data) {
  setMessage({ type: 'success', text: 'Configuración guardada correctamente ✓' })
  setTimeout(() => setMessage({ type: '', text: '' }), 3000)
}
```

Replace it with:

```typescript
if (res.data) {
  setMessage({ type: 'success', text: 'Configuración guardada correctamente ✓' })
  onSaved?.()
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dolibarr/DolibarrConfig.tsx
git commit -m "feat: add onSaved callback prop to DolibarrConfig"
```

---

## Task 7 — Update `DolibarrPanel.tsx`: remove wall, lock tabs, auto-reload

**Files:**
- Modify: `frontend/src/components/dolibarr/DolibarrPanel.tsx`

- [ ] **Step 1: Add a `useEffect` that auto-switches to the config tab when status is unconfigured**

Current file has (line 24–40):
```typescript
const [tab, setTab] = useState<DolibarrTab>('productos')
const [status, setStatus] = useState<IntegrationStatus | null>(null)
const [loading, setLoading] = useState(true)

useEffect(() => {
  ;(async () => {
    try {
      setLoading(true)
      const st = await getDolibarrStatus()
      setStatus(st)
    } catch (err) {
      console.error('Error loading Dolibarr status:', err)
    } finally {
      setLoading(false)
    }
  })()
}, [])
```

Replace with:
```typescript
const [tab, setTab] = useState<DolibarrTab>('productos')
const [status, setStatus] = useState<IntegrationStatus | null>(null)
const [loading, setLoading] = useState(true)

useEffect(() => {
  ;(async () => {
    try {
      setLoading(true)
      const st = await getDolibarrStatus()
      setStatus(st)
    } catch (err) {
      console.error('Error loading Dolibarr status:', err)
    } finally {
      setLoading(false)
    }
  })()
}, [])

useEffect(() => {
  if (status && !status.configured) {
    setTab('config')
  }
}, [status])
```

- [ ] **Step 2: Add `handleConfigSaved` callback**

After the `useEffect` blocks, add:

```typescript
const handleConfigSaved = async () => {
  try {
    const st = await getDolibarrStatus()
    setStatus(st)
    if (st.configured) {
      setTab('productos')
    }
  } catch (err) {
    console.error('Error recargando status Dolibarr:', err)
  }
}
```

- [ ] **Step 3: Remove the "not configured" wall block**

Delete these lines entirely (lines 52–81):

```typescript
if (!status?.configured) {
  return (
    <div className={`p-6 ${className}`}>
      <div className="bg-orange-50 border-l-4 border-orange-400 p-4 rounded">
        ...
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Update the tabs rendering to disable non-config tabs when unconfigured**

Find the `.map()` over tabs (around line 132). The current tab button is:

```tsx
<button
  key={t.id}
  onClick={() => setTab(t.id)}
  className={`px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
    tab === t.id
      ? 'text-blue-600 border-b-2 border-blue-600'
      : 'text-gray-700 hover:text-gray-900'
  }`}
>
  {t.label}
</button>
```

Replace with:

```tsx
<button
  key={t.id}
  onClick={() => setTab(t.id)}
  disabled={!status?.configured && t.id !== 'config'}
  className={`px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
    tab === t.id
      ? 'text-blue-600 border-b-2 border-blue-600'
      : 'text-gray-700 hover:text-gray-900'
  } ${!status?.configured && t.id !== 'config' ? 'opacity-40 cursor-not-allowed' : ''}`}
>
  {t.label}
</button>
```

- [ ] **Step 5: Pass `onSaved` to `DolibarrConfig`**

Find the line (around line 163):
```tsx
{tab === 'config' && <DolibarrConfig />}
```

Replace with:
```tsx
{tab === 'config' && <DolibarrConfig onSaved={handleConfigSaved} />}
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 7: Build to verify no bundling errors**

```bash
cd frontend && npm run build
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/dolibarr/DolibarrPanel.tsx
git commit -m "feat: remove config wall in DolibarrPanel, lock tabs when unconfigured, auto-reload on save"
```

---

## Task 8 — Manual end-to-end verification

- [ ] **Step 1: Start all services**

```bash
# Terminal 1 — Redis
docker run -d -p 6379:6379 redis:7-alpine

# Terminal 2 — FastAPI (ensure .env.development has NO DOLIBARR_URL/DOLIBARR_API_KEY)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3 — Frontend
cd frontend && npm run dev
```

- [ ] **Step 2: Verify "not configured" state**

Open `http://localhost:5173`. Navigate to the Dolibarr module.

Expected:
- Panel renders (no orange wall)
- "Configuración" tab is active automatically
- All other tabs (Productos, Terceros, Pedidos, Facturas, Stock) are visually dimmed and unclickable

- [ ] **Step 3: Enter credentials and save**

In the config form, enter:
- URL: any non-empty URL (e.g. `https://demo.dolibarr.org`)
- API Key: any non-empty string (e.g. `test-key-123`)

Click "Guardar Configuración".

Expected:
- Brief "Configuración guardada correctamente ✓" message appears
- Panel auto-navigates to "Productos" tab
- All tabs become enabled (full opacity, clickable)
- No page reload

- [ ] **Step 4: Verify credentials persist after page reload**

Reload the page. Navigate back to Dolibarr.

Expected:
- Panel opens on "Productos" tab (configured state)
- "Configuración" tab, when clicked, shows the saved URL pre-filled
- API Key field shows the saved value

- [ ] **Step 5: Verify all Dolibarr endpoints now use Redis credentials**

Call from the UI or Swagger (`http://localhost:8000/api/docs`):
- `GET /api/v1/dolibarr/categories` — should return 200 (or 502 if Dolibarr unreachable, not 503)
- `GET /api/v1/dolibarr/orders` — same
- `GET /api/v1/dolibarr/invoices` — same
- `GET /api/v1/dolibarr/stocks/warehouses` — same

Expected: none return 503 (which would mean credentials not found)
