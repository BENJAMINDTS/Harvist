/**
 * SearchConfig component — configuración de búsqueda antes de lanzar el scraping.
 *
 * Permite al usuario elegir el modo de búsqueda (EAN, Nombre+Marca o Personalizado),
 * ajustar el número de imágenes por producto y activar la generación de descripciones
 * con IA (Fase 5 — experimental). Muestra el nombre del CSV seleccionado como
 * referencia y expone los botones "Volver" e "Iniciar scraping".
 *
 * @module SearchConfig
 * @author BenjaminDTS | Carlos Vico
 * @version 1.0.0
 */

import React, { useCallback, useState } from "react";

// ─── Tipos ────────────────────────────────────────────────────────────────────

/**
 * Mapeo entre los campos internos del parser y las columnas reales del CSV.
 * Permite que el CSV del usuario tenga cualquier nombre de cabecera.
 */
export interface ColumnMapping {
  /** Columna del CSV que actúa como código único del producto. */
  columnaCodigo: string;
  /** Columna del CSV con el EAN/código de barras. */
  columnaEan: string;
  /** Columna del CSV con el nombre del producto. */
  columnaNombre: string;
  /** Columna del CSV con la marca del producto. */
  columnaMarca: string;
  /** Columna del CSV con la categoría del producto (opcional). */
  columnaCategoria: string;
  /** Columna del CSV cuyo valor se usa para nombrar los archivos de imagen (opcional). */
  columnaNombreFoto: string;
}

/** Tipo de trabajo: descarga de fotos o generación de descripciones. Mutuamente excluyentes. */
export type TipoJob = "fotos" | "descripciones";

/**
 * Valores de configuración de búsqueda que se envían al padre al lanzar el job.
 */
export interface SearchConfigValues {
  /** Tipo de trabajo: 'fotos' o 'descripciones'. */
  tipoJob: TipoJob;
  /** Modo de búsqueda seleccionado por el usuario (solo aplica en tipoJob='fotos'). */
  modo: "ean" | "nombre_marca" | "personalizado";
  /** Número de imágenes a descargar por producto (1-20, solo aplica en tipoJob='fotos'). */
  imagenesPorProducto: number;
  /**
   * Plantilla de query con placeholders para el modo personalizado.
   * Solo se usa cuando `modo === 'personalizado'`.
   */
  queryPersonalizada: string;
  /** Mapeo de columnas del CSV a campos internos del parser. */
  columnMapping: ColumnMapping;
  /** API key de Groq del usuario (opcional, tiene prioridad sobre la del .env). */
  groqApiKey: string;
  /** Tipo de tienda inyectado en el prompt (ej: 'tiendas de mascotas'). Vacío = usa el del servidor. */
  storeType: string;
}

/**
 * Props del componente SearchConfig.
 */
interface SearchConfigProps {
  /** Nombre del archivo CSV seleccionado previamente. */
  fileName: string;
  /**
   * Cabeceras detectadas en el CSV. Se usan para poblar los selectores
   * de mapeo de columnas.
   */
  csvHeaders: string[];
  /**
   * Callback asíncrono invocado al pulsar "Iniciar scraping".
   * Recibe los valores de configuración del formulario.
   */
  onLaunch: (config: SearchConfigValues) => Promise<void>;
  /** Callback invocado al pulsar "Volver". */
  onBack: () => void;
}

// ─── Constantes ───────────────────────────────────────────────────────────────

/** Número mínimo de imágenes por producto. */
const MIN_IMAGENES = 1;

/** Número máximo de imágenes por producto. */
const MAX_IMAGENES = 20;

/** Número de imágenes por defecto. */
const DEFAULT_IMAGENES = 5;

/**
 * Metadatos de cada modo de búsqueda para renderizar las radio cards.
 */
const MODOS_BUSQUEDA: ReadonlyArray<{
  valor: SearchConfigValues["modo"];
  titulo: string;
  descripcion: string;
}> = [
  {
    valor: "ean",
    titulo: "EAN",
    descripcion: "Busca por código de barras del producto.",
  },
  {
    valor: "nombre_marca",
    titulo: "Nombre + Marca",
    descripcion: "Busca combinando el nombre y la marca del producto.",
  },
  {
    valor: "personalizado",
    titulo: "Personalizado",
    descripcion:
      "Define una plantilla con placeholders: {nombre}, {marca}, {ean}, {codigo}, {categoria}.",
  },
];

// ─── Iconos SVG inline ────────────────────────────────────────────────────────
// Se usan SVGs inline para evitar dependencias externas de iconos.

interface IconProps {
  className?: string;
}

const DocumentIcon: React.FC<IconProps> = ({ className }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
    />
  </svg>
);

const ArrowLeftIcon: React.FC<IconProps> = ({ className }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18"
    />
  </svg>
);

const RocketIcon: React.FC<IconProps> = ({ className }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M15.59 14.37a6 6 0 0 1-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 0 0 6.16-12.12A14.98 14.98 0 0 0 9.631 8.41m5.96 5.96a14.926 14.926 0 0 1-5.841 2.58m-.119-8.54a6 6 0 0 0-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 0 0-2.58 5.84m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 0 1-2.448-2.448 14.9 14.9 0 0 1 .06-.312m-2.24 2.39a4.493 4.493 0 0 0-1.757 4.306 4.493 4.493 0 0 0 4.306-1.758M16.5 9a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Z"
    />
  </svg>
);

// ─── Componente ───────────────────────────────────────────────────────────────

/**
 * Formulario de configuración previo al lanzamiento del job de scraping.
 *
 * Gestiona de forma local el estado de todos los controles del formulario y
 * lo propaga al padre únicamente al confirmar con "Iniciar scraping".
 * Mientras `onLaunch` está en progreso, bloquea el botón y muestra un spinner
 * para evitar envíos duplicados.
 *
 * @author BenjaminDTS | Carlos Vico
 * @param fileName - Nombre del archivo CSV seleccionado previamente.
 * @param onLaunch - Callback asíncrono que recibe la configuración final.
 * @param onBack   - Callback invocado al pulsar "Volver".
 */
// ─── Sub-componente: selector de columna CSV ──────────────────────────────────

/**
 * Props del sub-componente ColumnSelect.
 */
interface ColumnSelectProps {
  /** id del elemento para asociar el label. */
  id: string;
  /** Etiqueta visible del campo. */
  label: string;
  /** Si true muestra un asterisco de requerido. */
  required?: boolean;
  /** Lista de cabeceras disponibles en el CSV. */
  headers: string[];
  /** Valor actualmente seleccionado. */
  value: string;
  /** Callback al cambiar la selección. */
  onChange: (val: string) => void;
  /** Texto de ayuda debajo del selector. */
  hint?: string;
}

/**
 * Selector de columna CSV con etiqueta, dropdown y texto de ayuda.
 * Renderiza las cabeceras del CSV como opciones de un <select>.
 *
 * @author BenjaminDTS | Carlos Vico
 * @param id       - id HTML del select.
 * @param label    - Etiqueta visible.
 * @param required - Indica si la columna es obligatoria.
 * @param headers  - Cabeceras del CSV.
 * @param value    - Valor seleccionado.
 * @param onChange - Callback al cambiar.
 * @param hint     - Texto de ayuda.
 */
const ColumnSelect: React.FC<ColumnSelectProps> = ({
  id,
  label,
  required = false,
  headers,
  value,
  onChange,
  hint,
}) => (
  <div className="flex flex-col gap-1">
    <label htmlFor={id} className="text-xs font-medium text-gray-700">
      {label}
      {required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={
        "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 " +
        "text-sm text-gray-800 " +
        "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent " +
        "transition-colors duration-150"
      }
    >
      {!required && (
        <option value="">(ninguna)</option>
      )}
      {headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
    </select>
    {hint && <p className="text-xs text-gray-400">{hint}</p>}
  </div>
);

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Busca en una lista de cabeceras del CSV el primer valor que coincida
 * (insensible a mayúsculas) con los nombres candidatos dados.
 * Si no hay coincidencia devuelve la primera cabecera disponible o "".
 *
 * Args:
 *   headers: Cabeceras del CSV.
 *   candidates: Nombres a buscar por orden de preferencia.
 *
 * Returns:
 *   Cabecera encontrada o primera cabecera del array o "".
 */
function autoDetect(headers: string[], ...candidates: string[]): string {
  const lower = headers.map((h) => h.toLowerCase());
  for (const c of candidates) {
    const idx = lower.indexOf(c.toLowerCase());
    if (idx !== -1) return headers[idx];
  }
  return headers[0] ?? "";
}

export const SearchConfig: React.FC<SearchConfigProps> = ({
  fileName,
  csvHeaders,
  onLaunch,
  onBack,
}) => {
  // ── Estado del formulario ────────────────────────────────────────────────────
  const [tipoJob, setTipoJob] = useState<TipoJob>("fotos");
  const [modo, setModo] = useState<SearchConfigValues["modo"]>("ean");
  const [imagenesPorProducto, setImagenesPorProducto] =
    useState<number>(DEFAULT_IMAGENES);
  const [queryPersonalizada, setQueryPersonalizada] = useState<string>("");

  // ── Estado del mapeo de columnas — se inicializa con auto-detección ──────────
  const [columnaCodigo, setColumnaCodigo] = useState<string>(
    () => autoDetect(csvHeaders, "codigo", "code", "id", "sku")
  );
  const [columnaEan, setColumnaEan] = useState<string>(
    () => autoDetect(csvHeaders, "ean", "barcode", "gtin", "upc")
  );
  const [columnaNombre, setColumnaNombre] = useState<string>(
    () => autoDetect(csvHeaders, "nombre", "name", "producto", "title")
  );
  const [columnaMarca, setColumnaMarca] = useState<string>(
    () => autoDetect(csvHeaders, "marca", "brand", "fabricante", "manufacturer")
  );
  const [columnaCategoria, setColumnaCategoria] = useState<string>(
    () => {
      const found = csvHeaders.find((h) =>
        ["categoria", "category", "tipo", "type", "familia", "family"].includes(h.toLowerCase())
      );
      return found ?? "";
    }
  );
  const [columnaNombreFoto, setColumnaNombreFoto] = useState<string>("");
  const [groqApiKey, setGroqApiKey] = useState<string>("");
  const [storeType, setStoreType] = useState<string>("");

  /** Indica si `onLaunch` está en curso para bloquear el botón y mostrar spinner. */
  const [launching, setLaunching] = useState<boolean>(false);

  // ── Handlers ────────────────────────────────────────────────────────────────

  /**
   * Maneja el cambio del slider/input de imágenes por producto.
   * Coerciona el valor al rango permitido [1, 20].
   *
   * Args:
   *   raw: Valor numérico recibido del input.
   */
  const handleImagenesChange = useCallback((raw: number): void => {
    const clamped = Math.max(MIN_IMAGENES, Math.min(MAX_IMAGENES, raw));
    setImagenesPorProducto(Number.isNaN(clamped) ? DEFAULT_IMAGENES : clamped);
  }, []);

  /**
   * Construye el objeto `SearchConfigValues` y llama a `onLaunch`.
   * Bloquea el botón durante la operación asíncrona.
   */
  const handleSubmit = useCallback(async (): Promise<void> => {
    if (launching) return;

    setLaunching(true);
    try {
      await onLaunch({
        tipoJob,
        modo,
        imagenesPorProducto,
        queryPersonalizada,
        columnMapping: {
          columnaCodigo,
          columnaEan,
          columnaNombre,
          columnaMarca,
          columnaCategoria,
          columnaNombreFoto,
        },
        groqApiKey,
        storeType,
      });
    } finally {
      // Siempre desbloquear, incluso si onLaunch lanza una excepción.
      setLaunching(false);
    }
  }, [
    launching,
    onLaunch,
    tipoJob,
    modo,
    imagenesPorProducto,
    queryPersonalizada,
    columnaCodigo,
    columnaEan,
    columnaNombre,
    columnaMarca,
    columnaCategoria,
    columnaNombreFoto,
    groqApiKey,
    storeType,
  ]);

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <section
      aria-label="Configuración de búsqueda"
      className="w-full max-w-2xl mx-auto flex flex-col gap-6 px-4 py-6 sm:px-0"
    >
      {/* ── Banner informativo del CSV ── */}
      <div
        className={
          "flex items-center gap-3 px-4 py-3 rounded-lg " +
          "bg-blue-50 border border-blue-200"
        }
        aria-label={`Archivo CSV seleccionado: ${fileName}`}
      >
        <DocumentIcon className="w-5 h-5 text-blue-500 shrink-0" />
        <div className="flex flex-col min-w-0">
          <span className="text-xs font-medium text-blue-500 uppercase tracking-wide">
            Archivo seleccionado
          </span>
          <span
            className="text-sm font-semibold text-blue-800 truncate"
            title={fileName}
          >
            {fileName}
          </span>
        </div>
      </div>

      {/* ── Selector de tipo de trabajo ── */}
      <fieldset>
        <legend className="text-sm font-semibold text-gray-700 mb-3">
          Tipo de trabajo
        </legend>
        <div className="flex flex-col gap-3 sm:flex-row">
          {(
            [
              { valor: "fotos", titulo: "Descargar fotos", descripcion: "Busca y descarga imágenes de producto mediante scraping." },
              { valor: "descripciones", titulo: "Generar descripciones", descripcion: "Genera descripciones de catálogo con IA (Claude API)." },
            ] as { valor: TipoJob; titulo: string; descripcion: string }[]
          ).map(({ valor, titulo, descripcion }) => {
            const isSelected = tipoJob === valor;
            return (
              <label
                key={valor}
                className={
                  "relative flex flex-1 cursor-pointer rounded-xl border-2 p-4 " +
                  "transition-colors duration-150 select-none " +
                  "focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-blue-500 " +
                  (isSelected
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/40")
                }
              >
                <input
                  type="radio"
                  name="tipoJob"
                  value={valor}
                  checked={isSelected}
                  onChange={() => setTipoJob(valor)}
                  className="sr-only"
                />
                <div className="flex flex-col gap-1 w-full">
                  <div className="flex items-center justify-between gap-2">
                    <span className={"text-sm font-semibold " + (isSelected ? "text-blue-700" : "text-gray-800")}>
                      {titulo}
                    </span>
                    <span
                      aria-hidden="true"
                      className={
                        "w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center " +
                        (isSelected ? "border-blue-500 bg-blue-500" : "border-gray-300 bg-white")
                      }
                    >
                      {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
                    </span>
                  </div>
                  <p className={"text-xs leading-snug " + (isSelected ? "text-blue-600" : "text-gray-500")}>
                    {descripcion}
                  </p>
                </div>
              </label>
            );
          })}
        </div>
      </fieldset>

      {/* ── Selector de modo de búsqueda (solo fotos) ── */}
      {tipoJob === "fotos" && <fieldset>
        <legend className="text-sm font-semibold text-gray-700 mb-3">
          Modo de búsqueda
        </legend>
        <div className="flex flex-col gap-3 sm:flex-row">
          {MODOS_BUSQUEDA.map(({ valor, titulo, descripcion }) => {
            const isSelected = modo === valor;
            return (
              <label
                key={valor}
                className={
                  "relative flex flex-1 cursor-pointer rounded-xl border-2 p-4 " +
                  "transition-colors duration-150 select-none " +
                  "focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-blue-500 " +
                  (isSelected
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/40")
                }
              >
                <input
                  type="radio"
                  name="modo"
                  value={valor}
                  checked={isSelected}
                  onChange={() => setModo(valor)}
                  className="sr-only"
                  aria-describedby={`modo-desc-${valor}`}
                />
                <div className="flex flex-col gap-1 w-full">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={
                        "text-sm font-semibold " +
                        (isSelected ? "text-blue-700" : "text-gray-800")
                      }
                    >
                      {titulo}
                    </span>
                    {/* Indicador visual de selección */}
                    <span
                      aria-hidden="true"
                      className={
                        "w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center " +
                        (isSelected
                          ? "border-blue-500 bg-blue-500"
                          : "border-gray-300 bg-white")
                      }
                    >
                      {isSelected && (
                        <span className="w-1.5 h-1.5 rounded-full bg-white" />
                      )}
                    </span>
                  </div>
                  <p
                    id={`modo-desc-${valor}`}
                    className={
                      "text-xs leading-snug " +
                      (isSelected ? "text-blue-600" : "text-gray-500")
                    }
                  >
                    {descripcion}
                  </p>
                </div>
              </label>
            );
          })}
        </div>

        {/* Campo de plantilla personalizada — solo visible en modo "personalizado" */}
        {modo === "personalizado" && (
          <div className="mt-4">
            <label
              htmlFor="query-personalizada"
              className="block text-xs font-medium text-gray-600 mb-1.5"
            >
              Plantilla de query
            </label>
            <input
              id="query-personalizada"
              type="text"
              value={queryPersonalizada}
              onChange={(e) => setQueryPersonalizada(e.target.value)}
              placeholder="{nombre} {marca} {ean}"
              className={
                "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 " +
                "text-sm text-gray-800 placeholder-gray-400 " +
                "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent " +
                "transition-colors duration-150"
              }
              aria-describedby="query-personalizada-hint"
            />
            <p
              id="query-personalizada-hint"
              className="mt-1.5 text-xs text-gray-400"
            >
              Placeholders disponibles:{" "}
              <code className="font-mono text-gray-600">{"{nombre}"}</code>,{" "}
              <code className="font-mono text-gray-600">{"{marca}"}</code>,{" "}
              <code className="font-mono text-gray-600">{"{ean}"}</code>,{" "}
              <code className="font-mono text-gray-600">{"{codigo}"}</code>,{" "}
              <code className="font-mono text-gray-600">{"{categoria}"}</code>
            </p>
          </div>
        )}
      </fieldset>

      }

      {/* ── Mapeo de columnas ── */}
      {csvHeaders.length > 0 && (
        <fieldset className="rounded-xl border border-gray-200 bg-white p-4">
          <legend className="text-sm font-semibold text-gray-700 px-1">
            Mapeo de columnas
          </legend>
          <p className="text-xs text-gray-500 mt-1 mb-4">
            Indica qué columna de tu CSV corresponde a cada campo.
            La detección automática ya ha pre-seleccionado las más probables.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Columna Código — siempre requerida */}
            <ColumnSelect
              id="col-codigo"
              label="Código del producto"
              required
              headers={csvHeaders}
              value={columnaCodigo}
              onChange={setColumnaCodigo}
              hint={
                tipoJob === "descripciones"
                  ? "Identificador único del producto."
                  : "Identificador único — se usa para nombrar las imágenes."
              }
            />

            {/* ── Columnas específicas de fotos ── */}
            {tipoJob === "fotos" && (
              <>
                {/* Columna EAN — requerida en modo EAN, opcional en PERSONALIZADO */}
                {(modo === "ean" || modo === "personalizado") && (
                  <ColumnSelect
                    id="col-ean"
                    label="EAN / Código de barras"
                    required={modo === "ean"}
                    headers={csvHeaders}
                    value={columnaEan}
                    onChange={setColumnaEan}
                    hint={
                      modo === "ean"
                        ? "Requerido en modo EAN."
                        : "Opcional — disponible como {ean} en la plantilla."
                    }
                  />
                )}

                {/* Columna Nombre — requerida en NOMBRE_MARCA, opcional en PERSONALIZADO */}
                {(modo === "nombre_marca" || modo === "personalizado") && (
                  <ColumnSelect
                    id="col-nombre"
                    label="Nombre del producto"
                    required={modo === "nombre_marca"}
                    headers={csvHeaders}
                    value={columnaNombre}
                    onChange={setColumnaNombre}
                    hint={
                      modo === "nombre_marca"
                        ? "Requerido en modo Nombre + Marca."
                        : "Opcional — disponible como {nombre} en la plantilla."
                    }
                  />
                )}

                {/* Columna Marca — requerida en NOMBRE_MARCA, opcional en PERSONALIZADO */}
                {(modo === "nombre_marca" || modo === "personalizado") && (
                  <ColumnSelect
                    id="col-marca"
                    label="Marca del producto"
                    required={modo === "nombre_marca"}
                    headers={csvHeaders}
                    value={columnaMarca}
                    onChange={setColumnaMarca}
                    hint={
                      modo === "nombre_marca"
                        ? "Requerido en modo Nombre + Marca."
                        : "Opcional — disponible como {marca} en la plantilla."
                    }
                  />
                )}

                {/* Columna Categoría — solo en modo personalizado */}
                {modo === "personalizado" && (
                  <ColumnSelect
                    id="col-categoria"
                    label="Categoría del producto"
                    headers={csvHeaders}
                    value={columnaCategoria}
                    onChange={setColumnaCategoria}
                    hint="Opcional — disponible como {categoria} en la plantilla personalizada."
                  />
                )}

                {/* Columna para nombrar las fotos */}
                <ColumnSelect
                  id="col-nombre-foto"
                  label="Nombre de las fotos"
                  headers={csvHeaders}
                  value={columnaNombreFoto}
                  onChange={setColumnaNombreFoto}
                  hint="Columna cuyo valor se usa para nombrar los archivos de imagen. Sin selección = usa el código."
                />
              </>
            )}

            {/* ── Columnas específicas de descripciones ── */}
            {tipoJob === "descripciones" && (
              <>
                <ColumnSelect
                  id="col-nombre"
                  label="Nombre del producto"
                  required
                  headers={csvHeaders}
                  value={columnaNombre}
                  onChange={setColumnaNombre}
                  hint="Requerido — se envía al modelo de IA para generar la descripción."
                />

                <ColumnSelect
                  id="col-marca"
                  label="Marca del producto"
                  required
                  headers={csvHeaders}
                  value={columnaMarca}
                  onChange={setColumnaMarca}
                  hint="Requerido — se incluye en el contexto del prompt."
                />

                <ColumnSelect
                  id="col-categoria"
                  label="Categoría del producto"
                  headers={csvHeaders}
                  value={columnaCategoria}
                  onChange={setColumnaCategoria}
                  hint="Opcional — ayuda al modelo a adaptar la descripción al tipo de producto."
                />
              </>
            )}
          </div>
        </fieldset>
      )}

      {/* ── Configuración IA (solo descripciones) ── */}
      {tipoJob === "descripciones" && (
        <fieldset className="rounded-xl border border-gray-200 bg-white p-4 flex flex-col gap-4">
          <legend className="text-sm font-semibold text-gray-700 px-1">
            Configuración de IA
          </legend>

          {/* API Key de Groq */}
          <div className="flex flex-col gap-1">
            <label
              htmlFor="groq-api-key"
              className="text-xs font-medium text-gray-700"
            >
              API Key de Groq
            </label>
            <input
              id="groq-api-key"
              type="password"
              value={groqApiKey}
              onChange={(e) => setGroqApiKey(e.target.value)}
              placeholder="gsk_..."
              className={
                "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 " +
                "text-sm text-gray-800 placeholder-gray-400 font-mono " +
                "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent " +
                "transition-colors duration-150"
              }
              aria-describedby="groq-api-key-hint"
            />
            <p id="groq-api-key-hint" className="text-xs text-gray-400">
              Opcional — si no la introduces se usa la configurada en el servidor.
              Obtenla en{" "}
              <span className="font-mono text-gray-500">console.groq.com</span>
            </p>
          </div>

          {/* Tipo de tienda */}
          <div className="flex flex-col gap-1">
            <label
              htmlFor="store-type"
              className="text-xs font-medium text-gray-700"
            >
              Tipo de tienda
            </label>
            <input
              id="store-type"
              type="text"
              value={storeType}
              onChange={(e) => setStoreType(e.target.value)}
              placeholder="tiendas de mascotas"
              className={
                "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 " +
                "text-sm text-gray-800 placeholder-gray-400 " +
                "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent " +
                "transition-colors duration-150"
              }
              aria-describedby="store-type-hint"
            />
            <p id="store-type-hint" className="text-xs text-gray-400">
              Define el sector en el que trabaja el copywriter de IA.
              Ejemplos: <em>tiendas de mascotas</em>, <em>ferreterías</em>, <em>ropa deportiva</em>.
              Vacío = usa el valor del servidor.
            </p>
          </div>
        </fieldset>
      )}

      {/* ── Imágenes por producto (solo fotos) ── */}
      {tipoJob === "fotos" && <div>
        <div className="flex items-center justify-between mb-3">
          <label
            htmlFor="imagenes-slider"
            className="text-sm font-semibold text-gray-700"
          >
            Imágenes por producto
          </label>
          {/* Input numérico sincronizado con el slider */}
          <input
            type="number"
            min={MIN_IMAGENES}
            max={MAX_IMAGENES}
            value={imagenesPorProducto}
            onChange={(e) => handleImagenesChange(parseInt(e.target.value, 10))}
            aria-label="Número exacto de imágenes por producto"
            className={
              "w-16 rounded-lg border border-gray-300 bg-white px-2 py-1 " +
              "text-sm text-center text-gray-800 font-semibold " +
              "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent " +
              "transition-colors duration-150 [appearance:textfield] " +
              "[&::-webkit-outer-spin-button]:appearance-none " +
              "[&::-webkit-inner-spin-button]:appearance-none"
            }
          />
        </div>

        <input
          id="imagenes-slider"
          type="range"
          min={MIN_IMAGENES}
          max={MAX_IMAGENES}
          step={1}
          value={imagenesPorProducto}
          onChange={(e) => handleImagenesChange(parseInt(e.target.value, 10))}
          aria-valuemin={MIN_IMAGENES}
          aria-valuemax={MAX_IMAGENES}
          aria-valuenow={imagenesPorProducto}
          aria-label={`Imágenes por producto: ${imagenesPorProducto}`}
          className={
            "w-full h-2 rounded-full appearance-none cursor-pointer " +
            "bg-gray-200 accent-blue-500 " +
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          }
        />

        {/* Etiquetas de rango */}
        <div
          className="flex justify-between mt-1"
          aria-hidden="true"
        >
          <span className="text-xs text-gray-400">{MIN_IMAGENES}</span>
          <span className="text-xs text-gray-400">{MAX_IMAGENES}</span>
        </div>
      </div>}

      {/* ── Acciones ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between">
        {/* Botón Volver */}
        <button
          type="button"
          onClick={onBack}
          disabled={launching}
          className={
            "inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg " +
            "text-sm font-medium text-gray-700 bg-white border border-gray-300 " +
            "hover:bg-gray-50 transition-colors duration-150 " +
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-gray-400 " +
            "disabled:opacity-50 disabled:cursor-not-allowed"
          }
        >
          <ArrowLeftIcon className="w-4 h-4" />
          Volver
        </button>

        {/* Botón Iniciar scraping */}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={launching}
          aria-busy={launching}
          className={
            "inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg " +
            "text-sm font-semibold text-white " +
            "transition-colors duration-150 " +
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 " +
            "disabled:opacity-60 disabled:cursor-not-allowed " +
            (launching
              ? "bg-blue-400"
              : "bg-blue-600 hover:bg-blue-700 active:bg-blue-800")
          }
        >
          {launching ? (
            <>
              {/* Spinner SVG animado */}
              <svg
                className="w-4 h-4 animate-spin"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Z"
                />
              </svg>
              Iniciando…
            </>
          ) : (
            <>
              <RocketIcon className="w-4 h-4" />
              Iniciar scraping
            </>
          )}
        </button>
      </div>
    </section>
  );
};
