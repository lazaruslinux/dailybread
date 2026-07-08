// Barcode decoding via zxing-wasm, configured to load its WASM from our own
// bundle: the app never fetches code from a CDN, on any network. This module
// is imported lazily (only when a scanner actually opens), so the decoder's
// weight stays out of the main bundle.
import { prepareZXingModule, readBarcodes } from 'zxing-wasm/reader'
import type { ReadResult } from 'zxing-wasm/reader'
import wasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url'

prepareZXingModule({
  overrides: {
    locateFile: (path: string, prefix: string) =>
      path.endsWith('.wasm') ? wasmUrl : prefix + path,
  },
})

// Retail product codes only — the formats printed on food packaging.
const OPTIONS = {
  formats: ['EAN-13', 'EAN-8', 'UPC-A', 'UPC-E'],
  tryHarder: true,
  maxNumberOfSymbols: 1,
} as const

// Decode one camera frame (or any image). Returns the digits, or null.
export async function readCode(image: ImageData | Blob): Promise<string | null> {
  const results: ReadResult[] = await readBarcodes(image, { ...OPTIONS, formats: [...OPTIONS.formats] })
  const hit = results.find((r) => r.isValid && /^[0-9]{6,14}$/.test(r.text))
  return hit ? hit.text : null
}
