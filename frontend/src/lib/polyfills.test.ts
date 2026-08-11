import { afterEach, describe, expect, it } from "vitest";

import { installPromiseWithResolvers, installUrlParse } from "./polyfills";

type ConResolvers = {
  withResolvers?: <T>() => {
    promise: Promise<T>;
    resolve: (value: T | PromiseLike<T>) => void;
    reject: (reason?: unknown) => void;
  };
};

type ConParse = { parse?: (url: string | URL, base?: string | URL) => URL | null };

const promesa = Promise as unknown as ConResolvers;
const url = URL as unknown as ConParse;

describe("installPromiseWithResolvers", () => {
  const original = promesa.withResolvers;
  afterEach(() => {
    if (original === undefined) delete promesa.withResolvers;
    else promesa.withResolvers = original;
  });

  it("instala Promise.withResolvers cuando el navegador no lo trae", async () => {
    delete promesa.withResolvers;
    installPromiseWithResolvers();
    expect(typeof promesa.withResolvers).toBe("function");
    const { promise, resolve } = promesa.withResolvers!<number>();
    resolve(42);
    await expect(promise).resolves.toBe(42);
  });

  it("el reject del polyfill sí rechaza la promesa", async () => {
    delete promesa.withResolvers;
    installPromiseWithResolvers();
    const { promise, reject } = promesa.withResolvers!<number>();
    reject(new Error("boom"));
    await expect(promise).rejects.toThrow("boom");
  });

  it("no reemplaza la implementación nativa cuando ya existe", () => {
    const marcador = (() => ({ promise: Promise.resolve(), resolve() {}, reject() {} })) as ConResolvers["withResolvers"];
    promesa.withResolvers = marcador;
    installPromiseWithResolvers();
    expect(promesa.withResolvers).toBe(marcador);
  });
});

describe("installUrlParse", () => {
  const original = url.parse;
  afterEach(() => {
    if (original === undefined) delete url.parse;
    else url.parse = original;
  });

  it("instala URL.parse cuando el navegador no lo trae", () => {
    delete url.parse;
    installUrlParse();
    expect(typeof url.parse).toBe("function");
    expect(url.parse!("https://ejemplo.com/a")?.href).toBe("https://ejemplo.com/a");
  });

  it("devuelve null ante una URL inválida (en vez de lanzar)", () => {
    delete url.parse;
    installUrlParse();
    expect(url.parse!("esto no es una url")).toBeNull();
  });

  it("resuelve una ruta relativa contra la base", () => {
    delete url.parse;
    installUrlParse();
    expect(url.parse!("/x", "https://ejemplo.com")?.href).toBe("https://ejemplo.com/x");
  });

  it("no reemplaza la implementación nativa cuando ya existe", () => {
    const marcador = ((() => null) as unknown) as ConParse["parse"];
    url.parse = marcador;
    installUrlParse();
    expect(url.parse).toBe(marcador);
  });
});
