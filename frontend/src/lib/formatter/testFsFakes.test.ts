import { describe, expect, it } from "vitest";
import { fakeInputDirectory, fakeOutputDirectory } from "./testFsFakes";

describe("fakeInputDirectory", () => {
  it("iterates files and subdirectories via values()", async () => {
    const root = fakeInputDirectory("root", {
      sub: { "a.txt": "hola" },
      "b.txt": "chau",
    });

    const names: string[] = [];
    for await (const handle of root.values()) {
      names.push(`${handle.kind}:${handle.name}`);
    }
    expect(names.sort()).toEqual(["directory:sub", "file:b.txt"]);
  });

  it("getFile() on a nested file handle returns its content", async () => {
    const root = fakeInputDirectory("root", { sub: { "a.txt": "hola" } });

    let fileContent = "";
    for await (const handle of root.values()) {
      if (handle.kind === "directory") {
        for await (const child of handle.values()) {
          if (child.kind === "file") {
            fileContent = await (await child.getFile()).text();
          }
        }
      }
    }
    expect(fileContent).toBe("hola");
  });
});

describe("fakeOutputDirectory", () => {
  it("creates nested directories and files on demand, and readAll() flattens them", async () => {
    const output = fakeOutputDirectory("salida");

    const subDir = await output.handle.getDirectoryHandle("AÑO 2000", { create: true });
    const fileHandle = await subDir.getFileHandle("archivo.txt", { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(new TextEncoder().encode("contenido").buffer);
    await writable.close();

    expect(output.readAll()).toEqual({ "AÑO 2000/archivo.txt": "contenido" });
  });

  it("getDirectoryHandle/getFileHandle without create throws for a missing entry", async () => {
    const output = fakeOutputDirectory("salida");
    await expect(output.handle.getDirectoryHandle("no-existe")).rejects.toThrow();
    await expect(output.handle.getFileHandle("no-existe.txt")).rejects.toThrow();
  });
});
