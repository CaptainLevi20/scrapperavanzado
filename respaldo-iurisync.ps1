# =====================================================================
#  Respaldo completo de IURISYNC
#  Copia: (1) base de datos  (2) documentos  (3) archivos de configuracion
#
#  Uso manual:
#    - En una terminal, dentro de la carpeta de instalacion:
#        powershell -ExecutionPolicy Bypass -File .\respaldo-iurisync.ps1
#
#  Uso programado (Programador de tareas de Windows):
#    Programa:   powershell.exe
#    Argumentos: -ExecutionPolicy Bypass -File "C:\iurisync\respaldo-iurisync.ps1"
#    (ajusta la ruta si copiaste los archivos en otra carpeta)
#
#  El respaldo queda en la subcarpeta  respaldos\AAAA-MM-DD  junto a este
#  archivo. RECUERDA copiar esa carpeta a otro disco u otro servidor: un
#  respaldo que vive en la misma maquina no protege si la maquina falla.
#
#  Nota tecnica: los documentos se empaquetan en un unico archivo
#  'documentos.tar.gz' generado DENTRO de Docker. Es a proposito: algunas
#  carpetas del almacenamiento terminan en espacio (validas en Linux,
#  invalidas en Windows) y una copia carpeta-por-carpeta al disco de
#  Windows falla. Dentro del .tar.gz esos nombres se conservan sin problema.
# =====================================================================

$ErrorActionPreference = 'Stop'

# Ubicarse SIEMPRE en la carpeta de este script (ahi estan docker-compose.prod.yml
# y .env.production), sin importar desde donde se ejecute.
Set-Location -Path $PSScriptRoot

$fecha       = Get-Date -Format 'yyyy-MM-dd'
$destino     = Join-Path $PSScriptRoot "respaldos\$fecha"
$destinoUnix = ($destino -replace '\\', '/')      # Docker en Windows quiere barras normales
$base        = @('compose', '--env-file', '.env.production', '-f', 'docker-compose.prod.yml')

function Check($paso) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR en el paso: $paso  (codigo $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "El respaldo NO quedo completo. Avisa al equipo de desarrollo." -ForegroundColor Red
        exit 1
    }
}

Write-Host "== Respaldo IURISYNC  $fecha =="
Write-Host "Carpeta destino: $destino"
New-Item -ItemType Directory -Force -Path $destino | Out-Null

# --- 1. Base de datos (usuarios y datos de cada documento) ---
Write-Host ""
Write-Host "[1/3] Base de datos..."
& docker @base exec -T postgres pg_dump -U iurisync -Fc iurisync -f /tmp/bd.dump ; Check "volcado de la base de datos"
& docker @base cp postgres:/tmp/bd.dump (Join-Path $destino 'bd.dump')           ; Check "copiar el volcado a la carpeta de respaldo"
& docker @base exec -T postgres rm /tmp/bd.dump                                  ; Check "borrar el archivo temporal dentro del contenedor"
Write-Host "      OK  ->  bd.dump"

# --- 2. Documentos (los archivos PDF, almacenamiento MinIO) ---
#     Se empaqueta desde dentro de Docker para no chocar con las reglas de
#     nombres de carpeta de Windows (ver nota tecnica arriba).
Write-Host ""
Write-Host "[2/3] Documentos... (puede tardar varios minutos)"
$minio = (& docker @base ps -q minio)
if ($LASTEXITCODE -ne 0 -or -not $minio) {
    Write-Host "ERROR: no se encontro el contenedor 'minio' en ejecucion." -ForegroundColor Red
    Write-Host "Levanta la herramienta y vuelve a intentar." -ForegroundColor Red
    exit 1
}
& docker run --rm --volumes-from $minio -v "${destinoUnix}:/backup" alpine tar czf /backup/documentos.tar.gz -C /data . ; Check "empaquetar los documentos"
Write-Host "      OK  ->  documentos.tar.gz"

# --- 3. Configuracion (contrasenas y ajustes; sin esto no se puede re-levantar) ---
Write-Host ""
Write-Host "[3/3] Configuracion..."
Copy-Item -Path '.env.production', 'docker-compose.prod.yml', 'Caddyfile' -Destination $destino
Write-Host "      OK  ->  .env.production, docker-compose.prod.yml, Caddyfile"

Write-Host ""
Write-Host "Respaldo terminado correctamente en:" -ForegroundColor Green
Write-Host "   $destino" -ForegroundColor Green
Write-Host ""
Write-Host "Contenido esperado: bd.dump, documentos.tar.gz, .env.production,"
Write-Host "docker-compose.prod.yml, Caddyfile"
Write-Host ""
Write-Host "SIGUIENTE PASO (manual): copia esa carpeta a otro disco o servidor,"
Write-Host "distinto de esta maquina."
