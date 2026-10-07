const utf8 = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
const encoder = new TextEncoder();

/** Strict UTF-8 decode that keeps a leading BOM. Throws on invalid input. */
export function decodeUtf8(bytes: Uint8Array): string {
  return utf8.decode(bytes);
}

export function encodeUtf8(text: string): Uint8Array {
  return encoder.encode(text);
}

/** Orders strings by their UTF-8 bytes, which is what "sorted bytewise" means in the spec. */
export function byteCompare(a: string, b: string): number {
  return Buffer.compare(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
}

/** ASCII-only lower-casing (`A-Z` to `a-z`), the spec's `fold`. */
export function fold(s: string): string {
  return s.replace(/[A-Z]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 32));
}
