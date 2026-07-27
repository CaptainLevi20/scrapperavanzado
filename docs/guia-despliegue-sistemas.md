# Guía de instalación de IURISYNC — para el equipo de sistemas

Esta guía no requiere conocimientos de programación. Sigue los pasos en orden.
Si algo no funciona como se describe aquí, detente en ese paso y avisa al
equipo de desarrollo antes de continuar.

## 1. Antes de empezar: qué necesitamos de tu parte

- [ ] Una máquina (física o virtual) **dentro de la red de la oficina**, con
      al menos: 4 núcleos de procesador, 8 GB de memoria RAM, 100 GB de disco.
- [ ] Docker instalado en esa máquina. Si no lo tienen, instrucciones oficiales
      aquí: https://docs.docker.com/engine/install/
- [ ] El nombre exacto del subdominio interno que van a usar (ejemplo:
      `documentos.avancejuridico.com.co`), y que su DNS interno ya apunte
      ese nombre a la IP de esta máquina.
- [ ] Confirmar: ¿tienen una autoridad certificadora (CA) interna propia para
      emitir certificados HTTPS? Si no están seguros, la respuesta por
      defecto es "no" y esta guía funciona igual (ver sección 5).
- [ ] Una regla de firewall que permita tráfico normal de navegación
      (puertos 80 y 443) desde la red de la oficina hacia esta máquina.

## 2. Copiar los archivos a la máquina

El equipo de desarrollo te entrega una carpeta comprimida con estos archivos.
Descomprímela en una carpeta de tu elección en el servidor, por ejemplo
`C:\iurisync\` o `/opt/iurisync/`:

- `docker-compose.prod.yml`
- `Caddyfile`
- `.env.production.example`
- `frontend/dist/` (carpeta ya compilada, no requiere Node.js)

## 3. Configurar las variables de producción

Copia `.env.production.example` a un archivo nuevo llamado `.env.production`,
en la misma carpeta. Ábrelo con un editor de texto simple (Bloc de notas
sirve) y reemplaza cada valor que dice `CAMBIAR_ESTO` por uno propio:

- `CADDY_DOMAIN` y `CORS_ORIGINS`: el subdominio interno real (el mismo en
  ambas líneas).
- `POSTGRES_PASSWORD` y la contraseña dentro de `DATABASE_URL`: deben ser
  **exactamente la misma contraseña**, elegida por ustedes, en ambos lugares.
- `S3_ACCESS_KEY` / `S3_SECRET_KEY`: un usuario y contraseña nuevos, elegidos
  por ustedes, para el almacenamiento de documentos.
- `REGISTRATION_CODE`: el código que cada persona del equipo va a usar para
  crear su cuenta la primera vez. Compártanlo solo con quienes deban tener
  acceso.

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
docker compose --env-file .env.production -f docker-compose.prod.yml up -d api worker beat caddy
```

Para confirmar que todo quedó corriendo:

```
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Deberías ver 7 servicios, todos en estado `running` o `healthy`. Si alguno
dice `restarting` repetidamente, avisa al equipo de desarrollo con el
resultado de este comando (reemplaza `api` por el nombre del servicio que
falla):

```
docker compose --env-file .env.production -f docker-compose.prod.yml logs api
```

## 5. Sobre el candado de seguridad (HTTPS)

Por defecto, esta instalación genera su propio certificado de seguridad
("candado casero"). La primera vez que alguien entre desde el navegador al
subdominio, va a ver una advertencia tipo "conexión no privada" o "sitio no
verificado" — es normal, hay que darle click en "Avanzado" y luego
"Continuar de todos modos" (el texto exacto varía según el navegador). Una
vez aceptado, el navegador no debería volver a preguntar en esa misma
máquina.

Si su empresa sí tiene una autoridad certificadora interna propia, avisen al
equipo de desarrollo — se puede reemplazar este certificado casero por uno
oficial de la empresa, sin necesidad de rehacer el resto de la instalación.

## 6. Verificación final

Desde un computador conectado a la red de la oficina, abre un navegador y
entra a `https://` seguido del subdominio configurado (ejemplo:
`https://documentos.avancejuridico.com.co`). Deberías ver la pantalla de
inicio de sesión de IURISYNC. Usa el `REGISTRATION_CODE` que configuraste en
el paso 3 para crear la primera cuenta desde la pantalla de registro.

Si la página no carga, revisa en este orden: (1) que el DNS interno
realmente apunte al servidor (`ping <subdominio>` desde otro computador de la
oficina), (2) que el firewall deje pasar el puerto 443, (3) el resultado del
comando `docker compose ... ps` del paso 4.
