"""
Caché en memoria de prefijos GS1 con aprendizaje automático.

Carga los prefijos desde ``data/gs1_prefixes_seed.json`` al inicializarse (Eager
Loading). Cuando un nivel superior del resolver (APIs, buscadores) identifica
un fabricante nuevo, se puede registrar su prefijo para que futuros EANs del
mismo fabricante se resuelvan directamente desde la caché (Nivel 2).

Relación con el resto del pipeline:
  - ``GS1PrefixCache`` es el Nivel 1 de la cascada EAN → marca.
  - Si ``resolve`` devuelve ``None``, el pipeline debe escalar a
    ``open_data_api`` (Nivel 2) y, si aún falla, a búsqueda web (Nivel 3).
  - Cuando Nivel 2 o Nivel 3 resuelven un EAN con confianza alta, deben llamar
    a ``register`` para que futuras resoluciones del mismo fabricante sean
    instantáneas desde caché.

:author: BenjaminDTS
:version: 1.0.0
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from services.scraper.brand_validator import BrandResult, longest_prefix_match

# ── Ruta por defecto al semillero GS1 ─────────────────────────────────────────
# brand_cache.py está en services/scraper/; el proyecto raíz queda dos niveles
# más arriba. Se calcula en tiempo de importación para que sea independiente del
# directorio de trabajo actual al lanzar el proceso.
_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
_DEFAULT_SEED: Path = _PROJECT_ROOT / "data" / "gs1_prefixes_seed.json"


class GS1PrefixCache:
    """
    Caché en memoria de prefijos GS1 → fabricante/empresa.

    Estrategia de carga:
      - Los prefijos se leen una sola vez desde el JSON semillero al crear la
        instancia (Eager Loading). Esto hace que la primera llamada a
        ``resolve`` sea igual de rápida que todas las siguientes.
      - El diccionario interno ``_prefixes`` indexa ``{prefijo: entrada}``
        donde la entrada es un ``dict`` con las claves ``company_name`` y
        ``country_code``.

    Aprendizaje automático (registro en caliente):
      - El método ``register`` añade nuevos prefijos descubiertos por niveles
        superiores (APIs, búsqueda web) sin reiniciar la caché.
      - Los cambios son solo en memoria; no se persisten al JSON semillero.
        Si se desea persistencia entre ejecuciones, exportar ``_prefixes`` a
        disco desde el worker o la tarea Celery.

    :author: BenjaminDTS
    """

    def __init__(self, seed_path: str | None = None) -> None:
        """
        Inicializa la caché cargando el semillero GS1.

        Args:
            seed_path: ruta absoluta o relativa al archivo JSON semillero.
                Si es ``None``, se usa la ruta por defecto
                ``<project_root>/data/gs1_prefixes_seed.json``.

        Raises:
            No lanza excepciones: si el archivo no existe o tiene JSON
            inválido, se registra un WARNING y la caché arranca vacía.
        """
        ruta: Path = Path(seed_path) if seed_path is not None else _DEFAULT_SEED

        # Diccionario interno: clave = prefijo (str), valor = entrada completa
        self._prefixes: dict[str, dict[str, str]] = {}

        self._cargar_semillero(ruta)
        logger.info(
            "Caché GS1 inicializada",
            extra={"total_prefijos": len(self._prefixes), "seed_path": str(ruta)},
        )

    # ── Carga interna ──────────────────────────────────────────────────────────

    def _cargar_semillero(self, ruta: Path) -> None:
        """
        Lee el JSON semillero y pobla ``_prefixes``.

        El método es tolerante a fallos: registra el error y continúa con
        caché vacía en lugar de propagar la excepción al llamador.

        Args:
            ruta: ruta al archivo ``gs1_prefixes_seed.json``.
        """
        if not ruta.exists():
            logger.warning(
                "Archivo semillero GS1 no encontrado; caché arranca vacía",
                extra={"ruta": str(ruta)},
            )
            return

        try:
            raw: list[dict[str, Any]] = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "No se pudo leer el semillero GS1; caché arranca vacía",
                exc_info=exc,
                extra={"ruta": str(ruta)},
            )
            return

        for entrada in raw:
            prefijo = entrada.get("prefix", "").strip()
            if not prefijo:
                # Saltamos entradas sin prefijo para no contaminar la caché
                continue
            self._prefixes[prefijo] = {
                "company_name": entrada.get("company_name", ""),
                "country_code": entrada.get("country_code", ""),
            }

        logger.debug(
            "Semillero GS1 cargado",
            extra={"entradas_cargadas": len(self._prefixes), "ruta": str(ruta)},
        )

    # ── API pública ────────────────────────────────────────────────────────────

    def resolve(self, ean: str) -> BrandResult | None:
        """
        Intenta resolver un EAN a una entrada de fabricante usando prefijos GS1.

        Delega la búsqueda de prefijo a ``longest_prefix_match`` para garantizar
        que el prefijo más específico (más largo) tiene prioridad sobre uno más
        genérico que también podría coincidir.

        Args:
            ean: código EAN/UPC como string de solo dígitos. No es necesario
                que haya sido validado previamente con ``validate_ean_checksum``;
                si el EAN es demasiado corto no se encontrará coincidencia y
                el método devuelve ``None`` de forma segura.

        Returns:
            Un ``BrandResult`` con ``source="cache_gs1"`` y
            ``confidence="high"`` si se encontró un prefijo coincidente,
            o ``None`` si la caché no puede resolver el EAN.
        """
        # longest_prefix_match recibe un dict[str, str] con el nombre de empresa
        # como valor; construimos esa vista en el momento de la llamada.
        lookup: dict[str, str] = {
            prefijo: datos["company_name"]
            for prefijo, datos in self._prefixes.items()
        }

        company_name: str | None = longest_prefix_match(ean, lookup)

        if company_name is None:
            logger.debug(
                "EAN no resuelto en caché GS1",
                extra={"ean": ean},
            )
            return None

        # Recuperar el country_code de la entrada original para enriquecer el
        # resultado (útil para depuración y futuros filtros por región).
        prefijo_encontrado = next(
            (p for p in self._prefixes if ean.startswith(p) and self._prefixes[p]["company_name"] == company_name),
            None,
        )
        country_code: str = (
            self._prefixes[prefijo_encontrado]["country_code"]
            if prefijo_encontrado
            else ""
        )

        logger.debug(
            "EAN resuelto desde caché GS1",
            extra={"ean": ean, "company_name": company_name, "country_code": country_code},
        )

        return BrandResult(
            ean_code=ean,
            brand_name=company_name,
            manufacturer=company_name,
            source="cache_gs1",
            confidence="high",
        )

    def register(self, prefix: str, company_name: str, country_code: str) -> None:
        """
        Registra un nuevo prefijo GS1 en la caché en memoria.

        El registro es temporal: persiste solo durante la vida del proceso.
        Para hacer los cambios permanentes es necesario actualizar el archivo
        ``gs1_prefixes_seed.json`` manualmente o mediante una tarea de
        mantenimiento separada.

        Args:
            prefix: prefijo GS1 (entre 6 y 10 dígitos) del nuevo fabricante.
            company_name: nombre de la empresa o fabricante asociado al prefijo.
            country_code: código de país ISO 3166-1 alpha-2 (p. ej. ``"ES"``).

        Raises:
            No lanza excepciones. Si el prefijo ya existe, su entrada se
            sobreescribe y se registra un aviso a nivel DEBUG.
        """
        if prefix in self._prefixes:
            logger.debug(
                "Prefijo GS1 ya existente; se sobreescribirá",
                extra={"prefix": prefix, "company_anterior": self._prefixes[prefix]["company_name"]},
            )

        self._prefixes[prefix] = {
            "company_name": company_name,
            "country_code": country_code,
        }

        logger.debug(
            "Prefijo GS1 registrado en caché",
            extra={"prefix": prefix, "company_name": company_name, "country_code": country_code},
        )
