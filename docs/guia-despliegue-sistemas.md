# Guía de instalación de IURISYNC — para el equipo de sistemas

Esta guía no requiere conocimientos de programación. Sigue los pasos en orden.
Si algo no funciona como se describe aquí, detente en ese paso y avisa al
equipo de desarrollo antes de continuar.

## 1. Antes de empezar: qué necesitamos de tu parte

- [ ] Una máquina (física o virtual) **dentro de la red de la oficina**, con
      al menos: 4 núcleos de procesador, 8 GB de memoria RAM, 100 GB de disco.
- [ ] Docker instalado en esa máquina. Si no lo tienen, instrucciones oficiales
      aquí: https://docs.docker.com/engine/install/
- [ ] Cómo se va a llegar a la máquina desde los demás computadores de la
      oficina: **idealmente un nombre, no una IP pelada.** Dos formas de
      lograrlo sin necesidad de un servidor de dominio: (a) si tienen DNS
      interno, un nombre apuntando a la IP de esta máquina, o (b) si no lo
      tienen — lo más común — un nombre corto inventado (ejemplo:
      `iurisync.local`) agregado al archivo "hosts" de cada computador de
      la oficina que vaya a usar la herramienta, apuntando a la IP interna
      fija de esta máquina (ejemplo: `192.168.1.50`). En Windows esto se
      hace agregando una línea a `C:\Windows\System32\drivers\etc\hosts`
      (necesita permisos de administrador); en PowerShell:

      ```
      Add-Content -Path "$env:windir\System32\drivers\etc\hosts" -Value "192.168.1.50  iurisync.local"
      ```

      **Importante — no uses la IP directamente en computadores Windows.**
      Varias versiones de Windows fallan al establecer la conexión segura
      (HTTPS) cuando se conecta a una IP sin nombre: el navegador muestra
      `ERR_SSL_PROTOCOL_ERROR` ("el sitio envió una respuesta no válida")
      en vez de la advertencia normal del candado casero, y no hay forma
      de aceptarla y seguir. Es una limitación de Windows (falta el
      nombre del sitio en el saludo de seguridad, algo llamado SNI), no
      un error de esta instalación. Usar un nombre — aunque sea
      inventado, resuelto solo por el archivo hosts — evita el problema
      por completo.
- [ ] Confirmar: ¿tienen una autoridad certificadora (CA) interna propia para
      emitir certificados HTTPS? Si no están seguros, la respuesta por
      defecto es "no" y esta guía funciona igual (ver sección 5).
- [ ] Una regla de firewall que permita, desde la red de la oficina hacia esta
      máquina, los puertos **80**, **443** y **9443**. Los dos primeros son el
      tráfico normal de navegación; el 9443 es por donde el navegador descarga
      y previsualiza los documentos. Si el 9443 queda cerrado, la herramienta
      abre y deja iniciar sesión, pero ningún documento se puede abrir ni
      descargar.

## 2. Copiar los archivos a la máquina

El equipo de desarrollo te entrega estos tres archivos. Cópialos en una
carpeta de tu elección en el servidor, por ejemplo `C:\iurisync\` o
`/opt/iurisync/`, todos juntos en la misma carpeta:

- `docker-compose.prod.yml`
- `Caddyfile`
- `.env.production.example`

## 3. Configurar las variables de producción

Copia `.env.production.example` a un archivo nuevo llamado `.env.production`,
en la misma carpeta. Ábrelo con un editor de texto simple (Bloc de notas
sirve) y reemplaza cada valor que dice `CAMBIAR_ESTO` por uno propio:

- `CADDY_DOMAIN` y `CORS_ORIGINS`: el subdominio interno real, o — si no
  tienen dominio — el nombre inventado que agregaron al archivo hosts de
  cada computador (ver sección 1; ejemplo: `CADDY_DOMAIN=iurisync.local`
  y `CORS_ORIGINS=https://iurisync.local`) — la misma dirección en ambas
  líneas. **No pongas aquí la IP directamente** (ver la advertencia sobre
  Windows en la sección 1).
- `S3_PUBLIC_ENDPOINT_URL`: la misma dirección otra vez, pero terminada en
  `:9443` (ejemplo: `https://documentos.avancejuridico.com.co:9443` o
  `https://iurisync.local:9443`). Es la dirección por la que el navegador
  de cada persona descarga los documentos.
- `POSTGRES_PASSWORD` y la contraseña dentro de `DATABASE_URL`: deben ser
  **exactamente la misma contraseña**, elegida por ustedes, en ambos lugares.
- `S3_ACCESS_KEY` / `S3_SECRET_KEY`: un usuario y contraseña nuevos, elegidos
  por ustedes, para el almacenamiento de documentos.
- `REGISTRATION_CODE`: el código que cada persona del equipo va a usar para
  crear su cuenta la primera vez. Compártanlo solo con quienes deban tener
  acceso.

**Cómo tienen que ser las contraseñas:** las de `POSTGRES_PASSWORD` /
`DATABASE_URL` y la de `S3_SECRET_KEY` deben usar **solo letras y números**
(nada de `@ : / # ?` ni otros símbolos raros, porque la contraseña de Postgres
va escrita dentro de la dirección de conexión `DATABASE_URL` y esos símbolos la
parten por la mitad), y tener **al menos 12 caracteres** (el almacenamiento de
documentos rechaza de plano cualquier clave de menos de 8).

Guarda el archivo. **No lo compartas por correo ni lo subas a ningún sitio
público** — contiene contraseñas.

## 4. Levantar la herramienta

Abre una terminal (PowerShell en Windows, o una terminal normal en Linux),
ubícate en la carpeta donde copiaste los archivos, y ejecuta estos comandos
uno por uno, en este orden exacto:

```
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres redis minio
```

Espera unos 15 segundos, luego:

```
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api alembic upgrade head
```

```
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed
```

```
docker compose --env-file .env.production -f docker-compose.prod.yml up -d frontend api worker beat caddy
```

Para confirmar que todo quedó corriendo:

```
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Deberías ver 8 servicios, todos en estado `running` o `healthy`. Si alguno
dice `restarting` repetidamente, avisa al equipo de desarrollo con el
resultado de este comando (reemplaza `api` por el nombre del servicio que
falla):

```
docker compose --env-file .env.production -f docker-compose.prod.yml logs api
```

## 5. Sobre el candado de seguridad (HTTPS)

Por defecto, esta instalación genera su propio certificado de seguridad
("candado casero"). Funciona igual ya sea que se entre por un subdominio o
por la IP interna de la máquina. La primera vez que alguien entre desde el
navegador, va a ver una advertencia tipo "conexión no privada" o "sitio no
verificado" — es normal, hay que darle click en "Avanzado" y luego
"Continuar de todos modos" (el texto exacto varía según el navegador). Una
vez aceptado, el navegador no debería volver a preguntar en esa misma
máquina.

**Importante — la descarga y previsualización de documentos usa una segunda
dirección** dentro del mismo servidor, terminada en `:9443` (ver sección 1).
El navegador la usa automáticamente en segundo plano cuando alguien abre un
documento — nadie entra ahí a propósito, como sí pasa con la página
principal. Esto significa que aceptar la advertencia de seguridad en la
página principal **no siempre cubre también esa segunda dirección**: en
Chrome y Edge sí queda cubierta automáticamente, pero **en Firefox no** — ahí
los documentos simplemente no se van a poder abrir (ni descargar ni
previsualizar), aunque el resto de la herramienta funcione normal, y sin
ningún aviso claro de por qué. Si en la oficina se usa Firefox, cada persona
debe visitar **una sola vez, manualmente**, `https://` seguido del
subdominio o la IP y `:9443` (ejemplo: `https://documentos.avancejuridico.com.co:9443`
o `https://192.168.1.50:9443`) y aceptar la advertencia ahí también —
después de eso no vuelve a pedirlo en esa máquina.

Si su empresa sí tiene una autoridad certificadora interna propia, avisen al
equipo de desarrollo — se puede reemplazar este certificado casero por uno
oficial de la empresa, sin necesidad de rehacer el resto de la instalación.

**Recomendado, sobre todo si en la oficina se usa Firefox:** para que nadie
tenga que aceptar advertencias manualmente (ni en la página principal ni en
la dirección `:9443` de arriba), pueden repartir el certificado raíz que
genera esta instalación a todos los computadores de la oficina por directiva
de grupo (Group Policy) o por el sistema de administración de equipos que
usen. El archivo está dentro del volumen de Docker `caddy_data`, en la ruta
`pki/authorities/local/root.crt`. Una vez instalado en cada máquina como
autoridad de confianza, el candado aparece normal y sin advertencias, en
ambas direcciones.

## 6. Verificación final

Desde un computador conectado a la red de la oficina — con el archivo hosts
ya configurado si no tienen dominio, ver sección 1 — abre un navegador y
entra a `https://` seguido del subdominio o nombre configurado (ejemplo:
`https://documentos.avancejuridico.com.co` o `https://iurisync.local`).
Deberías ver la pantalla de inicio de sesión de IURISYNC. Usa el
`REGISTRATION_CODE` que configuraste en el paso 3 para crear la primera
cuenta desde la pantalla de registro. Esa primera cuenta **no queda como
administrador automáticamente** — sin este paso, nadie va a poder activar,
desactivar ni crear fuentes dentro de la herramienta. Para convertirla en
administrador, ejecuta este comando (reemplaza `NOMBRE_DE_USUARIO` por el
usuario que acabas de crear):

```
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres psql -U iurisync -d iurisync -c "UPDATE users SET is_admin = true WHERE username = 'NOMBRE_DE_USUARIO';"
```

Si la página no carga, revisa en este orden: (1) que la dirección
configurada realmente llegue al servidor (`ping <subdominio o nombre>`
desde otro computador de la oficina — debe resolver a la IP correcta,
por DNS interno o por el archivo hosts), (2) que el firewall deje pasar
el puerto 443, (3) el resultado del comando `docker compose ... ps` del
paso 4. Si el navegador muestra `ERR_SSL_PROTOCOL_ERROR` en vez de la
advertencia normal del candado casero, revisa que no estés entrando por
la IP directamente — ver la advertencia sobre Windows en la sección 1.

Por último, **abre un documento** desde la herramienta (no basta con verlo en
la lista: hay que darle click para descargarlo o previsualizarlo). Si la
página carga y el listado se ve, pero al abrir un documento sale un error o la
descarga nunca empieza, casi siempre es una de estas tres cosas: el puerto
**9443** está cerrado en el firewall, `S3_PUBLIC_ENDPOINT_URL` en
`.env.production` no quedó con el subdominio o la IP correcta terminada en
`:9443`, o (si están en **Firefox**) todavía no se aceptó la advertencia de
seguridad en esa segunda dirección — ver el aviso de Firefox en la sección 5.

**Caso aparte — la previsualización no abre pero la descarga sí:** si al
_previsualizar_ un documento la vista queda en blanco y, al abrir la consola
del navegador (tecla F12 → pestaña "Consola"), aparece un mensaje del tipo
`Promise.withResolvers is not a function` o `URL.parse is not a function`, el
navegador de ese computador es **viejo** (anterior a mediados de 2024; por
ejemplo Chrome/Edge menores a la versión 126, o Firefox menores a 126). El
visor de PDF usa funciones del lenguaje que esas versiones viejas no traen. La
herramienta ya incluye "rellenos" (polyfills) que cubren estos navegadores, así
que a partir de la versión que trae este arreglo no debería volver a pasar; si
aun así ocurre, **actualizar el navegador a una versión reciente lo resuelve
definitivamente**. A diferencia de las tres causas anteriores, esto afecta
**solo la previsualización** (la descarga sigue funcionando) y no tiene que ver
con la red ni con el puerto `:9443`. Tras desplegar el arreglo, en el
computador afectado conviene forzar una recarga (Ctrl + F5) una vez, para que
el navegador tome la versión nueva y no la que tenía en caché.

## 7. Mantenimiento: reiniciar, apagar y actualizar

### Advertencia importante, vale para TODOS los comandos

Cada vez que escribas un comando `docker compose` contra este archivo, tiene
que llevar `--env-file .env.production`. Sin esa parte, Docker no lee las
contraseñas y arranca la base de datos con la contraseña vacía; la herramienta
falla después, de una forma confusa y difícil de diagnosticar. Es decir:

- Correcto: `docker compose --env-file .env.production -f docker-compose.prod.yml up -d`
- **Incorrecto**: `docker compose -f docker-compose.prod.yml up -d`

Ubícate siempre en la carpeta donde copiaste los archivos antes de ejecutar
cualquiera de estos comandos.

### Qué sistema operativo usar en el servidor

Recomendamos **Ubuntu Server (o cualquier Linux) con Docker Engine**, no
Windows. En Windows, Docker solo funciona con Docker Desktop, que necesita que
haya una sesión de usuario abierta en la máquina: si el servidor se reinicia
solo (por una actualización, un corte de luz, etc.) y nadie inicia sesión, los
contenedores **no vuelven a arrancar** y la herramienta queda caída sin que
nadie se entere. En Linux con Docker Engine eso no pasa: el servicio arranca
solo con la máquina.

Si por políticas internas tiene que ser Windows sí o sí, entonces hay que
configurar Docker Desktop para que se inicie automáticamente al iniciar sesión
(Settings → General → "Start Docker Desktop when you sign in"), y dejar la
sesión del usuario iniciada en el servidor.

### Reiniciar la herramienta

```
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Este mismo comando sirve tanto para levantar todo como para reiniciar lo que
esté caído: Docker deja como están los contenedores que ya funcionan bien.

### Apagar la herramienta

```
docker compose --env-file .env.production -f docker-compose.prod.yml down
```

Esto apaga los contenedores sin borrar nada: los documentos y la base de datos
quedan guardados y vuelven a estar disponibles al levantarla de nuevo.

### Actualizar a una versión nueva

Cuando el equipo de desarrollo avise que hay una versión nueva:

```
docker compose --env-file .env.production -f docker-compose.prod.yml pull
```

```
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Si la actualización incluye cambios en la base de datos, el equipo de
desarrollo te lo indicará y habrá que repetir el comando de `alembic upgrade
head` de la sección 4.

Si el equipo de desarrollo avisa que la versión trae una **fuente nueva**,
después de actualizar hay que correr una vez el sembrado del catálogo para
que esa fuente aparezca en el listado dentro de la herramienta:

```
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed
```

Es seguro repetirlo aunque ya se haya corrido.

## 8. Respaldos (copias de seguridad)

Esta herramienta guarda dos cosas que conviene respaldar periódicamente: la
base de datos (usuarios, metadatos de cada documento) y los documentos en sí
(los archivos). Recomendamos un respaldo diario, automático, guardado en un
disco o servidor **distinto** al de esta máquina — un respaldo que vive en el
mismo servidor no sirve de nada si ese servidor falla.

Ubícate en la carpeta donde copiaste los archivos (sección 2) y crea ahí una
subcarpeta llamada `respaldos`.

### Windows: crea el archivo `respaldo-iurisync.bat`

```bat
@echo off
set FECHA=%date:~-4%-%date:~3,2%-%date:~0,2%
cd /d C:\iurisync
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres pg_dump -U iurisync iurisync > respaldos\bd_%FECHA%.sql
docker compose --env-file .env.production -f docker-compose.prod.yml cp minio:/data respaldos\documentos_%FECHA%
```

(Ajusta `C:\iurisync` si copiaste los archivos en otra carpeta.) Luego, en el
Programador de tareas de Windows (Task Scheduler), crea una tarea nueva que
ejecute ese archivo todos los días, por ejemplo a las 2:00 a.m.

### Linux: crea el archivo `respaldo-iurisync.sh`

```bash
#!/bin/bash
FECHA=$(date +%F)
cd /opt/iurisync
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres pg_dump -U iurisync iurisync > respaldos/bd_$FECHA.sql
docker compose --env-file .env.production -f docker-compose.prod.yml cp minio:/data respaldos/documentos_$FECHA
```

(Ajusta `/opt/iurisync` si copiaste los archivos en otra carpeta.) Dale
permiso de ejecución (`chmod +x respaldo-iurisync.sh`) y agrégalo al cron para
que corra todos los días, por ejemplo a las 2:00 a.m.:

```
0 2 * * * /opt/iurisync/respaldo-iurisync.sh
```

### Un paso más: sácalos de esta máquina

Los comandos de arriba dejan los respaldos dentro de la misma carpeta
`respaldos`, en la misma máquina — eso ya protege contra un error humano o de
la aplicación, pero no contra una falla del servidor completo. Complementa
esto copiando esa carpeta `respaldos` periódicamente a otro disco, a otro
servidor de la oficina, o a donde ya respalden el resto de la información de
la empresa.

### Si alguna vez hay que restaurar un respaldo

Restaurar es una operación delicada (puede sobreescribir datos actuales) —
si llega a necesitarse de verdad, contacta al equipo de desarrollo antes de
ejecutar nada, con la fecha del respaldo que quieres restaurar a la mano.

## 9. Carpeta para "Descarga masiva de Decretos de Cali" (opcional)

Dentro de la herramienta, en **Laboratorio → Decretos Cali**, un administrador
puede bajar de una vez los ~72.000 decretos de la Alcaldía de Cali. Esos PDF se
guardan en una carpeta **de la máquina servidor** (no del computador de quien
usa la herramienta). Ocupan del orden de **5 a 30 GB** y la descarga tarda
varias horas.

Como la herramienta corre dentro de Docker, no ve las carpetas del servidor por
su cuenta: hay que indicarle una. Ya viene preparada:

- Por defecto, los PDF caen en una subcarpeta **`descargas`** dentro de la
  misma carpeta donde copiaste los archivos de instalación (por ejemplo
  `C:\iurisync\descargas`). Docker la crea sola la primera vez.
- Si esa unidad no tiene 30 GB libres, edita `.env.production` y cambia la
  línea `CALI_DESCARGAS_DIR` a otra carpeta con espacio, con **barras
  normales**, por ejemplo:

  ```
  CALI_DESCARGAS_DIR=D:/descargas-cali
  ```

  Luego aplica el cambio con:

  ```
  docker compose --env-file .env.production -f docker-compose.prod.yml up -d api worker
  ```

- **En el campo "Carpeta de destino" de la herramienta se escribe `/descargas`**
  (así, con barra al inicio), o una subcarpeta nueva como `/descargas/lote-2026`
  — la herramienta la crea sola. No se escribe la ruta de Windows.

Cuando termine, los PDF quedan en esa carpeta del servidor organizados como
`DECRETOS\ALCACALI\{año}\...`. Desde ahí, cópialos a donde deban vivir (por
ejemplo el disco de red `O:`) con el Explorador de Windows o un `robocopy`.

## 10. Notas por fuente

### Aviso "fuentes que pueden estar fallando"

Una fuente puede dejar de traer documentos sin que ninguna corrida marque
error: por ejemplo, si el sitio oficial deja de publicar en el lugar donde
IURISYNC busca (le pasó a la Corte Suprema en 2026). Para no depender de que
alguien lo note a mano, la herramienta compara cada fuente activa con su
propia historia del último año y avisa en dos casos:

- **Sin novedades:** lleva mucho más tiempo de lo normal sin ningún documento
  nuevo. "Lo normal" se calcula por fuente: a una que publica a diario se le
  avisa a los 14 días; a un boletín mensual, a los 60 aproximadamente.
- **Trae muy poco:** sigue llegando algo, pero menos de la cuarta parte de lo
  que suele traer en el mismo número de días. Solo aplica a fuentes que traen
  al menos 20 documentos al mes; en las más pequeñas, un mes flojo no
  significa nada.

Las fuentes con alerta aparecen en un recuadro al inicio del **Dashboard** y,
en la página **Fuentes**, con la marca "Revisar" junto a la fecha de su último
documento. Las fuentes inactivas no se vigilan, y una fuente sin historia
suficiente (menos de 6 días con documentos en el último año) no genera aviso.

El aviso es una señal para revisar, no una falla confirmada: puede ser que el
sitio de verdad no haya publicado (por ejemplo, durante la vacancia judicial
de diciembre y enero las cortes casi no publican). Si una fuente aparece en
alerta, conviene revisar primero si su sitio oficial tiene documentos más
recientes que los que tiene IURISYNC. Si todas las fuentes aparecen en alerta
a la vez, lo más probable es que las corridas diarias no se estén ejecutando.

### Superintendencia Nacional de Salud (`supersalud`)

- **Qué trae:** tres secciones del portal jurídico de la Supersalud —
  **Resoluciones**, **Circulares Externas** y el **Boletín Jurídico** (la
  publicación trimestral que recopila los conceptos jurídicos del periodo;
  cada boletín entra como un documento, su PDF completo). Las Actas de
  Conciliación quedan fuera.
- **Desde cuándo:** año 2015 en adelante.
- **Cómo quedan nombrados los documentos:** con un código corto del tipo
  `R_SNS_1234_2024` (una Resolución) o `C_SNS_0006_2016` (una Circular
  Externa) — la letra indica el tipo, el número es el consecutivo del acto
  y el último bloque es el año de publicación. Cuando el número no se puede
  determinar con certeza, el documento entra con su título original y queda
  marcado como "sin verificar" para que alguien lo revise a mano. Los anexos
  entran como documentos aparte, con el sufijo `_A01`. Los boletines usan
  `BOL_SNS_0074_ENE-MAR_2026` — número del boletín, trimestre y año.
- **Detalle técnico:** el Boletín Jurídico se obtiene de una lista de
  SharePoint en `docs.supersalud.gov.co` que responde por API sin el bloqueo
  ni el "vale de seguridad" que necesitan las otras dos secciones.
- **Fuente nueva:** después de actualizar a la versión que la incluye hay
  que correr una vez el sembrado del catálogo para que aparezca en el
  listado de fuentes:

  ```
  docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed
  ```

  Es seguro repetirlo.

### Superintendencia del Subsidio Familiar (`ssf`)

Una sola fuente que raspa **tres** secciones:

1. **Resoluciones** y **Circulares Externas** del portal `www.ssf.gov.co`
   (Liferay servido entero en HTML — sin API, sin filtros). Cobertura desde
   2024 (las circulares anteriores a 2011 tienen enlaces de descarga que ya
   no funcionan). Descargas desde `www.ssf.gov.co/documents/d/guest/...`.
   Títulos: `{C|R}_SSF_{número}_{año}`.
2. **Conceptos** jurídicos de la Relatoría (`juridica.ssf.gov.co`), sitio
   ASP.NET aparte. Cobertura desde 2015 (en la práctica trae todo; el dato
   más viejo es de 2017). No tiene paginación: una búsqueda por rango de
   fechas devuelve todo el catálogo (~1.000 conceptos) en una sola
   respuesta, y el servidor filtra por fecha de verdad, así que las corridas
   diarias son baratas. Los PDF se descargan de
   `juridica.blob.core.windows.net/juridica-documentos/...`.
   Títulos: `CTO_SSF_{consecutivo}_{año}`, tomados del **nombre del PDF de
   respuesta** (el radicado que muestra la tabla a veces es el de la
   consulta de entrada, no el del concepto). El radicado de la tabla queda
   guardado en el campo "detalle".

Cuando el número/radicado no se puede determinar, el documento entra con el
título crudo y marca de "no verificado".

**Certificados:** `www.ssf.gov.co` tiene la cadena TLS incompleta y la
familia se salta la validación para ese host (igual que `constitucional` y
`cndj`). `juridica.ssf.gov.co` y el almacén de PDF de conceptos **sí**
tienen certificado válido y se validan normalmente.

**Fuente nueva / sección nueva:** después de actualizar producción hay que
correr una vez
`docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`
para refrescar la descripción en el listado. Es seguro repetirlo.

### Superintendencia de Notariado y Registro (`snr`)

Una sola fuente que raspa dos categorías del portal WordPress de la SNR:
**Circulares** y **Resoluciones**. Cobertura desde 2015. Los documentos se
descargan de `servicios.supernotariado.gov.co/files/…`.

Particularidad: el listado del sitio **no tiene paginación** y corta duro en
20 tarjetas por búsqueda, sin importar cuántos resultados diga tener. Para no
perder documentos, la familia enumera el catálogo con muchas búsquedas `POST`
por prefijo del número de la norma, partiendo cada bloque hasta que la
respuesta alcanza a mostrar todo lo que el sitio reporta.

Por eso el **backfill completo** (rango amplio) recorre el catálogo con
muchas búsquedas y puede tardar bastante (decenas de minutos); una corrida
**incremental** vuelve a enumerar el año en curso de ambas categorías, así
que tampoco es instantánea. Hay un tope interno de búsquedas por categoría
para que una corrida no se dispare: si se alcanza, la corrida termina con un
error visible avisando que los resultados quedaron incompletos.

Se saltan las tarjetas sin archivo adjunto (las "notificación por aviso") y se
informa cuántas fueron. La fecha que manda es la de **publicación** del sitio
(no la de firma de la norma, que puede ser bastante anterior).

**Cobertura de las Circulares antiguas.** La enumeración por prefijo se apoya
en el código `CIR-AAAA-NNNNNN`, que la SNR sólo empezó a usar hacia 2025. Las
circulares anteriores (2015–2024) son texto libre ("Circular No. 123 de
2018") y el buscador del sitio nunca muestra más de 20 por año, sin "página
siguiente". Resultado práctico:

- **Resoluciones:** completas desde 2015.
- **Circulares 2025 en adelante** (y futuras): completas.
- **Circulares 2015–2024:** parciales — sólo entran las ~20 más recientes que
  el sitio alcanza a mostrar por cada año. La corrida deja un aviso visible
  ("… sólo muestra 20 …") en esos años.

Títulos: `{C|R}_SNR_{número}_{año}` (desde el código `CIR-AAAA-NNNNNN` /
`RES-AAAA-NNNNNN`). Los documentos viejos sin ese código entran con el
título crudo y marca de "no verificado".

Particularidad técnica: el certificado de seguridad de la SNR está mal
configurado, tanto en `www.supernotariado.gov.co` (donde se buscan los
documentos) como en `servicios.supernotariado.gov.co` (de donde se bajan los
archivos), así que la familia se salta esa validación en ambos, igual que
otras fuentes `.gov.co` como `ssf`, `constitucional` y `cndj`.

**Fuente nueva:** después de actualizar producción hay que correr una vez
`docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
Es seguro repetirlo.

### Superintendencia de Sociedades (`supersociedades`)

- **Qué trae:** dos boletines de recopilación de conceptos — el **Boletín
  Jurídico** (mensual) y el **Boletín Contable** (semestral). Cada boletín
  entra como un documento: su PDF completo.
- **Desde cuándo:** una corrida completa (2015 en adelante) trae hoy **110
  boletines jurídicos y 10 contables**. No es "todo lo publicado", porque la
  propia Supersociedades tituló muchos boletines viejos sin decir de qué mes o
  de qué año son:
  - **Jurídico:** 2015, 2016, 2022, 2023 y 2025 entran completos (12 al año);
    2024 entra con 10; de 2017 a 2021 entra sólo una parte (entre 3 y 8 al
    año). Lo que falta de esos años son boletines cuyo título en la página no
    trae el mes o el año y cuyo archivo PDF tampoco lo dice (por ejemplo
    `BoletinJuridico-Agosto.pdf` o `CONCEPTOS JURIDICOS_04.pdf`): no hay forma
    de fecharlos y quedan fuera.
  - **Contable:** desde el segundo semestre de 2021 en adelante, completo. Los
    tres boletines contables anuales de 2017, 2018 y 2020 no dicen a qué
    semestre corresponden, así que tampoco se pueden fechar y quedan fuera.
  - La lista de la página mezcla además una veintena de guías, libros y
    revistas que no son boletines. Se descartan a propósito; la corrida lo
    resume en una sola línea ("20 entradas … sin PDF de boletín, omitidas") en
    vez de ensuciar el informe con un aviso por cada una.
- **Cómo quedan nombrados:** `BOL_SS_AGO_2026` (jurídico: mes y año) y
  `BOL_SS_SI_2026` / `BOL_SS_SII_2026` (contable: semestre y año). Cuando el
  título de la página no trae el período, se lee del nombre del archivo PDF
  (así entran, por ejemplo, los mensuales de 2019 a 2021). Si dos boletines
  distintos caen en el mismo mes —pasa en 2014, con el jurídico y el del grupo
  de reorganización— el segundo entra con su título original de la página y
  marca de "sin verificar", para que no se pisen el archivo entre ellos.
- **Detalle técnico:** portal Liferay con certificado válido (no hace falta
  saltarse la validación). La lista de cada sección viene entera en la página
  (sin paginación); el enlace al PDF está dentro de cada boletín, así que la
  fuente abre cada boletín que caiga en el rango de fechas pedido, más los que
  no traen fecha en el título (para buscarla en el nombre del archivo). Una
  corrida completa abre unas 175 páginas y descarga cerca de 1 GB de PDF.
- **Fuente nueva:** después de actualizar producción hay que correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`
  para que aparezca en el listado. Es seguro repetirlo.

### Superintendencia de la Economía Solidaria (`supersolidaria`)

- **Qué trae:** cinco secciones del sitio jurídico de la Supersolidaria —
  **Resoluciones generales**, **Circulares externas**, **Circulares
  conjuntas**, **Cartas circulares** y **Conceptos jurídicos y contables**.
  Cada archivo entra como un documento; los anexos (incluidos los `.xlsx` /
  `.doc`) entran aparte con el sufijo `_A01`, `_A02`, `_A03`… según cuántos
  cuelguen de la misma circular.
- **Desde cuándo:** año 2015 en adelante.
- **Cuánto entrega hoy:** unos 570 documentos — cerca de 220 resoluciones, 260
  circulares externas, 60 cartas circulares y 18 conceptos. **Circulares
  conjuntas no entrega nada:** el sitio sólo tiene ahí 6 archivos de 2001 a
  2009, sin fecha publicada y por debajo del piso de 2015. La sección se
  consulta igual (por si publican material nuevo) y avisa en el registro con
  una sola línea "0 documentos".
- **Cómo quedan nombrados:** `R_SES_7935_2025` y `R_SES_8525_2024`
  (resolución: el número son los **últimos seis dígitos del radicado**, sin los
  ceros de la izquierda), `CE_SES_0102_2026` (circular externa),
  `CC_SES_0037_2026` (carta circular), `CTO_SES_<radicado>_2026` (concepto).
  Cuando no se puede determinar el número, el documento entra con su título
  original y marca de "sin verificar" (hoy, unos 150 de los 570).
- **Ojo con las fechas:** cerca de **un tercio de los documentos queda
  archivado con fecha 1 de enero de su año** — son las circulares y cartas
  viejas, cuya fecha exacta el sitio no publica en ninguna parte, así que sólo
  se conoce el año. Por eso **conviene correr el backfill por años completos**
  (por ejemplo 1 de enero a 31 de diciembre): un rango más corto que el año se
  salta en silencio todos esos documentos.
- **Detalle técnico:** sitio Drupal cuyo certificado llega **incompleto** (le
  falta el certificado intermedio), así que —igual que en la SSF, la SNR, la
  Corte Constitucional y la CNDJ— la fuente se salta la validación del
  certificado; sin eso el sitio no responde y la fuente entrega 0 documentos.
  Las 4 primeras secciones traen todo en una sola página; resoluciones,
  circulares externas y cartas circulares vienen agrupadas por año (circulares
  conjuntas no). Conceptos es una lista paginada, y los conceptos cuyo PDF no
  empieza por `AAAAMMDD_` (≈1 de cada 3 de esa sección) se omiten con aviso
  porque no hay de dónde sacarles la fecha.
- **Fuente nueva:** después de actualizar producción, correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
  Es seguro repetirlo.

### Procuraduría General de la Nación (`procuraduria`)

- **Qué trae:** dos secciones de la Relatoría de la Procuraduría
  (`apps.procuraduria.gov.co/relatoria`) — **Normativa** (resoluciones,
  directivas, circulares, memorandos, instructivos…) y **Conceptos** (SIREL,
  tipos "CONCEPTO" y "CONCEPTO (MISIONAL)"). La página de SharePoint
  `normatividad.aspx` es solo un marco vacío; el contenido real es esa
  aplicación.
- **Qué no trae:** los enlaces de Normativa que apuntan a normas de otras
  entidades (leyes en la página del Senado, decretos de Presidencia,
  resoluciones de MinSalud…) — solo los documentos alojados por la
  Procuraduría.
- **Desde cuándo:** año 2015 en adelante.
- **Cuánto entrega hoy:** unos 537 documentos de Normativa y unos 8.000–9.000
  conceptos (≈600–800 por año). La primera corrida completa de conceptos es
  larga; las siguientes solo traen lo nuevo.
- **Cómo quedan nombrados:** `R_PGN_0338_2025` (resolución), `DIR_PGN_0021_2025`
  (directiva, directiva conjunta y directiva unificada), `C_PGN_0012_2025`
  (circular, circular conjunta y circular externa), `M_PGN_0002_2026`
  (memorando), `CCIR_…` (carta circular), `INS_…` (instructivo), `A_…`
  (acuerdo), `PRO_…` (protocolo), `MAN_…` (manual); el decreto usa
  el código común de ministerios (`D0262000`). Conceptos:
  `CTO_PGN_0000236_2026` (consecutivo a 7 dígitos + año); sin número:
  `CTO_PGN_SN245408_2025` (número interno de SIREL). Cada dependencia numera
  por su cuenta, así que cuando dos documentos distintos dan el mismo nombre
  los siguientes llevan `_2`, `_3` (el más antiguo en el sistema de la
  Procuraduría queda sin sufijo).
- **Ojo:** ambos buscadores muestran un reCAPTCHA que hoy el servidor no
  exige para las consultas que usa la fuente. Si algún día lo exige, la
  corrida mostrará errores "Error consultando Normativa/Conceptos …" con 0
  documentos: en ese caso **se pausa la fuente** (no se intenta saltar el
  reCAPTCHA).
- **Detalle técnico:** el sitio donde se consulta (`apps.procuraduria.gov.co`)
  entrega su certificado de seguridad incompleto, así que —igual que en la
  SSF, la SNR, Supersolidaria, la Corte Constitucional y la CNDJ— la fuente
  se salta la validación del certificado para esas consultas; sin eso el
  sitio no responde y la fuente entrega 0 documentos. Las descargas de los
  documentos sí se hacen con la validación normal: los enlaces de Normativa
  que el sitio publica en `apps.procuraduria.gov.co` dan error, así que la
  fuente los descarga siempre desde `www.procuraduria.gov.co`, que valida su
  certificado sin problema. Los conceptos llegan en Word (.doc/.docx).
- **Ojo con los conceptos:** la Procuraduría publica cada concepto en su
  sistema (SIREL) varios meses después de la fecha del concepto —
  típicamente entre 2 y 7 meses, y a veces más de un año—. Por eso la
  corrida automática diaria (que solo mira los últimos días) casi nunca va a
  traer conceptos nuevos: en la práctica traerá sobre todo Normativa. Para
  mantener los conceptos al día, hay que correr esta fuente a mano una vez
  al mes, pidiendo el año en curso y el anterior completos (por ejemplo, del
  1 de enero del año pasado a hoy); los documentos que ya se descargaron
  antes no se vuelven a descargar.
- **Duplicados raros:** si la Procuraduría vuelve a subir un concepto
  corregido, puede aparecer dos veces con el mismo nombre. Es poco frecuente;
  se detecta a simple vista en la lista de documentos y se borra a mano.
- **Fuente nueva:** después de actualizar producción, correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
  Es seguro repetirlo.

### Ministerio de Salud y Protección Social (`minsalud`)

- **Qué trae:** las cuatro secciones de normativa del sitio del Ministerio —
  **Resoluciones**, **Circulares**, **Conceptos jurídicos** y **Boletines
  jurídicos** (uno por mes). Las cuatro páginas del sitio muestran una sola
  biblioteca de documentos; la fuente la lee completa de una vez.
- **Desde cuándo:** año 2015 en adelante.
- **Cuánto entrega hoy:** unos 2.900 documentos — cerca de 1.480
  resoluciones, 330 circulares, 950 conceptos y 140 boletines.
- **Cómo quedan nombrados:** `R_MSPS_1809_2026` (resolución),
  `C_MSPS_0031_2026` (circular: externa, interna, conjunta o de la Comisión
  de Precios de Medicamentos), `CTO_MSPS_201711601019341_2017` (concepto: su
  número de radicado + año), `BOL_MSPS_MAY_2016` (boletín: mes + año). Cuando
  dos documentos distintos dan el mismo nombre (pasa en ~30 casos: el mismo
  documento subido dos veces, versiones "con anexo técnico", o series
  distintas con el mismo número) los siguientes llevan `_2`, `_3`. Si un
  documento no trae número reconocible queda como `…_SN{número interno}_año`
  con un aviso en el registro (hoy 2 casos).
- **Ojo con las fechas:** resoluciones y circulares traen fecha publicada
  desde 2023; conceptos y boletines casi nunca la traen. Para esos y para los
  documentos anteriores a 2023, la fuente usa la fecha escrita en la
  descripción, o si no, la fecha en que el Ministerio subió el archivo. Los
  documentos de fin de año que el Ministerio sube en enero quedan con fecha
  31 de diciembre de su propio año (para que la corrida diaria no se los
  pierda); si ninguna fecha sirve, quedan con el 1 de enero. Por eso, para
  años viejos, conviene correr la fuente por año completo.
- **Corrida diaria:** esta fuente mira los últimos 60 días (no solo los
  últimos días), porque el Ministerio a veces sube los documentos semanas
  después de su fecha.
- **Detalle técnico:** el sitio web del Ministerio es muy lento (las páginas
  tardan minutos), pero la fuente no las usa: consulta directamente la lista
  de documentos, que responde en segundos. Certificado válido.
- **Fuente nueva:** después de actualizar producción, correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
  Es seguro repetirlo.

### Corte Suprema de Justicia (`corte_suprema`)

- **De dónde saca los documentos:** del buscador oficial de providencias de
  la Corte (consultaprovidencias.cortesuprema.gov.co). Lee las cuatro salas
  (Tutelas, Laboral, Civil y Penal), de la más nueva a la más vieja.
- **Fallas pasajeras de la Corte:** el buscador de la Corte a veces responde
  mal a una consulta suelta (se midió alrededor de 1 de cada 180). La fuente
  vuelve a intentar hasta 3 veces, con 5 segundos de espera entre intentos,
  antes de darse por vencida. Solo si los 3 intentos fallan queda un error
  en la corrida, y esa sala queda incompleta en esa corrida. Si la Corte
  rechaza la consulta de plano (un error que no es del servidor), no se
  reintenta y el error aparece de inmediato.
- **Si la fuente deja de traer documentos:** primero hay que revisar si la
  Corte está cargando providencias nuevas en su buscador. En octubre de 2026
  se confirmó que la Corte había dejado de cargarlas: lo último en Tutelas,
  Laboral y Civil era del 30 de abril de 2026, y en Penal de finales de
  julio. Desde entonces solo aparecían algunos documentos viejos editados,
  el último el 15 de septiembre. No era una falla de IURISYNC ni del
  certificado (válido hasta marzo de 2027). Cuando la Corte se ponga al día,
  conviene lanzar una corrida manual desde el 30 de abril de 2026, porque la
  corrida diaria solo mira los últimos 3 días.

### Tribunales Superiores (`rama_judicial`)

- **Cómo quedan nombrados:** `T_{TRIBUNAL}_{radicado}`, por ejemplo
  `T_HUIL_41001_31_05_002_2021_00031_01`. Todos los documentos del mismo
  proceso llevan el mismo nombre, y la herramienta los agrupa como
  actuaciones del mismo caso.
- **De dónde sale el radicado:** primero del nombre del archivo, esté donde
  esté y aunque venga con guiones o espacios (`19. 41001-31-05-002-…`,
  `Auto 11001 31 10 013 …`). Si el nombre no lo trae completo, se lee de la
  primera página del PDF ("Radicación: …"). Del PDF solo se toma cuando no hay
  duda: si el nombre trae el número corto (`2022-00078-01`), el radicado del
  PDF debe terminar igual; si no, el PDF debe traer un único radicado.
- **Qué se queda con el nombre original:** las listas de Estados y Edictos
  del día (son de varios procesos a la vez) y los documentos donde el
  radicado es dudoso. En una muestra real de octubre de 2026, quedaba con
  nombre correcto cerca del 86% de lo que antes quedaba sin formato.
- **Corrección de lo ya guardado (una sola vez):** después de actualizar a la
  versión que trae este cambio, correr primero en modo simulación (solo
  cuenta, no cambia nada):

  ```
  docker compose --env-file .env.production -f docker-compose.prod.yml run --rm worker python -m core.backfill_tribunales_titulos --simular
  ```

  y luego de verdad:

  ```
  docker compose --env-file .env.production -f docker-compose.prod.yml run --rm worker python -m core.backfill_tribunales_titulos
  ```

  Lee el PDF de cada documento sin formato, así que puede tardar del orden de
  una hora. Se puede repetir sin riesgo: lo ya corregido no se vuelve a tocar.
  Al terminar muestra cuántos se corrigieron por el nombre, cuántos por el
  PDF y cuántos quedaron igual.
