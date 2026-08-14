# Fuente Ministerio del Interior (mininterior) — Design

## Contexto

Siguiente fuente en la ronda de "ir agregando ministerios/entidades familia
por familia" (después de Minhacienda, que quedó pausada por estar detrás de
Radware Bot Manager en todo el dominio — ver memoria de proyecto
`iurisync-minhacienda-blocked`). El usuario pidió:
`mininterior.gov.co/normatividad/`.

## Descubrimiento del sitio

- **Sin protección anti-robots.** A diferencia de Minhacienda, tanto el
  listado como los PDFs se descargan con una petición `requests` común y
  corriente — confirmado con `curl` plano, sin headers especiales.
- El sitio es WordPress (Divi + un plugin de filtros tipo "de_mach"/ACF), con
  un tipo de contenido propio `normativas`. No expone REST API para ese post
  type (`/wp-json/wp/v2/types` solo lista `post`), así que no hay atajo de
  API — se scrapea el HTML del archivo igual que `adr`/`ane`/`anh`.
- El archivo (`/normatividad/`, paginado 6 por página vía
  `/normatividad/page/N/`) es un **único listado cronológico mezclando TODOS
  los tipos** (a diferencia de `madr`/`mincit`, que tienen una página propia
  por categoría) — WP_Query interno confirmado en el HTML:
  `orderby: meta_value, meta_key: fecha_de_entrada_en_vigencia, order: DESC`.
  Es decir, siempre viene ordenado del más nuevo al más viejo por esa fecha,
  sin excepción.
- El sitio tiene filtros visuales (dependencia, tipo de norma, año) pero
  **no se pudieron activar de forma confiable por automatización** — cambiar
  los `<select>` actualiza la URL vía `history.pushState` pero no dispara la
  petición AJAX real (ni tocando el botón "Filtrar" se vio la llamada en la
  red). No hace falta: como el listado ya viene ordenado del más nuevo al más
  viejo, se pagina secuencialmente y se para en cuanto se encuentra un
  documento anterior a `fini` — mismo principio que otras fuentes basadas en
  orden cronológico nativo del sitio.
- Cada item de listado trae, en HTML confirmado contra la página real:
  - Badge de tipo (`Decreto`, `Resolución`, ...) como texto plano.
  - Título ya redactado por el ministerio (`h4.dmach-post-title`), ej.
    `"DECRETO No. 1028 DEL 5 DE AGOSTO DE 2026"` /
    `"Resolución No. 1386 del 04 de agosto de 2026"`.
  - Descripción (resumen).
  - **Fecha de entrada en vigencia** con precisión de día completo, formato
    único confirmado `"{mes en minúsculas} {día sin cero a la izquierda},
    {año}"` (ej. `"agosto 5, 2026"`) — a diferencia de Mineducación, no hace
    falta la degradación a "solo año".
  - Enlace directo al PDF (`a.et_pb_button`, texto "Documento"), alojado en
    `wp-content/uploads/...` — plano, sin sesión ni referer, confirmado
    descargable con `curl` (PDF real de 17.9 MB probado).
- El listado tiene items empatados en la misma fecha entre páginas
  consecutivas (confirmado en vivo: la misma Resolución aparece tanto en la
  página 1 como en la página 2) porque WordPress no usa un desempate estable
  cuando `orderby=meta_value` tiene valores repetidos. Produce duplicados
  ocasionales entre páginas contiguas — inofensivos, porque el `doc_id`
  aguas abajo se calcula por URL, no por posición en el listado.

## Decisiones explícitas del usuario

- **Alcance de tipos**: el filtro "tipo de norma" del sitio tiene 50+
  valores mezclando normas formales con documentos administrativos internos
  (Informe, Manual, Memorandos, Meci, Notificación, Programa de
  Transparencia y Ética Pública, Respuestas derecho de petición, Tutela...).
  El usuario eligió explícitamente la opción recomendada: **solo normas
  formales** — Decreto, Resolución, Circular (Externa/Interna), Ley, Ley
  Estatutaria, Directiva, Acuerdo, Concepto, Acto Administrativo, Acto
  Legislativo. Cualquier tipo fuera de esta lista se descarta silenciosamente
  (no detiene la paginación, ver `_TIPOS_EN_ALCANCE` en el código).
  - Nota: dentro de "Resolución" hay un volumen alto de resoluciones
    caso-por-caso (consultas previas de proyectos de infraestructura/minería/
    energía emitidas por la Dirección de la Autoridad Nacional de Consulta
    Previa) — confirmado que sí llevan tipo "Resolución" en el propio sitio,
    así que entran dentro del alcance elegido; no es un error de
    clasificación, es simplemente el volumen real de ese tipo formal en este
    ministerio.
- **Formato de título**: el usuario prefirió normalizar al mismo formato ya
  usado por `madr`/`mincit`/`mineducacion` (`{LETRA}_{SIGLA}_{numero:04d}_
  {año}`) en vez de conservar el título tal cual lo redacta el sitio, para
  mantener consistencia entre fuentes. Sigla elegida: `MININT`.

## Vías alternas descartadas

Ninguna — a diferencia de Minhacienda, el sitio directo del ministerio no
tuvo ningún bloqueo, así que no hizo falta buscar una fuente espejo.

## Arquitectura

Un archivo `core/scrapers/families/mininterior.py`, clase
`ScrapMininterior(BaseScrapper)` registrada como `@register_family
("mininterior")`. `scrap()` pagina `/normatividad/` y `/normatividad/page/
{n}/` secuencialmente; por cada item fuera de alcance (tipo no reconocido) lo
descarta sin afectar la paginación; al primer item EN alcance con fecha
anterior a `fini`, deja de pedir páginas (el orden descendente del sitio
garantiza que todo lo que sigue también es más viejo). Sin parámetros de
`family_params` (`{}`), igual que `mincit`/`madr`/`mineducacion`.

- `f_public`: fecha completa parseada de "Fecha de entrada en vigencia".
  `doc_id_uses_publication_date` y `filters_by_publication_date` se dejan en
  su default (`True`/`False`), mismo criterio que `madr.py`: es una fecha
  intrínseca al documento, y no hay campo separado de "fecha de
  providencia"/expedición distinto en el listado.
- `checks_for_republication` se deja en su default `True`: el PDF cuelga de
  una URL GET directa.

## Rama

A diferencia de Mineducación (que se construyó sobre `feat/fuente-
mineducacion`), esta fuente se creó en su propia rama (`feat/fuente-
mininterior`) partiendo directo de `master` — decisión explícita del
usuario, para que el PR de Mininterior sea revisable/mergeable de forma
independiente sin arrastrar el trabajo de Mineducación (que todavía no
estaba mergeado a `master` en ese momento).
