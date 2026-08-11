// Rellenos (polyfills) de funciones modernas de JavaScript para navegadores
// anteriores a mediados de 2024. El visor de PDF (react-pdf / pdf.js) usa varias
// de estas funciones; si el navegador no las trae, el visor se cae y la
// previsualización deja de funcionar, aunque el resto de la app sí ande. Este
// módulo se importa de primero en main.tsx para dejarlas disponibles antes de
// que se abra cualquier PDF. Al aparecer una función nueva sin soporte en un
// navegador viejo, se agrega aquí su relleno.

type ConResolvers = {
  withResolvers?: <T>() => {
    promise: Promise<T>;
    resolve: (value: T | PromiseLike<T>) => void;
    reject: (reason?: unknown) => void;
  };
};

// Promise.withResolvers — Chrome/Edge ≥119, Firefox ≥121, Safari ≥17.4.
export function installPromiseWithResolvers(): void {
  const objetivo = Promise as unknown as ConResolvers;
  if (typeof objetivo.withResolvers === "function") return; // ya nativo
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

type ConParse = {
  parse?: (url: string | URL, base?: string | URL) => URL | null;
};

// URL.parse — Chrome/Edge ≥126, Firefox ≥126, Safari ≥18.4. Devuelve la URL o
// null ante una entrada inválida, en vez de lanzar como `new URL(...)`.
export function installUrlParse(): void {
  const objetivo = URL as unknown as ConParse;
  if (typeof objetivo.parse === "function") return; // ya nativo
  objetivo.parse = function parse(url: string | URL, base?: string | URL): URL | null {
    try {
      return base === undefined ? new URL(url) : new URL(url, base);
    } catch {
      return null;
    }
  };
}

installPromiseWithResolvers();
installUrlParse();
