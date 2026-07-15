# Previsualizador de documentos — Diseño

Fecha: 2026-07-15

## Contexto y objetivo

Hoy, para saber si un documento descargado es útil, hay que descargarlo (botón "Descargar") y abrirlo en el visor de PDF del sistema operativo, y luego volver a la pestaña de IURISYNC para marcarlo como "Útil"/"No útil" en la tabla de Documentos. Este diseño agrega un previsualizador inline: un botón "Previsualizar" por fila abre un modal con el documento renderizado ahí mismo, junto con los botones de marcar — permitiendo revisar y marcar sin salir de la aplicación, y sin perder el filtro/página actual de la tabla.

Explícitamente en alcance:
- Botón "Previsualizar" (ícono de ojo) por fila, junto al botón "Descargar" existente.
- Modal con el PDF renderizado inline (usando el visor nativo del navegador vía `<iframe>`).
- Fallback para tipos de archivo que el navegador no puede previsualizar nativamente (Word, RTF): mensaje + botón de descarga dentro del mismo modal.
- Botones Útil / No útil dentro del modal, que marcan el documento **y avanzan automáticamente** al siguiente de la lista actualmente cargada en la tabla.
- Botón "Siguiente" para saltar al próximo documento sin marcarlo (sin cambiar su `review_status`).
- Botón "Anterior" para retroceder un documento en la lista actual (simetría con "Siguiente").

Explícitamente fuera de alcance:
- Cambios de backend — el endpoint `/documents/{id}/download` ya existente (autenticado, redirige a una URL firmada de MinIO) se reutiliza tal cual.
- Navegación cruzando páginas de la tabla (si se llega al final de los documentos cargados en la página actual, el modal se cierra; para seguir revisando hay que cambiar de página en la tabla y volver a abrir el previsualizador).
- Previsualización real de Word/RTF (conversión a PDF, visor de Office, etc.) — se limita a PDF, con un mensaje honesto de "no disponible" para el resto.
- Atajos de teclado, zoom/controles de PDF más allá de los nativos del navegador.

## Arquitectura

Cambio puramente de frontend. El endpoint de descarga ya funciona (requiere `Authorization: Bearer <token>`, redirige a una URL firmada de MinIO); `downloadDocumentFile` en `api/documents.ts` ya sabe pedirlo con el token y convertir la respuesta en un `Blob`. Se extrae esa lógica de fetch a una función reutilizable y se agrega un componente de modal que la consume para renderizar el archivo en pantalla en vez de descargarlo.

### `api/documents.ts`

Nueva función:

```ts
export async function fetchDocumentBlob(id: number): Promise<Blob> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}/documents/${id}/download`, { headers });
  if (!response.ok) {
    throw new Error("No se pudo cargar el documento");
  }
  return response.blob();
}
```

`downloadDocumentFile` se reescribe para usar `fetchDocumentBlob` internamente en vez de duplicar el fetch, manteniendo su comportamiento actual (crear un enlace temporal y disparar la descarga).

### `DocumentPreviewDialog.tsx` (nuevo)

Recibe la lista de documentos actualmente cargados en la tabla (`Document[]`) y un índice inicial (`initialIndex: number`), más un callback `onOpenChange`. Mantiene internamente el índice del documento que se está mostrando (`currentIndex`).

Al montar o cuando cambia `currentIndex`:
1. Llama a `fetchDocumentBlob(document.id)`.
2. Si el `content_type` del documento es `"application/pdf"`, crea un `Object URL` del blob y lo usa como `src` de un `<iframe>`.
3. Si no, no crea ningún `Object URL` de renderizado — muestra el mensaje de "vista previa no disponible" con un botón que dispara `downloadDocumentFile` directamente.
4. Libera (`URL.revokeObjectURL`) el `Object URL` anterior cada vez que cambia de documento o el modal se cierra, para no acumular blobs en memoria.

Cabecera del modal: título, tipo, fecha de publicación del documento actual (mismos datos que ya se muestran en la fila de la tabla).

Pie del modal: botones Útil, No útil, Anterior, Siguiente — deshabilitados mientras hay una mutación de marcado en curso.

### `DocumentsPage.tsx`

Agrega un botón "Previsualizar" (ícono de ojo, mismo estilo que el botón "Descargar" existente) en cada fila. Al hacer clic, abre `DocumentPreviewDialog` pasándole `documentsQuery.data.items` y el índice de esa fila dentro del arreglo.

## Flujo de revisión rápida

- **Útil / No útil**: llama a `updateDocumentReviewStatus(id, status)` (ya existe, es la misma mutación que usan los botones de la tabla). Al resolver con éxito:
  - Si `currentIndex` no es el último de la lista, incrementa `currentIndex` (avanza al siguiente documento, dispara su fetch de blob).
  - Si era el último, cierra el modal (`onOpenChange(false)`).
  - Invalida la query `["documents"]` igual que ya hace `reviewMutation` en la tabla, para que al cerrar el modal la fila ya refleje el nuevo estado.
- **Siguiente**: incrementa `currentIndex` sin llamar a ninguna mutación (no cambia `review_status`). Deshabilitado si ya está en el último documento de la lista.
- **Anterior**: decrementa `currentIndex`. Deshabilitado si ya está en el primer documento de la lista.
- **Cerrar** (X del modal o Escape): cierra sin hacer ningún cambio adicional al documento actual.

## Manejo de errores

- **Falla al pedir el blob** (red, 404, sesión expirada): el modal muestra un mensaje inline ("No se pudo cargar la vista previa") con un botón "Reintentar" que vuelve a llamar a `fetchDocumentBlob` para el documento actual. El modal no se cierra solo.
- **Falla la mutación de marcar** (Útil/No útil): se muestra un mensaje de error dentro del modal (mismo texto/patrón que ya usa `DocumentsPage` para sus propios errores de marcado) con opción de reintentar. El modal **no avanza** al siguiente documento si la marca no se guardó — solo avanza tras una respuesta exitosa.
- **Documento no-PDF**: no es un error — es el camino esperado del fallback (mensaje + botón de descarga), no dispara ningún estado de error.

## Testing

- **`api/documents.test.ts`**: tests para `fetchDocumentBlob` — éxito devuelve un `Blob` con el contenido esperado; una respuesta no-OK (404) lanza un error. Mismo patrón MSW que ya usan los tests existentes de `downloadDocumentFile`.
- **`components/DocumentPreviewDialog.test.tsx`** (nuevo):
  - Abre con un documento `content_type: "application/pdf"` y verifica que se renderiza un `<iframe>` con el blob cargado.
  - Abre con un documento `content_type: "application/msword"` (u otro no-PDF) y verifica el mensaje de "vista previa no disponible" junto con un botón de descarga funcional.
  - Marcar "Útil" en un documento que no es el último de la lista: verifica que la mutación se llama con el `id` correcto y que el modal pasa a mostrar el siguiente documento (nuevo fetch de blob).
  - Marcar el **último** documento de la lista: verifica que el modal se cierra (`onOpenChange(false)` llamado).
  - "Siguiente" avanza al próximo documento sin invocar la mutación de marcado.
  - "Anterior" está deshabilitado en el primer documento, y "Siguiente" está deshabilitado en el último.
  - Una respuesta de error al pedir el blob muestra el mensaje de reintento; reintentar vuelve a pedir el blob.
- **`pages/DocumentsPage.test.tsx`**: agrega un caso que confirma que el botón "Previsualizar" de una fila abre `DocumentPreviewDialog` con el documento correcto (verificable por el título mostrado en la cabecera del modal).
