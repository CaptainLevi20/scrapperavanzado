export {};

declare global {
  // Chrome's FileSystemHandle.move() is not in TypeScript's DOM typings yet, and
  // not every browser/drive supports it — always feature-check before calling.
  interface FileSystemHandle {
    move?(newName: string): Promise<void>;
  }
}
