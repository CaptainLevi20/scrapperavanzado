// In-memory fakes for the File System Access API, used only in tests — jsdom implements
// neither FileSystemDirectoryHandle/FileSystemFileHandle nor showDirectoryPicker natively.

export type DirectoryEntries = { [key: string]: string | DirectoryEntries };

function buildFileHandle(name: string, content: string): FileSystemFileHandle {
  return {
    kind: "file",
    name,
    isSameEntry: async () => false,
    getFile: async () => new File([content], name),
    createWritable: async () => {
      throw new Error("Read-only fake file handle: createWritable is not supported.");
    },
  } as unknown as FileSystemFileHandle;
}

function buildDirectoryHandle(name: string, entries: DirectoryEntries): FileSystemDirectoryHandle {
  const children = new Map<string, FileSystemFileHandle | FileSystemDirectoryHandle>();
  for (const [childName, value] of Object.entries(entries)) {
    children.set(
      childName,
      typeof value === "string" ? buildFileHandle(childName, value) : buildDirectoryHandle(childName, value)
    );
  }

  return {
    kind: "directory",
    name,
    isSameEntry: async () => false,
    values: () => {
      const iterator = children.values();
      return {
        [Symbol.asyncIterator]() {
          return this;
        },
        next: async () => iterator.next(),
      } as unknown as ReturnType<FileSystemDirectoryHandle["values"]>;
    },
    getDirectoryHandle: async () => {
      throw new Error("Read-only fake directory handle: getDirectoryHandle is not supported.");
    },
    getFileHandle: async () => {
      throw new Error("Read-only fake directory handle: getFileHandle is not supported.");
    },
  } as unknown as FileSystemDirectoryHandle;
}

export function fakeInputDirectory(name: string, entries: DirectoryEntries): FileSystemDirectoryHandle {
  return buildDirectoryHandle(name, entries);
}

interface RecordingNode {
  kind: "file" | "directory";
  content?: ArrayBuffer;
  children?: Map<string, RecordingNode>;
}

export interface RecordingDirectory {
  handle: FileSystemDirectoryHandle;
  readAll(): Record<string, string>;
}

export function fakeOutputDirectory(name: string): RecordingDirectory {
  const root: RecordingNode = { kind: "directory", children: new Map() };

  function wrapFile(node: RecordingNode, fileName: string): FileSystemFileHandle {
    return {
      kind: "file",
      name: fileName,
      isSameEntry: async () => false,
      getFile: async () => new File([node.content ?? new ArrayBuffer(0)], fileName),
      createWritable: async () => {
        return {
          write: async (data: ArrayBuffer) => {
            node.content = data;
          },
          close: async () => {},
        } as unknown as FileSystemWritableFileStream;
      },
    } as unknown as FileSystemFileHandle;
  }

  function wrapDir(node: RecordingNode, dirName: string): FileSystemDirectoryHandle {
    return {
      kind: "directory",
      name: dirName,
      isSameEntry: async () => false,
      values: () => {
        throw new Error("fakeOutputDirectory does not support iteration — it's write-only for copy.ts.");
      },
      getDirectoryHandle: async (childName: string, options?: { create?: boolean }) => {
        let child = node.children!.get(childName);
        if (!child) {
          if (!options?.create) throw new DOMException("Not found", "NotFoundError");
          child = { kind: "directory", children: new Map() };
          node.children!.set(childName, child);
        }
        if (child.kind !== "directory") throw new DOMException("Mismatched kind", "TypeMismatchError");
        return wrapDir(child, childName);
      },
      getFileHandle: async (childName: string, options?: { create?: boolean }) => {
        let child = node.children!.get(childName);
        if (!child) {
          if (!options?.create) throw new DOMException("Not found", "NotFoundError");
          child = { kind: "file" };
          node.children!.set(childName, child);
        }
        if (child.kind !== "file") throw new DOMException("Mismatched kind", "TypeMismatchError");
        return wrapFile(child, childName);
      },
    } as unknown as FileSystemDirectoryHandle;
  }

  function flatten(node: RecordingNode, prefix: string, out: Record<string, string>): void {
    for (const [childName, child] of node.children ?? []) {
      const path = prefix ? `${prefix}/${childName}` : childName;
      if (child.kind === "file") {
        out[path] = new TextDecoder().decode(child.content ?? new ArrayBuffer(0));
      } else {
        flatten(child, path, out);
      }
    }
  }

  return {
    handle: wrapDir(root, name),
    readAll: () => {
      const out: Record<string, string> = {};
      flatten(root, "", out);
      return out;
    },
  };
}
