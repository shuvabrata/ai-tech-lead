"""Load and validate YAML query catalog definitions."""

from pathlib import Path
import re
from typing import Any

import yaml

from app.api.graph.v1.query import validate_read_only_query

from .model import CatalogNamespace, CatalogParameter, CatalogQuery, CatalogView

_SAFE_ID_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class CatalogLoadError(ValueError):
    """Raised when the query catalog cannot be loaded or validated."""


def get_default_catalog_dir() -> Path:
    """Return the default query catalog directory for local and Docker runs."""
    candidates = [
        Path.cwd() / "queries_catalog",
        Path(__file__).resolve().parents[2] / "queries_catalog",
        Path(__file__).resolve().parents[3] / "queries_catalog",
    ]

    for candidate in candidates:
        if (candidate / "catalog.yaml").exists():
            return candidate

    return candidates[0]


def load_namespaces(catalog_dir: str | Path | None = None) -> list[CatalogNamespace]:
    """Load namespace metadata from the master catalog file."""
    base_dir = (Path(catalog_dir) if catalog_dir is not None else get_default_catalog_dir()).resolve()
    catalog_file = base_dir / "catalog.yaml"
    data = _load_yaml_mapping(catalog_file)
    raw_namespaces = data.get("namespaces")

    if not isinstance(raw_namespaces, list) or not raw_namespaces:
        raise CatalogLoadError(f"{catalog_file} must define a non-empty namespaces list")

    namespaces: list[CatalogNamespace] = []
    seen_directories: set[str] = set()
    for order, raw_namespace in enumerate(raw_namespaces):
        if not isinstance(raw_namespace, dict):
            raise CatalogLoadError(f"{catalog_file} namespace at index {order} must be a mapping")

        try:
            namespace = CatalogNamespace(**raw_namespace, order=order)
        except ValueError as exc:
            raise CatalogLoadError(f"Invalid namespace at index {order}: {exc}") from exc

        if namespace.directory in seen_directories:
            raise CatalogLoadError(f"Duplicate namespace directory: {namespace.directory}")

        seen_directories.add(namespace.directory)
        namespaces.append(namespace)

    return namespaces


def load_catalog(
    catalog_dir: str | Path | None = None,
    *,
    validate_cypher: bool = True,
) -> list[CatalogQuery]:
    """Load all catalog query YAML files as normalized query definitions."""
    base_dir = (Path(catalog_dir) if catalog_dir is not None else get_default_catalog_dir()).resolve()
    namespaces = load_namespaces(base_dir)
    queries: list[CatalogQuery] = []
    seen_ids: set[str] = set()

    for namespace in namespaces:
        namespace_dir = base_dir / namespace.directory
        if not namespace_dir.is_dir():
            raise CatalogLoadError(f"Namespace directory does not exist: {namespace_dir}")

        for query_file in sorted(namespace_dir.glob("*.yaml")):
            query = _load_query_file(
                query_file=query_file,
                namespace=namespace,
                base_dir=base_dir,
                validate_cypher=validate_cypher,
            )

            if query.id in seen_ids:
                raise CatalogLoadError(f"Duplicate catalog query id: {query.id}")

            seen_ids.add(query.id)
            queries.append(query)

    return sorted(queries, key=lambda query: (query.namespace.order, query.name.lower()))


def get_catalog_query(
    catalog_id: str,
    catalog_dir: str | Path | None = None,
    *,
    validate_cypher: bool = True,
) -> CatalogQuery:
    """Return one catalog query by stable id."""
    for query in load_catalog(catalog_dir, validate_cypher=validate_cypher):
        if query.id == catalog_id:
            return query

    raise CatalogLoadError(f"Catalog query not found: {catalog_id}")


def _load_query_file(
    *,
    query_file: Path,
    namespace: CatalogNamespace,
    base_dir: Path,
    validate_cypher: bool,
) -> CatalogQuery:
    raw_query = _load_yaml_mapping(query_file)
    raw_queries = raw_query.get("queries")
    if not isinstance(raw_queries, dict):
        raise CatalogLoadError(f"{query_file} must define a queries mapping")

    queries: dict[CatalogView, str] = {}
    for view in ("tabular", "graph"):
        query_text = raw_queries.get(view)
        if query_text is None:
            continue
        if not isinstance(query_text, str) or not query_text.strip():
            raise CatalogLoadError(f"{query_file} has an empty {view} query")
        if validate_cypher and not validate_read_only_query(query_text):
            raise CatalogLoadError(f"{query_file} has a non-read-only {view} query")
        queries[view] = query_text

    slug = query_file.stem
    if not _SAFE_ID_SEGMENT.fullmatch(slug):
        raise CatalogLoadError(f"{query_file} filename must be a path-safe slug")

    catalog_id = f"{namespace.directory}/{slug}"
    parameters = [
        _build_parameter(raw_parameter, query_file)
        for raw_parameter in raw_query.get("parameters", []) or []
    ]
    tags = raw_query.get("tags", []) or []

    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise CatalogLoadError(f"{query_file} tags must be a list of strings")

    try:
        return CatalogQuery(
            id=catalog_id,
            slug=slug,
            namespace=namespace,
            name=raw_query.get("name"),
            description=raw_query.get("description"),
            queries=queries,
            available_views=list(queries.keys()),
            parameters=parameters,
            tags=tags,
            source_path=str(query_file.relative_to(base_dir.parent)),
        )
    except ValueError as exc:
        raise CatalogLoadError(f"Invalid query file {query_file}: {exc}") from exc


def _build_parameter(raw_parameter: Any, query_file: Path) -> CatalogParameter:
    if not isinstance(raw_parameter, dict):
        raise CatalogLoadError(f"{query_file} parameters must be mappings")

    if "required" not in raw_parameter:
        raise CatalogLoadError(f"{query_file} parameter {raw_parameter.get('name')} must define required")

    try:
        return CatalogParameter(**raw_parameter)
    except ValueError as exc:
        raise CatalogLoadError(f"Invalid parameter in {query_file}: {exc}") from exc


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CatalogLoadError(f"Catalog file does not exist: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise CatalogLoadError(f"{path} must contain a YAML mapping")

    return data
