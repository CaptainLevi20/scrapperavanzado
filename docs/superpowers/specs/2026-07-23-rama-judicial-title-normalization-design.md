# Normalización de títulos — Rama Judicial (tribunales superiores) — Diseño

Fecha: 2026-07-23

## Contexto y objetivo

Al pilotear el scraper de `rama_judicial` contra el sitio real (Tribunal Superior de Bogotá, junio 2026), se encontró que la mayoría de los documentos (723 de 949, 76%) llegan con un `title` derivado directamente del nombre de archivo crudo que sube cada despacho, con formato heterogéneo y poco legible, por ejemplo:

```
11001310302020220015001_DraGonzalezAutoAdmiteRecurso
```

Este diseño agrega una regla de normalización: cuando el nombre de archivo empieza con el radicado judicial completo (23 dígitos) seguido de `_`, el `title` final se reemplaza por un identificador estandarizado — mismo formato para los 33 tribunales superiores, solo cambia el código del tribunal.

Explícitamente en alcance:
- Los 33 `Source` de tipo tribunal superior (tienen `dept_code` en `family_params`, ver `core/seed.py`).
- Solo quiere el radicado — el resto del nombre original (juez, acción) **se descarta**, no se guarda en ningún campo.

Explícitamente fuera de alcance:
- Los 6 `Source` de tipo Juzgado (`JUZGADOS_ENTIDADES`) — no tienen `dept_code`, no hay código de tribunal que anteponer, sus títulos no cambian.
- Los títulos que no empiezan con exactamente 23 dígitos + `_` (nombres de persona tipo `033-2025-00417-01 PAOLA ANDREA NARANJO QUINTANA`, o avisos genéricos tipo `ESTADO E-0109 DEL 26 DE JUNIO DE 2026`) — quedan exactamente como llegan hoy, sin normalizar.

## Formato del título normalizado

```
T_{CODIGO}_{radicado segmentado con "_"}
```

- `T_`: fijo, indica "Tribunal".
- `{CODIGO}`: código de 3-4 letras del tribunal (tabla completa abajo), según el `dept_code` de la fuente.
- El radicado (23 dígitos) se segmenta igual que `_format_radicado` en `core/scrapers/families/cndj.py`, pero con `_` en vez de `-`: `n[0:5]_n[5:7]_n[7:9]_n[9:12]_n[12:16]_n[16:21]_n[21:23]`.

Ejemplo real (Tribunal Superior de Bogotá, radicado `11001310302020220015001`):

```
T_BTA_11001_31_03_020_2022_00150_01
```

## Condición de disparo

El nombre de archivo crudo (`name_no_ext`, ya sin extensión) debe empezar con **exactamente 23 dígitos seguidos de `_`** (regex `^\d{23}_`). Esta condición se verificó contra los datos reales del piloto: 726 de 949 títulos calzan con este patrón — de esos, 723 además tienen "Dr"/"Dra" después, pero 3 no (typos de la fuente: un espacio extra antes de "Dr", o falta "Dr" por completo). Por eso la condición de disparo es solo el prefijo de 23 dígitos, **no** depender de que aparezca "Dr"/"Dra" — ya vimos que eso no es 100% confiable en los datos reales.

Si el nombre de archivo no calza con este patrón (longitud de dígitos distinta de 23, o no hay `_` después), el `title` se deja exactamente como hoy (el nombre de archivo original sin extensión) — no se intenta adivinar ni forzar el formato.

## Tabla de códigos por tribunal (33)

| dept_code | Tribunal | Código |
|---|---|---|
| 05 | Antioquia | ANTI |
| 08 | Atlántico | ATLA |
| 11 | Bogotá | BTA |
| 13 | Bolívar | BOLI |
| 15 | Boyacá | BOYA |
| 17 | Caldas | CALD |
| 18 | Caquetá | CAQU |
| 19 | Cauca | CAUC |
| 20 | Cesar | CESA |
| 23 | Córdoba | CORD |
| 25 | Cundinamarca | CUND |
| 27 | Chocó | CHOC |
| 41 | Huila | HUIL |
| 44 | La Guajira | GUAJ |
| 47 | Magdalena | MAGD |
| 50 | Meta | META |
| 52 | Nariño | NARI |
| 54 | Norte de Santander | NSAN |
| 63 | Quindío | QUIN |
| 66 | Risaralda | RISA |
| 68 | Santander | SANT |
| 70 | Sucre | SUCR |
| 73 | Tolima | TOLI |
| 76 | Valle del Cauca | VALL |
| 81 | Arauca | ARAU |
| 85 | Casanare | CASA |
| 86 | Putumayo | PUTU |
| 88 | San Andrés | SAND |
| 91 | Amazonas | AMAZ |
| 94 | Guainía | GUAI |
| 95 | Guaviare | GUAV |
| 97 | Vaupés | VAUP |
| 99 | Vichada | VICH |

Dictada directamente por el usuario, entidad por entidad — no derivada automáticamente del nombre.

## Backend

### `core/scrapers/families/rama_judicial.py`

- Nuevo diccionario `TRIBUNAL_CODES: dict[str, str]` (dept_code → código), junto a `SUPERIORES_DEPTS`/`JUZGADOS_ENTIDADES`.
- Nueva función `_normalize_title(name_no_ext: str, dept_code: str) -> str`:
  - Si `dept_code` no está en `TRIBUNAL_CODES` (fuente sin código, ej. Juzgados) → devuelve `name_no_ext` sin cambios.
  - Si `name_no_ext` no calza con `^\d{23}_` → devuelve `name_no_ext` sin cambios.
  - Si calza → devuelve `f"T_{TRIBUNAL_CODES[dept_code]}_{n[0:5]}_{n[5:7]}_{n[7:9]}_{n[9:12]}_{n[12:16]}_{n[16:21]}_{n[21:23]}"` donde `n` son los primeros 23 dígitos.
- En `scrap()`, donde hoy se arma `title=name_no_ext` en el `RawDocModel`, se reemplaza por `title=_normalize_title(name_no_ext, self._dept_code)`.
- `save_path` sigue usando `doc_name` (el nombre sanitizado para ruta) como hoy — este cambio es solo sobre el campo `title`/metadato, no sobre la ruta de almacenamiento.

## Testing

- `tests/families/test_rama_judicial.py`:
  - `_normalize_title` (o el comportamiento de `scrap()` end-to-end): un radicado de 23 dígitos con código de tribunal conocido produce `T_{CODIGO}_{segmentado}`.
  - Un `name_no_ext` que no empieza con 23 dígitos (nombre de persona, aviso "ESTADO...") no se modifica.
  - Un `dept_code` sin código en la tabla (ej. Juzgado, `dept_code=""`) no se modifica el título aunque el nombre sí tenga 23 dígitos al inicio.
  - Los 3 casos reales con typo (espacio extra antes de "Dr", o sin "Dr") también se normalizan correctamente — la condición de disparo no depende de "Dr"/"Dra".
  - `TRIBUNAL_CODES` tiene exactamente 33 entradas, una por cada `dept_code` de `SUPERIORES_DEPTS`.
