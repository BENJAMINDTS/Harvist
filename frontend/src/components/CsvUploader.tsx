/**
 * CsvUploader component — zona de carga de archivos CSV con drag & drop.
 *
 * Valida el tipo MIME y la extensión del archivo en el cliente antes de
 * propagarlo al componente padre mediante el callback `onFileSelected`.
 * Además extrae y expone las cabeceras del CSV para que el paso siguiente
 * pueda ofrecer un selector gráfico de columnas.
 *
 * @module CsvUploader
 * @author BenjaminDTS | Carlos Vico
 * @version 1.1.0
 */

import React, { useCallback, useRef, useState } from "react";

// ─── Tipos ────────────────────────────────────────────────────────────────────

/**
 * Props del componente CsvUploader.
 */
interface CsvUploaderProps {
  /**
   * Callback invocado cuando el usuario selecciona un CSV válido.
   * Recibe el archivo y la lista de cabeceras detectadas en la primera fila.
   */
  onFileSelected: (file: File, headers: string[]) => void;
}

/**
 * Posibles estados visuales del uploader.
 */
type UploaderState = "idle" | "dragover" | "selected" | "error";

// ─── Constantes ───────────────────────────────────────────────────────────────

/** MIME types aceptados para archivos CSV. */
const ACCEPTED_MIME_TYPES: ReadonlySet<string> = new Set([
  "text/csv",
  "text/plain",
  "application/csv",
]);

/** Extensión obligatoria del archivo. */
const ACCEPTED_EXTENSION = ".csv";

// ─── Utilidades ───────────────────────────────────────────────────────────────

/**
 * Lee la primera línea de un archivo CSV y devuelve sus cabeceras.
 *
 * Detecta el delimitador más probable (`,` `;` `\t` `|`) contando
 * cuántas celdas produce cada candidato en la primera fila.
 *
 * Args:
 *   file: Archivo CSV a leer.
 *
 * Returns:
 *   Promesa que resuelve con el array de nombres de columna (strings limpios).
 */
function parseCsvHeaders(file: File): Promise<string[]> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? "";
      const firstLine = text.split(/\r?\n/)[0] ?? "";

      const candidates = [",", ";", "\t", "|"] as const;
      let delimiter: string = ",";
      let maxCount = 0;
      for (const d of candidates) {
        const count = firstLine.split(d).length;
        if (count > maxCount) {
          maxCount = count;
          delimiter = d;
        }
      }

      const headers = firstLine
        .split(delimiter)
        .map((h) => h.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean);

      resolve(headers);
    };
    // Leer solo los primeros 8 KB — suficiente para la cabecera
    reader.readAsText(file.slice(0, 8192));
  });
}

/**
 * Formatea un tamaño en bytes a una cadena legible (KB / MB).
 *
 * Args:
 *   bytes: Tamaño del archivo en bytes.
 *
 * Returns:
 *   Cadena con el tamaño formateado y la unidad correspondiente.
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Valida que un archivo sea un CSV por extensión y por tipo MIME.
 *
 * Args:
 *   file: Objeto File a validar.
 *
 * Returns:
 *   Cadena con el mensaje de error, o `null` si el archivo es válido.
 */
function validateCsvFile(file: File): string | null {
  const hasValidExtension = file.name
    .toLowerCase()
    .endsWith(ACCEPTED_EXTENSION);

  if (!hasValidExtension) {
    return `El archivo debe tener extensión ${ACCEPTED_EXTENSION}. Se recibió: "${file.name}".`;
  }

  const hasValidMime =
    file.type === "" || ACCEPTED_MIME_TYPES.has(file.type);

  if (!hasValidMime) {
    return `Tipo de archivo no permitido (${file.type}). Solo se aceptan archivos CSV.`;
  }

  return null;
}

// ─── Componente ───────────────────────────────────────────────────────────────

/**
 * Zona interactiva de carga de archivos CSV con soporte de drag & drop y
 * apertura del explorador de archivos nativo.
 *
 * Gestiona cuatro estados visuales: idle, dragover, selected y error.
 * La validación de tipo MIME y extensión se realiza en el cliente antes
 * de invocar `onFileSelected`.
 *
 * @author BenjaminDTS | Carlos Vico
 * @param onFileSelected - Callback que recibe el File CSV seleccionado y válido.
 */
export const CsvUploader: React.FC<CsvUploaderProps> = ({ onFileSelected }) => {
  // ── Estado ──────────────────────────────────────────────────────────────────
  const [uploaderState, setUploaderState] = useState<UploaderState>("idle");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");

  /** Referencia al input[type="file"] oculto. */
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Handlers ────────────────────────────────────────────────────────────────

  /**
   * Procesa un archivo recibido, ya sea por drag & drop o por el input nativo.
   * Valida formato y actualiza el estado visual en consecuencia.
   *
   * Args:
   *   file: Archivo recibido del evento del DOM.
   */
  const handleFile = useCallback(
    async (file: File): Promise<void> => {
      const validationError = validateCsvFile(file);

      if (validationError !== null) {
        setUploaderState("error");
        setErrorMessage(validationError);
        setSelectedFile(null);
        return;
      }

      const headers = await parseCsvHeaders(file);

      setUploaderState("selected");
      setErrorMessage("");
      setSelectedFile(file);
      onFileSelected(file, headers);
    },
    [onFileSelected]
  );

  /**
   * Reinicia el componente a su estado inicial (idle).
   */
  const handleReset = useCallback((): void => {
    setUploaderState("idle");
    setSelectedFile(null);
    setErrorMessage("");

    // Limpiar el input nativo para permitir reseleccionar el mismo archivo.
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  /**
   * Abre el explorador de archivos del sistema operativo.
   */
  const handleOpenFilePicker = useCallback((): void => {
    fileInputRef.current?.click();
  }, []);

  // ── Handlers de drag & drop ─────────────────────────────────────────────────

  const handleDragOver = useCallback(
    (event: React.DragEvent<HTMLElement>): void => {
      event.preventDefault();
      event.stopPropagation();
      if (uploaderState !== "selected") {
        setUploaderState("dragover");
      }
    },
    [uploaderState]
  );

  const handleDragLeave = useCallback(
    (event: React.DragEvent<HTMLElement>): void => {
      event.preventDefault();
      event.stopPropagation();
      if (uploaderState === "dragover") {
        setUploaderState("idle");
      }
    },
    [uploaderState]
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLElement>): void => {
      event.preventDefault();
      event.stopPropagation();

      const files = event.dataTransfer.files;
      if (files.length === 0) return;

      // Solo se procesa el primer archivo en caso de drop múltiple.
      handleFile(files[0]);
    },
    [handleFile]
  );

  // ── Handler del input nativo ─────────────────────────────────────────────────

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const files = event.target.files;
      if (!files || files.length === 0) return;
      handleFile(files[0]);
    },
    [handleFile]
  );

  // ── Clases Tailwind según estado ─────────────────────────────────────────────

  const dropZoneBaseClasses =
    "relative flex flex-col items-center justify-center w-full min-h-40 sm:min-h-48 " +
    "rounded-xl border-2 border-dashed transition-colors duration-200 " +
    "cursor-pointer select-none focus-visible:outline-none focus-visible:ring-2 " +
    "focus-visible:ring-offset-2 focus-visible:ring-blue-500";

  const dropZoneStateClasses: Record<UploaderState, string> = {
    idle:
      "border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50 " +
      "text-gray-500",
    dragover:
      "border-blue-500 bg-blue-50 text-blue-700 scale-[1.01]",
    selected:
      "border-green-400 bg-green-50 text-green-700 cursor-default",
    error:
      "border-red-400 bg-red-50 text-red-700",
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <section aria-label="Carga de archivo CSV" className="w-full">
      {/* Input oculto — solo accesible programáticamente */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,text/csv,text/plain,application/csv"
        aria-hidden="true"
        tabIndex={-1}
        className="sr-only"
        onChange={handleInputChange}
      />

      {/* Zona de drop */}
      <div
        role="button"
        tabIndex={uploaderState === "selected" ? -1 : 0}
        aria-label={
          uploaderState === "selected"
            ? `Archivo seleccionado: ${selectedFile?.name}`
            : "Haz clic o arrastra un archivo CSV aquí"
        }
        className={`${dropZoneBaseClasses} ${dropZoneStateClasses[uploaderState]}`}
        onClick={uploaderState !== "selected" ? handleOpenFilePicker : undefined}
        onKeyDown={(e) => {
          if (
            uploaderState !== "selected" &&
            (e.key === "Enter" || e.key === " ")
          ) {
            e.preventDefault();
            handleOpenFilePicker();
          }
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* ── Estado: idle ── */}
        {uploaderState === "idle" && (
          <div className="flex flex-col items-center gap-3 p-6 text-center">
            <UploadIcon className="w-10 h-10 text-gray-400" />
            <p className="text-sm font-medium text-gray-700">
              Arrastra tu archivo CSV aquí
            </p>
            <p className="text-xs text-gray-400">
              o haz{" "}
              <span className="font-semibold text-blue-500 underline underline-offset-2">
                clic para seleccionar
              </span>
            </p>
            <p className="text-xs text-gray-400">Solo archivos .csv</p>
          </div>
        )}

        {/* ── Estado: dragover ── */}
        {uploaderState === "dragover" && (
          <div className="flex flex-col items-center gap-3 p-6 text-center pointer-events-none">
            <UploadIcon className="w-12 h-12 text-blue-500 animate-bounce" />
            <p className="text-sm font-semibold text-blue-700">
              Suelta el archivo aquí
            </p>
          </div>
        )}

        {/* ── Estado: selected ── */}
        {uploaderState === "selected" && selectedFile !== null && (
          <div className="flex flex-col items-center gap-3 p-6 text-center w-full">
            <CheckCircleIcon className="w-10 h-10 text-green-500" />
            <div className="flex flex-col gap-1">
              <p
                className="text-sm font-semibold text-green-800 break-all max-w-xs sm:max-w-sm"
                title={selectedFile.name}
              >
                {selectedFile.name}
              </p>
              <p className="text-xs text-green-600">
                {formatFileSize(selectedFile.size)}
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleReset();
              }}
              className={
                "mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md " +
                "text-xs font-medium text-green-700 bg-white border border-green-300 " +
                "hover:bg-green-100 transition-colors duration-150 " +
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-500"
              }
              aria-label="Eliminar el archivo seleccionado y volver a elegir"
            >
              <RefreshIcon className="w-3.5 h-3.5" />
              Cambiar archivo
            </button>
          </div>
        )}

        {/* ── Estado: error ── */}
        {uploaderState === "error" && (
          <div className="flex flex-col items-center gap-3 p-6 text-center w-full">
            <ErrorIcon className="w-10 h-10 text-red-500" />
            <p
              role="alert"
              aria-live="assertive"
              className="text-sm font-medium text-red-700 max-w-xs sm:max-w-sm"
            >
              {errorMessage}
            </p>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleReset();
              }}
              className={
                "mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md " +
                "text-xs font-medium text-red-700 bg-white border border-red-300 " +
                "hover:bg-red-100 transition-colors duration-150 " +
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
              }
              aria-label="Intentar de nuevo con otro archivo"
            >
              <RefreshIcon className="w-3.5 h-3.5" />
              Intentar de nuevo
            </button>
          </div>
        )}
      </div>
    </section>
  );
};

// ─── Iconos SVG inline ────────────────────────────────────────────────────────
// Se usan SVGs inline para no añadir dependencias externas (ej. heroicons npm).

interface IconProps {
  className?: string;
}

const UploadIcon: React.FC<IconProps> = ({ className }) => (
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
      d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
    />
  </svg>
);

const CheckCircleIcon: React.FC<IconProps> = ({ className }) => (
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
      d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
    />
  </svg>
);

const ErrorIcon: React.FC<IconProps> = ({ className }) => (
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
      d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
    />
  </svg>
);

const RefreshIcon: React.FC<IconProps> = ({ className }) => (
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
      d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
    />
  </svg>
);
