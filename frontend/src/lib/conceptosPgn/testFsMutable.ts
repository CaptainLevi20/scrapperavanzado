// In-memory, mutable fake of the File System Access API, used only in tests —
// jsdom has none of it. Unlike formatter/testFsFakes.ts (read-only input /
// write-only output), this one supports renaming in place: iteration,
// creating files, removeEntry and FileSystemFileHandle.move().

import type { DirectoryEntries } from "../formatter/testFsFakes";

export interface MutableFsOptions {
  supportsMove?: boolean;
  failMoveFor?: string[];
  failWriteFor?: string[];
  truncateWriteFor?: string[];
}

interface FileNode {
  kind: "file";
  name: string;
  content: Uint8Array;
}

interface DirNode {
  kind: "directory";
  name: string;
  children: Map<string, FileNode | DirNode>;
}

export interface MutableDirectory {
  handle: FileSystemDirectoryHandle;
  snapshot(): Record<string, string>;
  put(path: string, content: string): void;
}

const encoder = new TextEncoder();
// ignoreBOM keeps a leading BOM in snapshots, so tests can assert it's written.
const decoder = new TextDecoder("utf-8", { ignoreBOM: true });

function notFound(): DOMException {
  return new DOMException("Not found", "NotFoundError");
}

export function fakeMutableDirectory(
  name: string,
  entries: DirectoryEntries,
  options: MutableFsOptions = {}
): MutableDirectory {
  const { supportsMove = true, failMoveFor = [], failWriteFor = [], truncateWriteFor = [] } = options;

  function build(dirName: string, tree: DirectoryEntries): DirNode {
    const node: DirNode = { kind: "directory", name: dirName, children: new Map() };
    for (const [childName, value] of Object.entries(tree)) {
      node.children.set(
        childName,
        typeof value === "string"
          ? { kind: "file", name: childName, content: encoder.encode(value) }
          : build(childName, value)
      );
    }
    return node;
  }

  const root = build(name, entries);
  const fileHandles = new WeakMap<FileNode, FileSystemFileHandle>();
  const dirHandles = new WeakMap<DirNode, FileSystemDirectoryHandle>();

  function wrapFile(node: FileNode, parent: DirNode): FileSystemFileHandle {
    const cached = fileHandles.get(node);
    if (cached) return cached;
    const handle: Record<string, unknown> = {
      kind: "file",
      get name() {
        return node.name;
      },
      isSameEntry: async (other: FileSystemHandle) => other === handle,
      getFile: async () => new File([node.content.slice()], node.name),
      createWritable: async () => {
        let pending = new Uint8Array(0);
        return {
          write: async (data: ArrayBuffer | Uint8Array | Blob) => {
            if (failWriteFor.includes(node.name)) throw new Error("Fallo de escritura simulado");
            const bytes =
              data instanceof Blob ? new Uint8Array(await data.arrayBuffer()) : new Uint8Array(data as ArrayBuffer);
            pending = truncateWriteFor.includes(node.name) ? bytes.slice(0, Math.floor(bytes.length / 2)) : bytes;
          },
          close: async () => {
            node.content = pending;
          },
          abort: async () => {},
        } as unknown as FileSystemWritableFileStream;
      },
    };
    if (supportsMove) {
      handle.move = async (newName: string) => {
        if (failMoveFor.includes(node.name)) throw new DOMException("Movimiento no permitido", "NotAllowedError");
        const clash = [...parent.children.keys()].find(
          (existing) => existing !== node.name && existing.toLowerCase() === newName.toLowerCase()
        );
        if (clash) throw new DOMException("Ya existe", "InvalidModificationError");
        parent.children.delete(node.name);
        node.name = newName;
        parent.children.set(newName, node);
      };
    }
    const typed = handle as unknown as FileSystemFileHandle;
    fileHandles.set(node, typed);
    return typed;
  }

  function wrapDir(node: DirNode): FileSystemDirectoryHandle {
    const cached = dirHandles.get(node);
    if (cached) return cached;
    const handle = {
      kind: "directory",
      name: node.name,
      isSameEntry: async (other: FileSystemHandle) => other === handle,
      values: () => {
        const iterator = [...node.children.values()]
          .map((child) => (child.kind === "file" ? wrapFile(child, node) : wrapDir(child)))
          [Symbol.iterator]();
        return {
          [Symbol.asyncIterator]() {
            return this;
          },
          next: async () => iterator.next(),
        };
      },
      getDirectoryHandle: async (childName: string, opts?: { create?: boolean }) => {
        let child = node.children.get(childName);
        if (!child) {
          if (!opts?.create) throw notFound();
          child = { kind: "directory", name: childName, children: new Map() };
          node.children.set(childName, child);
        }
        if (child.kind !== "directory") throw new DOMException("Mismatched kind", "TypeMismatchError");
        return wrapDir(child);
      },
      getFileHandle: async (childName: string, opts?: { create?: boolean }) => {
        let child = node.children.get(childName);
        if (!child) {
          if (!opts?.create) throw notFound();
          child = { kind: "file", name: childName, content: new Uint8Array(0) };
          node.children.set(childName, child);
        }
        if (child.kind !== "file") throw new DOMException("Mismatched kind", "TypeMismatchError");
        return wrapFile(child, node);
      },
      removeEntry: async (childName: string) => {
        if (!node.children.delete(childName)) throw notFound();
      },
    } as unknown as FileSystemDirectoryHandle;
    dirHandles.set(node, handle);
    return handle;
  }

  function flatten(node: DirNode, prefix: string, out: Record<string, string>): void {
    for (const [childName, child] of node.children) {
      const path = prefix ? `${prefix}/${childName}` : childName;
      if (child.kind === "file") out[path] = decoder.decode(child.content);
      else flatten(child, path, out);
    }
  }

  return {
    handle: wrapDir(root),
    snapshot: () => {
      const out: Record<string, string> = {};
      flatten(root, "", out);
      return out;
    },
    put: (path: string, content: string) => {
      const parts = path.split("/");
      const fileName = parts.pop()!;
      let dir = root;
      for (const part of parts) {
        let next = dir.children.get(part);
        if (!next) {
          next = { kind: "directory", name: part, children: new Map() };
          dir.children.set(part, next);
        }
        if (next.kind !== "directory") throw new Error(`${part} no es una carpeta`);
        dir = next;
      }
      dir.children.set(fileName, { kind: "file", name: fileName, content: encoder.encode(content) });
    },
  };
}
