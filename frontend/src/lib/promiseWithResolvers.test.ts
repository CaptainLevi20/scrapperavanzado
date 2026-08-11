import { afterEach, describe, expect, it } from "vitest";

import { installPromiseWithResolvers } from "./promiseWithResolvers";

type ConResolvers = {
  withResolvers?: <T>() => {
    promise: Promise<T>;
    resolve: (value: T | PromiseLike<T>) => void;
    reject: (reason?: unknown) => void;
  };
};

const objetivo = Promise as unknown as ConResolvers;

describe("installPromiseWithResolvers", () => {
  // Estado nativo capturado antes de manipularlo; se restaura tras cada prueba
  // para no filtrar el borrado a otros tests del proyecto.
  const original = objetivo.withResolvers;

  afterEach(() => {
    if (original === undefined) {
      delete objetivo.withResolvers;
    } else {
      objetivo.withResolvers = original;
    }
  });

  it("instala Promise.withResolvers cuando el navegador no lo trae", async () => {
    delete objetivo.withResolvers;
    expect(objetivo.withResolvers).toBeUndefined();

    installPromiseWithResolvers();

    expect(typeof objetivo.withResolvers).toBe("function");
    const { promise, resolve } = objetivo.withResolvers!<number>();
    resolve(42);
    await expect(promise).resolves.toBe(42);
  });

  it("el reject del polyfill sí rechaza la promesa", async () => {
    delete objetivo.withResolvers;
    installPromiseWithResolvers();

    const { promise, reject } = objetivo.withResolvers!<number>();
    reject(new Error("boom"));
    await expect(promise).rejects.toThrow("boom");
  });

  it("no reemplaza la implementación nativa cuando ya existe", () => {
    const marcador = () => ({ promise: Promise.resolve<never>(undefined as never), resolve() {}, reject() {} });
    objetivo.withResolvers = marcador as ConResolvers["withResolvers"];

    installPromiseWithResolvers();

    expect(objetivo.withResolvers).toBe(marcador);
  });
});
