"""
Tests unitarios para el retry parcial: pipeline de scraping y tarea Celery retry_job.

Verifica que:
  - El pipeline registra correctamente los productos fallidos en el resumen
  - retry_job filtra los productos según los flags de RetryJobRequest
  - retry_job incrementa el contador de reintentos en JobStatus
  - retry_job actualiza la lista de failed_products tras el procesamiento
  - retry_job limpia la lista cuando todos los productos se recuperan
  - retry_job no reprocesa productos que ya tuvieron éxito

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from api.v1.schemas.job import EstadoJob, JobStatus, RetryJobRequest, SearchConfig, TipoJob


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_job_status(
    job_id: str | None = None,
    estado: EstadoJob = EstadoJob.COMPLETADO,
    imagenes_descargadas: int = 10,
    imagenes_fallidas: int = 3,
    total_productos: int = 13,
    reintentos: int = 0,
    productos_fallidos: list[str] | None = None,
) -> JobStatus:
    """
    Construye un JobStatus de prueba.

    Args:
        job_id:               UUID como string. Si None, genera uno nuevo.
        estado:               estado del job.
        imagenes_descargadas: contador de imágenes descargadas exitosamente.
        imagenes_fallidas:    contador de imágenes fallidas.
        total_productos:      total de productos del CSV.
        reintentos:           número de reintentos ya realizados.
        productos_fallidos:   lista de códigos fallidos.

    Returns:
        Instancia de JobStatus con los valores proporcionados.
    """
    return JobStatus(
        job_id=uuid.UUID(job_id or str(uuid.uuid4())),
        estado=estado,
        imagenes_descargadas=imagenes_descargadas,
        imagenes_fallidas=imagenes_fallidas,
        total_productos=total_productos,
        reintentos=reintentos,
        productos_fallidos=productos_fallidos or [],
        mensaje="Estado de prueba.",
    )


def _make_failed_products(
    codigos: list[str],
    razon: str = "imagen",
) -> list[dict]:
    """
    Construye una lista de productos fallidos con el formato de Redis.

    Args:
        codigos: lista de códigos de producto.
        razon:   razón del fallo ('imagen', 'marca', 'descripcion', 'seo').

    Returns:
        Lista de dicts con campos 'codigo', 'nombre' y 'razon'.
    """
    return [{"codigo": c, "nombre": f"Producto {c}", "razon": razon} for c in codigos]


# ── Tests del pipeline ────────────────────────────────────────────────────────


class TestScrapingPipelineFailedProducts:
    """
    Tests sobre el seguimiento de productos fallidos en ScrapingPipeline.

    :author: BenjaminDTS
    """

    def test_pipeline_includes_failed_products_in_resumen(self) -> None:
        """Verifica que el resumen del pipeline incluye '_productos_fallidos'."""
        from services.scraper.pipeline import ScrapingPipeline

        config = SearchConfig(tipo_job=TipoJob.FOTOS)
        pipeline = ScrapingPipeline(job_id="test-job", config=config)

        csv_content = "codigo,nombre,marca,ean\nABC,Producto A,MarcaX,1234567890123"

        # Simular producer lanzando excepción (producto fallido)
        with (
            patch("services.scraper.pipeline.CsvParser") as mock_parser,
            patch("services.scraper.pipeline.buscar_urls_imagenes", side_effect=RuntimeError("Sin URLs")),
            patch("services.scraper.pipeline.get_storage_service") as mock_storage,
        ):
            from services.csv_parser import Producto, ResultadoParseo

            mock_producto = Producto(codigo="ABC", nombre="Producto A", marca="MarcaX")
            mock_parser.return_value.parsear.return_value = ResultadoParseo(
                productos=[mock_producto], errores=[]
            )
            mock_storage.return_value.create_zip.return_value = "/tmp/test.zip"

            resumen = pipeline.ejecutar(contenido_csv=csv_content)

        assert "_productos_fallidos" in resumen

    def test_failed_products_list_has_required_fields(self) -> None:
        """Verifica que cada entrada de _productos_fallidos tiene 'codigo', 'nombre' y 'razon'."""
        from services.scraper.pipeline import ScrapingPipeline

        config = SearchConfig(tipo_job=TipoJob.FOTOS)
        pipeline = ScrapingPipeline(job_id="test-job", config=config)

        csv_content = "codigo,nombre,marca,ean\nABC,Producto A,MarcaX,1234567890123"

        with (
            patch("services.scraper.pipeline.CsvParser") as mock_parser,
            patch("services.scraper.pipeline.buscar_urls_imagenes", side_effect=RuntimeError("Error")),
            patch("services.scraper.pipeline.get_storage_service") as mock_storage,
        ):
            from services.csv_parser import Producto, ResultadoParseo

            mock_producto = Producto(codigo="ABC", nombre="Producto A", marca="MarcaX")
            mock_parser.return_value.parsear.return_value = ResultadoParseo(
                productos=[mock_producto], errores=[]
            )
            mock_storage.return_value.create_zip.return_value = "/tmp/test.zip"

            resumen = pipeline.ejecutar(contenido_csv=csv_content)

        fallidos = resumen["_productos_fallidos"]
        assert len(fallidos) == 1
        assert fallidos[0]["codigo"] == "ABC"
        assert fallidos[0]["nombre"] == "Producto A"
        assert fallidos[0]["razon"] == "imagen"

    def test_successful_products_not_in_failed_list(self) -> None:
        """Verifica que los productos con imágenes descargadas no aparecen en _productos_fallidos."""
        from services.scraper.pipeline import ScrapingPipeline

        config = SearchConfig(tipo_job=TipoJob.FOTOS)
        pipeline = ScrapingPipeline(job_id="test-job", config=config)

        csv_content = "codigo,nombre,marca,ean\nABC,Producto A,MarcaX,1234567890123"

        with (
            patch("services.scraper.pipeline.CsvParser") as mock_parser,
            patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://img.example.com/1.jpg"]),
            patch("services.scraper.pipeline.descargar_imagenes_producto") as mock_consumer,
            patch("services.scraper.pipeline.get_storage_service") as mock_storage,
        ):
            from services.csv_parser import Producto, ResultadoParseo

            mock_producto = Producto(codigo="ABC", nombre="Producto A", marca="MarcaX")
            mock_parser.return_value.parsear.return_value = ResultadoParseo(
                productos=[mock_producto], errores=[]
            )
            # Simular descarga exitosa
            mock_result = MagicMock()
            mock_result.exitoso = True
            mock_consumer.return_value = [mock_result]
            mock_storage.return_value.create_zip.return_value = "/tmp/test.zip"

            resumen = pipeline.ejecutar(contenido_csv=csv_content)

        assert resumen["_productos_fallidos"] == []

    def test_codigos_filtro_processes_only_matching_products(self) -> None:
        """Verifica que codigos_filtro limita los productos procesados."""
        from services.scraper.pipeline import ScrapingPipeline

        config = SearchConfig(tipo_job=TipoJob.FOTOS)
        pipeline = ScrapingPipeline(job_id="test-job", config=config)

        csv_content = (
            "codigo,nombre,marca,ean\n"
            "AAA,Producto A,MarcaX,1111111111111\n"
            "BBB,Producto B,MarcaY,2222222222222\n"
            "CCC,Producto C,MarcaZ,3333333333333"
        )

        procesados: list[str] = []

        with (
            patch("services.scraper.pipeline.CsvParser") as mock_parser,
            patch("services.scraper.pipeline.buscar_urls_imagenes") as mock_producer,
            patch("services.scraper.pipeline.descargar_imagenes_producto") as mock_consumer,
            patch("services.scraper.pipeline.get_storage_service") as mock_storage,
        ):
            from services.csv_parser import Producto, ResultadoParseo

            productos = [
                Producto(codigo="AAA", nombre="Producto A"),
                Producto(codigo="BBB", nombre="Producto B"),
                Producto(codigo="CCC", nombre="Producto C"),
            ]
            mock_parser.return_value.parsear.return_value = ResultadoParseo(
                productos=productos, errores=[]
            )

            def capture_producer(producto, cantidad):  # noqa: ANN001
                procesados.append(producto.codigo)
                return ["http://img.example.com/1.jpg"]

            mock_producer.side_effect = capture_producer
            mock_result = MagicMock()
            mock_result.exitoso = True
            mock_consumer.return_value = [mock_result]
            mock_storage.return_value.create_zip.return_value = "/tmp/test.zip"

            pipeline.ejecutar(
                contenido_csv=csv_content,
                codigos_filtro={"AAA", "CCC"},
            )

        assert set(procesados) == {"AAA", "CCC"}
        assert "BBB" not in procesados


# ── Tests de retry_job ────────────────────────────────────────────────────────


class TestRetryJobTask:
    """
    Tests unitarios para la tarea Celery retry_job.

    Mockea Redis y el pipeline completamente para aislar la lógica de la tarea.

    :author: BenjaminDTS
    """

    def _setup_redis_mock(
        self,
        job_id: str,
        job_status: JobStatus,
        failed_products: list[dict],
        csv_content: str = "codigo,nombre,marca,ean\nABC,Prod A,MarcaX,1111111111111",
        config_dict: dict | None = None,
    ) -> MagicMock:
        """
        Configura un mock de Redis con los datos necesarios para retry_job.

        Args:
            job_id:          ID del job.
            job_status:      JobStatus a devolver para la clave job:{job_id}.
            failed_products: lista de failed_products a devolver.
            csv_content:     contenido CSV a devolver para la clave csv.
            config_dict:     config SearchConfig a devolver; si None usa defaults.

        Returns:
            MagicMock configurado como cliente Redis síncrono.
        """
        config_dict = config_dict or SearchConfig().model_dump()
        mock_redis = MagicMock()
        mock_redis.close = MagicMock()

        def get_side_effect(key: str) -> str | None:
            if key == f"job:{job_id}":
                return job_status.model_dump_json()
            if key == f"job:{job_id}:failed_products":
                return json.dumps(failed_products)
            if key == f"job:{job_id}:csv":
                return csv_content
            if key == f"job:{job_id}:config":
                return json.dumps(config_dict)
            return None

        mock_redis.get.side_effect = get_side_effect
        mock_redis.set = MagicMock()
        mock_redis.delete = MagicMock()
        return mock_redis

    def test_retry_job_filters_products_by_retry_config_images(self) -> None:
        """Verifica que retry_job procesa solo los productos con razon='imagen' cuando retry_images=True."""
        from workers.tasks import retry_job

        job_id = str(uuid.uuid4())
        status = _make_job_status(job_id, imagenes_fallidas=2)
        failed_products = _make_failed_products(["AAA", "BBB"], razon="imagen")

        mock_redis = self._setup_redis_mock(job_id, status, failed_products)

        with (
            patch("workers.tasks._get_redis_client", return_value=mock_redis),
            patch("workers.tasks.ScrapingPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.ejecutar.return_value = {
                "imagenes_descargadas": 2,
                "imagenes_fallidas": 0,
                "_productos_fallidos": [],
                "total_productos": 2,
            }
            mock_pipeline_cls.return_value = mock_pipeline

            retry_config = RetryJobRequest(retry_images=True, retry_brands=False, retry_descriptions=False, retry_seo=False)
            result = retry_job(job_id, retry_config.model_dump())

        assert result["productos_reintentados"] == 2
        call_kwargs = mock_pipeline.ejecutar.call_args
        assert call_kwargs is not None
        codigos = call_kwargs.kwargs.get("codigos_filtro") or call_kwargs.args[0] if call_kwargs.args else None
        # Verificar que se pasó codigos_filtro con los dos productos
        filtro = mock_pipeline.ejecutar.call_args.kwargs.get("codigos_filtro", set())
        assert "AAA" in filtro
        assert "BBB" in filtro

    def test_retry_job_skips_products_with_non_matching_razon(self) -> None:
        """Verifica que productos con razon='marca' se omiten si retry_brands=False."""
        from workers.tasks import retry_job

        job_id = str(uuid.uuid4())
        status = _make_job_status(job_id, imagenes_fallidas=0)
        failed_products = _make_failed_products(["AAA"], razon="marca")

        mock_redis = self._setup_redis_mock(job_id, status, failed_products)

        with (
            patch("workers.tasks._get_redis_client", return_value=mock_redis),
            patch("workers.tasks.ScrapingPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline_cls.return_value = mock_pipeline

            retry_config = RetryJobRequest(retry_images=True, retry_brands=False, retry_descriptions=False, retry_seo=False)
            result = retry_job(job_id, retry_config.model_dump())

        assert result["productos_reintentados"] == 0
        mock_pipeline.ejecutar.assert_not_called()

    def test_retry_job_increments_reintentos_counter(self) -> None:
        """Verifica que retry_job incrementa el campo reintentos del JobStatus."""
        from workers.tasks import retry_job

        job_id = str(uuid.uuid4())
        status = _make_job_status(job_id, reintentos=1)
        failed_products = _make_failed_products(["AAA"])

        mock_redis = self._setup_redis_mock(job_id, status, failed_products)

        calls_to_set: list[tuple] = []
        mock_redis.set = MagicMock(side_effect=lambda key, value, **kw: calls_to_set.append((key, value)))

        with (
            patch("workers.tasks._get_redis_client", return_value=mock_redis),
            patch("workers.tasks.ScrapingPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.ejecutar.return_value = {
                "imagenes_descargadas": 1,
                "imagenes_fallidas": 0,
                "_productos_fallidos": [],
                "total_productos": 1,
            }
            mock_pipeline_cls.return_value = mock_pipeline

            retry_config = RetryJobRequest(retry_images=True)
            retry_job(job_id, retry_config.model_dump())

        # El JobStatus guardado debe tener reintentos=2 (era 1, incrementado a 2)
        job_key = f"job:{job_id}"
        saved_jsons = [v for k, v in calls_to_set if k == job_key]
        assert saved_jsons, "JobStatus no fue persistido en Redis"

        # El último estado guardado debe tener reintentos >= 2
        last_status = JobStatus.model_validate_json(saved_jsons[-1])
        assert last_status.reintentos == 2

    def test_retry_job_updates_failed_products_after_processing(self) -> None:
        """Verifica que la lista de failed_products en Redis se actualiza tras el retry."""
        from workers.tasks import retry_job

        job_id = str(uuid.uuid4())
        status = _make_job_status(job_id, imagenes_fallidas=2)
        # 2 productos fallidos; uno se recupera, el otro sigue fallando
        failed_products = _make_failed_products(["AAA", "BBB"])

        mock_redis = self._setup_redis_mock(job_id, status, failed_products)

        with (
            patch("workers.tasks._get_redis_client", return_value=mock_redis),
            patch("workers.tasks.ScrapingPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            # BBB sigue fallando en el retry
            mock_pipeline.ejecutar.return_value = {
                "imagenes_descargadas": 1,
                "imagenes_fallidas": 1,
                "_productos_fallidos": [{"codigo": "BBB", "nombre": "Producto BBB", "razon": "imagen"}],
                "total_productos": 2,
            }
            mock_pipeline_cls.return_value = mock_pipeline

            retry_config = RetryJobRequest(retry_images=True)
            retry_job(job_id, retry_config.model_dump())

        # Verificar que se escribió la nueva lista de fallidos (solo BBB)
        set_calls = mock_redis.set.call_args_list
        failed_key = f"job:{job_id}:failed_products"
        failed_writes = [c for c in set_calls if c.args[0] == failed_key]
        assert failed_writes, "La lista de failed_products no fue actualizada en Redis"

        last_value = json.loads(failed_writes[-1].args[1])
        codigos_restantes = [fp["codigo"] for fp in last_value]
        assert "BBB" in codigos_restantes
        assert "AAA" not in codigos_restantes

    def test_retry_job_clears_failed_products_when_all_succeed(self) -> None:
        """Verifica que la clave failed_products se elimina de Redis cuando todos se recuperan."""
        from workers.tasks import retry_job

        job_id = str(uuid.uuid4())
        status = _make_job_status(job_id, imagenes_fallidas=2)
        failed_products = _make_failed_products(["AAA", "BBB"])

        mock_redis = self._setup_redis_mock(job_id, status, failed_products)

        with (
            patch("workers.tasks._get_redis_client", return_value=mock_redis),
            patch("workers.tasks.ScrapingPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            # Todos se recuperan
            mock_pipeline.ejecutar.return_value = {
                "imagenes_descargadas": 2,
                "imagenes_fallidas": 0,
                "_productos_fallidos": [],
                "total_productos": 2,
            }
            mock_pipeline_cls.return_value = mock_pipeline

            retry_config = RetryJobRequest(retry_images=True)
            retry_job(job_id, retry_config.model_dump())

        failed_key = f"job:{job_id}:failed_products"
        mock_redis.delete.assert_called_with(failed_key)

    def test_retry_job_does_not_reprocess_successful_products(self) -> None:
        """Verifica que los productos exitosos del job original no se incluyen en el retry."""
        from workers.tasks import retry_job

        job_id = str(uuid.uuid4())
        # 10 ok + 2 fallidos = 12 total
        csv_content = (
            "codigo,nombre,marca,ean\n"
            + "\n".join(f"P{i:02d},Prod {i},Marca,{i:013d}" for i in range(12))
        )
        status = _make_job_status(
            job_id,
            imagenes_descargadas=10,
            imagenes_fallidas=2,
            total_productos=12,
        )
        # Solo 2 productos fallidos
        failed_products = _make_failed_products(["P10", "P11"])

        mock_redis = self._setup_redis_mock(job_id, status, failed_products, csv_content=csv_content)

        with (
            patch("workers.tasks._get_redis_client", return_value=mock_redis),
            patch("workers.tasks.ScrapingPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.ejecutar.return_value = {
                "imagenes_descargadas": 2,
                "imagenes_fallidas": 0,
                "_productos_fallidos": [],
                "total_productos": 2,
            }
            mock_pipeline_cls.return_value = mock_pipeline

            retry_config = RetryJobRequest(retry_images=True)
            retry_job(job_id, retry_config.model_dump())

        filtro = mock_pipeline.ejecutar.call_args.kwargs.get("codigos_filtro", set())
        # Solo P10 y P11 deben estar en el filtro — los otros 10 no
        assert filtro == {"P10", "P11"}
        for i in range(10):
            assert f"P{i:02d}" not in filtro
