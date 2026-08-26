# Reorganizador de lotes (Laboratorio)

## Problema

El Formateador (`frontend/src/lib/formatter/`) renombra y copia archivos
sueltos dentro de una única carpeta de año. No sirve para el caso real que
motiva esta funcionalidad: lotes de intake ya organizados por
`Tipo → [Entidad] → Año → archivo` (confirmado por el usuario y verificado
contra un lote real de referencia, `D:\LOTE 2`: 53,057 archivos / 169 GB en
24 carpetas de Tipo), donde la inmensa mayoría de los archivos (99.3% en el
lote de referencia) ya está bien ubicada y solo una minoría rompe el patrón
por errores de intake — carpeta de entidad faltante, carpeta de año
faltante, o (más raro) sin forma de resolverse automáticamente.

El Formateador tampoco sirve técnicamente para este volumen: itera con
`showDirectoryPicker()` y `FileSystemDirectoryHandle` en el navegador,
pensado para lotes de un solo nivel. Recorrer 53 mil archivos en 2-3 niveles
así sería lento y fragil en una pestaña de navegador.

## Alcance

Esta es una herramienta de desarrollo interna: el usuario confirmó que solo
el desarrollador la usa, siempre en la máquina donde vive el lote (nunca un
usuario final, ni un servidor remoto separado del disco). Por eso:

- No usa el selector de carpetas del navegador. El admin escribe una ruta de
  disco absoluta (`D:\LOTE 2`) y el **backend** recorre esa ruta
  directamente.
- No hace falta un job en segundo plano (Celery): recorrer el árbol
  completo (solo metadatos de carpetas/archivos, sin abrir contenido) tomó
  ~15s sobre 53 mil archivos en pruebas manuales — un endpoint síncrono
  normal alcanza.
- **Nunca mueve los archivos que ya están bien ubicados.** Solo actúa sobre
  las excepciones detectadas.
- **Fuera de alcance:** fusionar o renombrar carpetas de Tipo a nivel
  superior. Se verificó que `Ccircular` y `CIRCULAR` (que parecían
  duplicados por el nombre) en realidad usan prefijos de archivo distintos
  (`CCIR_` vs `C_`) — son tipos distintos, no una carpeta mal escrita. Decidir
  si dos carpetas de Tipo son la misma cosa requiere criterio de dominio que
  esta herramienta no intenta automatizar.
- **Fuera de alcance:** carpetas con más niveles de los tres esperados (p.
  ej. `Gacetas\GC\1992\AC\...`, `CIRCULAR\PGN\2024\CONCEPTOS\...`) no se
  tocan. Todo indica que son subcategorías intencionales propias de ese
  Tipo, no errores — se reportan como informativas solamente.

## Regla de auditoría

Para cada carpeta de Tipo (nivel 1, tomada tal cual existe en disco):

1. **Clasificar el Tipo.** Se miran sus subcarpetas directas: si son todas
   años (patrón `1[89]\d{2}|20\d{2}`) el Tipo es `sin_entidad` (como
   `Leyes`); si son códigos de entidad, el Tipo es `con_entidad` (como
   `DECRETOS`, `RESOLUCIONES`). La clasificación es por **mayoría estricta**
   de carpetas tipo-entidad sobre carpetas tipo-año — un empate entre ambos
   conteos (siendo los dos mayores a cero) se resuelve a `sin_entidad`, para
   no arriesgar clasificar como `con_entidad` un Tipo que en realidad es
   `sin_entidad` con un par de carpetas sueltas (backups, temporales). La
   única excepción es cuando el Tipo no tiene subcarpetas en absoluto (cero y
   cero): ahí no hay evidencia estructural y se resuelve a `con_entidad`, para
   no arriesgar una `proposed_path` que le falte el segmento de Entidad. Un
   Tipo `con_entidad` puede tener alguna carpeta de año colada entre las de
   entidad, y eso es precisamente una excepción a resolver (ver abajo).
2. **Tipo `con_entidad`:** cada archivo debe vivir en `Entidad/Año/archivo`.
   Cuatro formas de excepción:
   - `missing_entity_folder`: el archivo está en `Tipo/Año/archivo` (la
     carpeta de año cuelga directo del Tipo). Ej.:
     `DECRETOS\2022\D_MSPS_0017AJ_2022.pdf`.
   - `missing_year_folder`: el archivo está en `Tipo/Entidad/archivo` (sin
     carpeta de año). Ej.: `RESOLUCIONES\SGCANDINA\RSG2058.docx`.
   - `entity_mismatch`: el archivo ya está en `Tipo/Entidad/Año/archivo`
     (forma completa), pero la Entidad del nombre del archivo no coincide
     con la carpeta de Entidad donde vive — típicamente porque esa carpeta
     es en realidad un cajón de miscelánea (ej. `ACUERDOS\ARCHIVO\2003\
     A_AGN_0015_2003.pdf`, donde "ARCHIVO" no es una entidad real y el
     nombre dice `AGN`).
   - `year_mismatch`: mismo caso pero con el Año — el archivo ya está en
     `Tipo/Entidad/Año/archivo`, pero el año del nombre no coincide con la
     carpeta de año donde vive (ej. `ACUERDOS\MME\2014\A_MME_0031_2015.pdf`,
     archivado bajo 2014 pero el nombre dice 2015).

   Para ambas: solo se marca cuando el nombre sí resuelve a un valor
   reconocible y ese valor es distinto de la carpeta actual — un nombre que
   no sigue el patrón no puede probar que la carpeta esté mal, así que se
   deja como bien ubicado (mismo principio del punto 4). Si un archivo tiene
   AMBOS mal (Entidad y Año), se reporta una sola excepción `entity_mismatch`
   que ya trae el Año corregido también — nunca dos excepciones separadas
   para el mismo archivo.

   La comparación de Entidad ignora mayúsculas/minúsculas — Windows ya trata
   los nombres de carpeta así (no pueden coexistir `INVIMA` e `invima` como
   carpetas distintas), así que una diferencia solo de mayúsculas nunca es
   un problema real, ni a nivel de archivo ni de carpeta. Caso real:
   `Documentos/INVIMA` con archivos nombrando `invima` (minúscula) — no se
   marca nada, la carpeta se deja tal cual. Esto también aplica a la
   sugerencia de renombrar carpeta (abajo): variantes de mayúsculas del
   mismo valor alternativo cuentan como un solo voto, no como dos entidades
   distintas, y una carpeta hermana existente bloquea la sugerencia sin
   importar la diferencia de mayúsculas en su nombre.

   A diferencia de las otras dos, `entity_mismatch`/`year_mismatch` pueden
   ser un falso positivo genuino — la carpeta y el nombre pueden referirse
   al mismo valor con grafías distintas (ej. `CMAGUACHICA` en la carpeta vs
   `CAGUACHICA` en el nombre), y mover el archivo fragmentaría una entidad
   que en realidad ya estaba bien consolidada. Por eso, y solo para estas
   dos, la UI ofrece un botón "Dejar así" por fila que la excluye del lote a
   aplicar sin bloquear las demás filas (`missing_entity_folder`/
   `missing_year_folder` siempre representan un archivo genuinamente
   incompleto, así que no tiene sentido "dejarlos así").

   **Sugerencia de renombrar carpeta en vez de mover archivo por archivo.**
   Cuando los archivos ya estructurados de una carpeta de Entidad resuelven,
   desde su nombre, mayoritariamente a la MISMA entidad distinta de la
   carpeta actual, la corrección real no es mover cada archivo — es que la
   carpeta entera tiene el nombre equivocado. En ese caso se reporta una
   única `FolderRenameSuggestion` (`{tipo, current_entity, suggested_entity,
   current_path, proposed_path, file_count}`) en vez de N excepciones
   `entity_mismatch`. Condiciones para activarla, todas conservadoras a
   propósito:
   - Todos los archivos que discrepan de la carpeta coinciden entre sí en
     una única entidad alternativa (si hay dos entidades distintas
     propuestas, es ambiguo, no se sugiere nada).
   - Esa entidad alternativa la nombran **más** archivos que los que
     coinciden con el nombre actual de la carpeta — mayoría estricta, mismo
     principio que la clasificación `con_entidad`/`sin_entidad` de un Tipo.
     Esto permite detectar una carpeta cuyo nombre quedó desactualizado
     (muchos archivos ya usan el nombre correcto, un remanente menor sigue
     usando el nombre viejo de la carpeta) sin arriesgarse en un caso
     realmente parejo (ej. un empate 2 contra 2 no alcanza).
   - Al menos 2 archivos lo confirman (un solo archivo es exactamente el
     caso `entity_mismatch` normal, con su propio "Dejar así").
   - La entidad sugerida no coincide con ninguna carpeta hermana que ya
     exista bajo ese Tipo (evita ofrecer lo que en realidad sería una fusión
     de carpetas, no un renombrado — eso queda fuera de alcance, igual que
     fusionar carpetas de Tipo).

   Caso real que motivó la mayoría estricta (en vez de exigir unanimidad):
   `CONCEPTO/CCTCP` tenía 404 archivos — 336 nombraban `CTCP` (incluyendo
   variantes con un espacio de más por error de tipeo) y 68 nombraban
   `CCTCP` (coincidiendo con la carpeta). Confirmado con el usuario que
   `CTCP` es la entidad correcta y `CCTCP` un error — con la regla de
   unanimidad original, los 68 archivos que sí coincidían con la carpeta
   bloqueaban la sugerencia para los 336 restantes.

   Al extraer la entidad del nombre del archivo, un espacio de más justo
   después del guion bajo (ej. `CTO_ CTCP_...` en vez de `CTO_CTCP_...`,
   error de tipeo humano) se recorta antes de comparar — así `CTCP` y
   `" CTCP"` cuentan como el mismo valor, no como dos entidades distintas.

   Un archivo cuyo nombre resuelve a una entidad **con guion** (ej.
   `MME-MJD-MDEF`, una circular conjunta de varios ministerios) no cuenta
   como voto ni a favor ni en contra al calcular el consenso — no es que
   discrepe con la carpeta, es que menciona más de una entidad a la vez.
   Caso real: `CIRCULAR/Min Minas y Energia` tenía 49 archivos que
   nombraban `MME` y 2 circulares conjuntas (`MME-MJD-MDEF`,
   `MME-MTRA`) — sin esta excepción, esos 2 archivos rompían el consenso
   de los 49 y bloqueaban la sugerencia para toda la carpeta. Si la carpeta
   sí se renombra, esos archivos "conjuntos" se mueven igual (la carpeta se
   mueve completa), simplemente no cuentan para decidir si renombrar.

   Como con `entity_mismatch`/`year_mismatch`, es editable (el nombre de
   entidad sugerido) y tiene su propio "Dejar así" — puede ser un falso
   positivo si el patrón de nombres coincide por casualidad.

**Archivos ignorados por completo:** basura generada por el sistema
operativo (`Thumbs.db`, `desktop.ini`, `.DS_Store`, sin distinguir
mayúsculas/minúsculas) nunca entra a ningún conteo, tabla de excepciones ni
lista de `extra_depth` — ni siquiera se menciona en ningún lado. No son
documentos, así que aplicarles cualquiera de las reglas de arriba no tiene
sentido.

3. **Tipo `sin_entidad`:** cada archivo debe vivir en `Año/archivo` directo
   bajo el Tipo. No se detectó ningún caso de excepción de este tipo en el
   lote de referencia, pero si un archivo apareciera directo bajo el Tipo
   (sin carpeta de año) se clasifica también como `missing_year_folder` —
   mismo `kind` que el caso 2, la carpeta que falta es la misma.
4. **Resolver el dato faltante desde el nombre del archivo.** La mayoría de
   archivos de intake ya sigue el patrón `TIPOCODE_ENTIDAD_NUMERO_AÑO.ext`
   (el mismo que produce el Formateador). Se intenta extraer:
   - El **año**: el token de 4 dígitos que matchea el patrón de año, típicamente
     el último segmento antes de la extensión.
   - La **entidad**: el segundo token separado por `_` (después del código
     de tipo), cuando aplica — pero solo si ese token no es puramente
     numérico. Algunas series de documentos (ej. Gacetas: `GC_0114_1992.pdf`)
     siguen un patrón más corto `CODIGO_NUMERO_AÑO` (3 tokens, sin entidad
     codificada), y en ese caso el segundo token es el número del documento,
     no una entidad — un código de entidad real siempre tiene letras
     (`MSPS`, `PGN`, `AGN`, `GC`...), así que un token todo-numérico ahí
     nunca se toma como entidad.
   Si el nombre no calza con ese patrón (como `RSG2058.docx`, sin año ni
   entidad codificados), no se puede resolver automáticamente.
5. **No resuelto automáticamente → revisión manual.** Se marca la excepción
   con el dato faltante en blanco, y como sugerencia editable (nunca
   autoritativa — la fecha de un archivo puede no reflejar la fecha real del
   acto administrativo) se ofrece el año de última modificación del archivo
   en disco. Como esta sugerencia se ve idéntica a un año leído con
   confianza del nombre del archivo, la UI marca el campo con un aviso
   ("Sin confirmar — revisa el documento") siempre que `detected_year` sea
   `None` — el admin debe verificar contra el documento antes de aplicar.
6. **Ruta propuesta.** Una vez resueltos tipo, entidad (si aplica) y año, la
   ruta propuesta es `Tipo/[Entidad/]Año/nombre-original-del-archivo` — esta
   herramienta reorganiza carpetas, no renombra archivos (eso ya lo hace el
   Formateador; no se duplica esa responsabilidad aquí).

## Backend

**`core/reorganize.py`** (lógica pura, sin FastAPI ni I/O de red):
- `analyze_batch(root: Path) -> BatchAnalysis`: recorre el árbol con
  `os.walk` o `Path.rglob`, clasifica cada Tipo, detecta excepciones según
  la regla de arriba, y devuelve un resumen: conteos por Tipo (total /
  excepciones), la lista de excepciones (`ReorganizeException`), y la lista
  de casos informativos de profundidad extra (`ExtraDepthEntry`) — nunca
  la lista completa de archivos ya bien ubicados (evita mandar 53 mil filas
  al frontend que no aportarían nada). `extra_depth` en sí también se
  recorta a los primeros `EXTRA_DEPTH_LIMIT` (500) por la misma razón —
  Tipos como `Gacetas` o `CIRCULAR` pueden acumular miles de archivos bajo
  un mismo nivel extra — pero el conteo real completo siempre viaja en
  `extra_depth_total`, así nunca se pierde silenciosamente cuántos hay.
  Los archivos sueltos directamente bajo `root` (sin carpeta de Tipo) se
  reportan igual en `extra_depth` (con `tipo=""`) en vez de excluirse del
  conteo. También devuelve `folder_renames: list[FolderRenameSuggestion]`
  cuando aplica (ver la regla de auditoría, punto 2).
- `apply_moves(moves: list[ResolvedMove]) -> ApplyResult`: por cada
  movimiento, valida que el origen y el destino resuelvan dentro de `root`
  (se salta con `skip_reason` si no — protege contra un `current_path` o
  `target_path` con `..` o una ruta absoluta que se saliera de la carpeta),
  que el origen exista y el destino **no** exista ya (nunca sobrescribe),
  crea las carpetas destino que falten (`Path.mkdir(parents=True,
  exist_ok=True)`) y mueve el archivo (`shutil.move` — casi instantáneo al
  ser mismo volumen). Devuelve, por archivo, si se movió o se saltó y por
  qué (mismo patrón `copiedCount`/`skippedCount` que ya usa `copy.ts` del
  Formateador).
- `apply_folder_renames(root: Path, renames: list[ResolvedFolderRename]) ->
  list[FolderRenameOutcome]`: mismas protecciones que `apply_moves`
  (contención dentro de `root`, origen debe existir, destino **no** debe
  existir ya, un fallo por carpeta nunca aborta el resto) pero mueve la
  carpeta completa de una vez (`shutil.move` sobre un directorio) en vez de
  archivo por archivo.

**`api/routers/reorganize.py`** (nuevo router, protegido con
`require_admin` a nivel de router — a diferencia de `sources.py`, aquí
*ninguna* operación es de solo lectura para un usuario regular; no hay caso
de uso para un `GET` público):
- `POST /reorganize/analyze` — body `{ root_path: str }`. 404 si la ruta no
  existe o no es un directorio. Llama a `analyze_batch` y devuelve el
  `BatchAnalysis`.
- `POST /reorganize/apply` — body `{ root_path: str, moves: list[{
  current_path: str, target_path: str }], folder_renames: list[{
  current_path: str, target_path: str }] = [] }`. 404 si `root_path` no
  existe o no es un directorio (misma validación que `analyze`). Llama
  primero a `apply_folder_renames` (una carpeta destino de un `move` en
  cola necesita existir para cuando ese move corra) y luego a
  `apply_moves`, combina ambos en el `ApplyResult`.

**`api/schemas.py`** — nuevos modelos:
```python
class ReorganizeAnalyzeRequest(BaseModel):
    root_path: str

class ReorganizeException(BaseModel):
    tipo: str
    kind: Literal["missing_entity_folder", "missing_year_folder", "entity_mismatch", "year_mismatch"]
    current_path: str
    detected_entity: Optional[str] = None
    detected_year: Optional[int] = None
    mtime_year_hint: Optional[int] = None
    proposed_path: Optional[str] = None  # None si falta resolver algo

class TipoSummary(BaseModel):
    tipo: str
    total_files: int
    exception_count: int

class ExtraDepthEntry(BaseModel):
    tipo: str
    current_path: str

class FolderRenameSuggestion(BaseModel):
    tipo: str
    current_entity: str
    suggested_entity: str
    current_path: str
    proposed_path: str
    file_count: int

class BatchAnalysis(BaseModel):
    root_path: str
    total_files: int
    tipos: list[TipoSummary]
    exceptions: list[ReorganizeException]
    extra_depth: list[ExtraDepthEntry]  # recortado a EXTRA_DEPTH_LIMIT (500)
    extra_depth_total: int  # conteo real, sin recortar
    folder_renames: list[FolderRenameSuggestion]

class ResolvedMove(BaseModel):
    current_path: str
    target_path: str

class ResolvedFolderRename(BaseModel):
    current_path: str
    target_path: str

class ReorganizeApplyRequest(BaseModel):
    root_path: str
    moves: list[ResolvedMove]
    folder_renames: list[ResolvedFolderRename] = []

class MoveResult(BaseModel):
    current_path: str
    target_path: str
    moved: bool
    skip_reason: Optional[str] = None

class FolderRenameOutcome(BaseModel):
    current_path: str
    target_path: str
    renamed: bool
    skip_reason: Optional[str] = None

class ApplyResult(BaseModel):
    results: list[MoveResult]
    folder_rename_results: list[FolderRenameOutcome] = []
```

`api/main.py` agrega `app.include_router(reorganize.router)`.

Todos los campos `*_path` de `ReorganizeException`, `ExtraDepthEntry`,
`FolderRenameSuggestion`, `ResolvedMove`, `ResolvedFolderRename`,
`MoveResult` y `FolderRenameOutcome` son **rutas relativas a `root_path`**
(con `/` como separador, independiente del SO), no rutas absolutas de
disco — el frontend nunca necesita conocer ni reconstruir la ruta
absoluta, solo la reenvía tal cual la recibió.

## Frontend

`FormatterPage.tsx` se convierte en un contenedor liviano con dos pestañas
— "Renombrado" (lo que existe hoy) y "Reorganización" (nuevo) — porque
juntar ambos flujos en un solo archivo lo haría difícil de seguir. Se
reubica el contenido actual sin cambiar su lógica:

- `frontend/src/pages/formatter/RenamePanel.tsx` — el JSX y los handlers
  que hoy viven en `FormatterPage.tsx`, movidos tal cual (mismo
  comportamiento, mismos tests, solo cambia la ubicación del archivo y el
  nombre del componente).
- `frontend/src/pages/formatter/ReorganizePanel.tsx` — nuevo. Un input de
  texto para la ruta + botón "Analizar" → tabla de sugerencias de renombrar
  carpeta (Tipo, carpeta actual, entidad nueva editable, archivos
  afectados, carpeta propuesta, "Dejar así") + tabla de excepciones (Tipo,
  ruta actual, entidad detectada editable, año detectado/sugerido editable,
  ruta propuesta, "Dejar así" para `entity_mismatch`/`year_mismatch`) +
  botón "Aplicar" único para ambas tablas (deshabilitado hasta que todas
  las filas activas —no descartadas con "Dejar así"— tengan sus campos
  resueltos, mismo criterio `canCopy` que ya usa el Formateador). Los casos
  de profundidad extra solo se cuentan en el resumen de arriba
  (`extra_depth_total`) — nunca se listan uno por uno en pantalla, ya que
  son puramente informativos y nunca se tocan (a diferencia de las otras
  dos tablas, no cambian según lo que el admin haga).
- `frontend/src/pages/FormatterPage.tsx` — pasa a ser el shell con estado de
  pestaña activa (`useState<"rename" | "reorganize">`) que renderiza el
  panel correspondiente.
- `frontend/src/api/reorganize.ts` — `analyzeReorganization(rootPath)` /
  `applyReorganization(rootPath, moves, folderRenames)`, usando `apiFetch`
  como el resto de `frontend/src/api/*.ts`.
- `frontend/src/lib/reorganize/proposePath.ts` — `computeProposedPath`
  (excepciones archivo por archivo) y `computeFolderRenameTarget(tipo,
  entityName)` (sugerencias de renombrar carpeta), ambas puras y editables
  — nunca autoritativas.

`lib/formatter/` (la lógica de renombrado) no cambia — la sigue usando
`RenamePanel.tsx` exactamente igual que hoy.

## Manejo de errores

- Ruta inexistente o que no es carpeta → `404` con mensaje claro
  ("La ruta no existe o no es una carpeta").
- Usuario sin `is_admin` → `403` (mismo comportamiento que
  `require_admin` en `sources.py`).
- En `apply`, un movimiento (de archivo o de renombrado de carpeta) cuyo
  destino ya existe se salta (no sobrescribe) y se reporta con
  `skip_reason`; un error de I/O al mover (permiso denegado, archivo
  bloqueado) también se salta y se reporta — nunca aborta el resto del
  lote por un solo fallo.

## Pruebas

**Backend (`tests/test_core_reorganize.py`, lógica pura sobre `tmp_path`):**
- Un Tipo `con_entidad` con archivos ya en `Entidad/Año/archivo` no produce
  ninguna excepción.
- Un Tipo `sin_entidad` (como `Leyes`) con archivos en `Año/archivo` no
  produce ninguna excepción (no se confunde con `missing_entity_folder`).
- `Tipo/Año/archivo.pdf` con nombre `X_ENTIDAD_0001_AÑO.pdf` se detecta como
  `missing_entity_folder`, con `detected_entity` y `proposed_path` resueltos
  automáticamente.
- `Tipo/Entidad/archivo.docx` con nombre que no sigue el patrón se detecta
  como `missing_year_folder`, con `detected_year=None`, `mtime_year_hint` poblado
  desde la fecha de modificación del archivo de prueba, y
  `proposed_path=None`.
- Un archivo con un nivel extra de profundidad aparece en `extra_depth` y
  nunca en `exceptions`.
- Un archivo ya en `Tipo/Entidad/Año/archivo` cuya Entidad no coincide con
  la del nombre del archivo se detecta como `entity_mismatch`, con
  `detected_entity` resuelto desde el nombre. Si el nombre no se puede
  resolver, o si coincide con la carpeta, no produce ninguna excepción.
- Mismo caso pero con el Año se detecta como `year_mismatch`. Si ambos
  (Entidad y Año) están mal, se reporta una sola excepción `entity_mismatch`
  con el Año ya corregido también.
- `apply_moves` mueve el archivo y crea las carpetas destino que faltan.
- `apply_moves` no sobrescribe un destino que ya existe (se salta con
  `skip_reason`).

**Backend API (`tests/test_api_reorganize.py`):**
- Usuario no-admin recibe `403` en `POST /reorganize/analyze` y
  `POST /reorganize/apply`.
- Ruta inexistente devuelve `404`.
- Caso feliz de `analyze` sobre un árbol de prueba en `tmp_path` devuelve
  la forma esperada.

**Frontend:**
- `frontend/src/pages/formatter/RenamePanel.test.tsx` — los tests que hoy
  están en `FormatterPage.test.tsx`, reubicados sin cambios de aserciones.
- `frontend/src/pages/formatter/ReorganizePanel.test.tsx` (MSW mockeando
  `/reorganize/analyze` y `/reorganize/apply`) — muestra la tabla de
  excepciones tras analizar, permite editar entidad/año, deshabilita
  "Aplicar" mientras falte algo por resolver, y muestra el resultado tras
  aplicar.
- `frontend/src/pages/FormatterPage.test.tsx` (reducido) — cambiar de
  pestaña muestra el panel correspondiente.
