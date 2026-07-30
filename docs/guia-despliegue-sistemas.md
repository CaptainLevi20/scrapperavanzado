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
      oficina: o un nombre de dominio interno con su DNS ya apuntando a la
      IP de esta máquina, o — si no tienen servidor de DNS/dominio, que es
      lo más común — simplemente **la IP interna fija de esta máquina**
      (ejemplo: `192.168.1.50`). No hace falta nada más: la guía funciona
      igual de bien con una IP que con un nombre.
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

- `CADDY_DOMAIN` y `CORS_ORIGINS`: el subdominio interno real, o la IP
  interna fija de la máquina si no tienen dominio (ejemplo: `CADDY_DOMAIN=192.168.1.50`
  y `CORS_ORIGINS=https://192.168.1.50`) — la misma dirección en ambas líneas.
- `S3_PUBLIC_ENDPOINT_URL`: la misma dirección otra vez (subdominio o IP),
  pero terminada en `:9443` (ejemplo: `https://documentos.avancejuridico.com.co:9443`
  o `https://192.168.1.50:9443`). Es la dirección por la que el navegador de
  cada persona descarga los documentos.
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

Desde un computador conectado a la red de la oficina, abre un navegador y
entra a `https://` seguido del subdominio o la IP configurada (ejemplo:
`https://documentos.avancejuridico.com.co` o `https://192.168.1.50`).
Deberías ver la pantalla de inicio de sesión de IURISYNC. Usa el
`REGISTRATION_CODE` que configuraste en el paso 3 para crear la primera
cuenta desde la pantalla de registro.

Si la página no carga, revisa en este orden: (1) que la dirección
configurada realmente llegue al servidor (`ping <subdominio o IP>` desde
otro computador de la oficina — si usan subdominio, que además el DNS
interno lo resuelva a la IP correcta), (2) que el firewall deje pasar el
puerto 443, (3) el resultado del comando `docker compose ... ps` del paso 4.

Por último, **abre un documento** desde la herramienta (no basta con verlo en
la lista: hay que darle click para descargarlo o previsualizarlo). Si la
página carga y el listado se ve, pero al abrir un documento sale un error o la
descarga nunca empieza, casi siempre es una de estas tres cosas: el puerto
**9443** está cerrado en el firewall, `S3_PUBLIC_ENDPOINT_URL` en
`.env.production` no quedó con el subdominio o la IP correcta terminada en
`:9443`, o (si están en **Firefox**) todavía no se aceptó la advertencia de
seguridad en esa segunda dirección — ver el aviso de Firefox en la sección 5.

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
