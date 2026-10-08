# Fuente: Superintendencia de Transporte (`supertransporte`)

Fecha: 2026-10-08. Código: `core/scrapers/families/supertransporte.py`.

## Sitio

- `www.supertransporte.gov.co` es WordPress (tema Avada). La página de
  Normativa (`/index.php/transparencia-normatividad/`) agrupa la normativa en
  anclas (`#leyes`, `#decretos`, `#res-internas`, `#circ-externas`,
  `#circ-conjuntas`, …).
- **Resoluciones generales:** una página por año,
  `/index.php/resoluciones-generales/<año>/` (2000→hoy; 2020 vive en
  `/2020-2/`). Las genera el plugin `resoluciones_menu`: cada
  `<section class="resolution">` trae «Supertransporte expide la Resolución N
  de AAAA», un párrafo «Fecha de resolución: …» (o «Fecha de publicación»; en
  2011 «Bogotá, 22 de Diciembre» sin año), el epígrafe, el PDF y a veces
  anexos o resoluciones acompañantes.
- **Circulares SICOV:** lista numerada en
  `/index.php/transparencia-normatividad-circular-sicov/`.
- **Circular Única de Infraestructura y Transporte:** un PDF por título
  (I–VII) más el «Cuadro control de modificaciones», en
  `/index.php/circulares/circular-unica-de-infraestructura-y-transporte/`.
- **Conceptos:** la «Biblioteca Jurídica»
  (`bibliotecajuridica.supertransporte.gov.co:3000`) es una aplicación React
  en modo desarrollo. Su listado (852 registros; 793 conceptos 2020–2021) está
  escrito dentro de `bundle.js` (`this.documents = [...]` en
  `ProcessService.js`); el backend que declara (`172.27.244.20`) es una IP
  privada que no se usa. Los archivos se sirven en `/files/<nombre>`
  (PDF o TIF escaneado). Fechas de relleno (`01-01-<año>`), título = tema.
- Las carpetas `/documentos/<año>/<Mes>/<Dependencia>_<día>/` dan la fecha de
  subida del archivo.

## Alcance (aprobado por el usuario)

Entran: resoluciones generales, resoluciones internas, circulares externas,
conjuntas y SICOV, títulos de la Circular Única y conceptos de la Biblioteca.

Quedan fuera: leyes y decretos (enlazan a Función Pública, Senado, SUIN),
sentencias y normativa por proceso (índices en Excel), gaceta, políticas y
manuales; de la Biblioteca, todo lo que no es concepto.

## Títulos (sigla `SPT`)

| Documento | Título |
|---|---|
| Resolución 9788 de 2026 | `R_SPT_9788_2026` (número con relleno a 4) |
| Anexos | `R_SPT_9596_2026_A01`, `_A02`… |
| Toda circular (externa, conjunta, SICOV) | `C_SPT_0054_2023`; radicados largos tal cual: `C_SPT_20265330000164_2026` |
| Circular sin número | `C_SPT_SN_2023` |
| Título de la Circular Única | `TCU_SPT_III_20260818` (título y fecha de la versión); cuadro: `TCU_SPT_CUADRO-CONTROL_20260818` |
| Concepto | `CTO_SPT_20203000286531` (radicado del nombre de archivo) |

- El número sólo cuenta si el texto empieza por el acto: «Alcance a la
  Circular…» y «Fe de Erratas – Circular…» quedan con el texto del sitio y
  marca de sin verificar (como en SIC).
- «Anexo técnico … / Circular Externa …» en la lista de circulares es anexo
  de la circular listada justo antes.
- Títulos repetidos (la misma resolución subida en dos carpetas, la circular
  93 de 2016 en SICOV y en conjuntas) se distinguen con `_2`, `_3`, calculado
  sobre el conjunto completo de la página/lista (no del rango) y ordenado por
  expedición, publicación y URL. El mismo archivo enlazado dos veces cuenta
  una sola vez.

## Fechas y filtro

- `f_providencia`: la fecha del texto (resolución, circular). En SICOV, que
  sólo dice «Circular 43 de 2018», la fecha de la carpeta si es del mismo año
  y si no el 1 de enero. Sólo se mira la cabeza del texto (antes de «–»,
  «)»…), porque la descripción cita otras fechas.
- `f_public`: la fecha de la carpeta, salvo que sea anterior a la expedición
  (carpeta reutilizada) o no siga el patrón: entonces la de expedición.
  `filters_by_publication_date = True`.
- Las resoluciones se buscan en las páginas desde un año antes de `fini`;
  `scheduled_min_lookback_days = 30` porque la subida puede ir semanas detrás.
- Conceptos: fecha `<año>-01-01` y filtro por **año** (todas sus fechas son de
  relleno; ver la regla de fechas sólo-año).

## Medición (2026-10-08, carga completa)

1.777 documentos: 914 resoluciones (incluye anexos y 4 internas), 76
circulares, 8 títulos de la Circular Única y 779 conceptos (793 menos 14
repetidos). 4 títulos sin verificar. 12 enlaces rotos en el propio sitio
(11 resoluciones antiguas, 1 concepto). Una corrida diaria lee ~2 páginas de
resoluciones, 3 páginas más y el `bundle.js` (~5 MB).
