// Polyfill de `Promise.withResolvers` para navegadores anteriores a finales de
// 2023 (Chrome/Edge <119, Firefox <121, Safari <17.4). El visor de PDF
// (react-pdf / pdf.js) llama a esta función al abrir la previsualización; sin
// ella, el visor se cae con "Promise.withResolvers is not a function" y la
// previsualización deja de funcionar en esos navegadores, aunque el resto de la
// app sí ande. Se importa de primero en main.tsx para dejarla disponible antes
// de que se abra cualquier PDF.

type ConResolvers = {
  withResolvers?: <T>() => {
    promise: Promise<T>;
    resolve: (value: T | PromiseLike<T>) => void;
    reject: (reason?: unknown) => void;
  };
};

export function installPromiseWithResolvers(): void {
  const objetivo = Promise as unknown as ConResolvers;
  // Respeta la implementación nativa cuando el navegador ya la trae.
  if (typeof objetivo.withResolvers === "function") return;
  objetivo.withResolvers = function withResolvers<T>() {
    let resolve!: (value: T | PromiseLike<T>) => void;
    let reject!: (reason?: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  };
}

installPromiseWithResolvers();
