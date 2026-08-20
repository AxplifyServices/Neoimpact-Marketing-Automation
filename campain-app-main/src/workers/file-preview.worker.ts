import { read, utils } from 'xlsx';

interface PreviewPayload {
  headers: string[];
  rows: string[][];
  totalRows: number;
}

self.onmessage = async (event: MessageEvent<{ file: File }>) => {
  try {
    const file = event.data.file;
    const arrayBuffer = await file.arrayBuffer();

    const workbook = read(arrayBuffer, { type: 'array' });
    const firstSheetName = workbook.SheetNames[0];
    const firstSheet = firstSheetName ? workbook.Sheets[firstSheetName] : undefined;

    if (!firstSheet) {
      (self as any).postMessage({ ok: true, data: null });
      return;
    }

    const jsonData = utils.sheet_to_json(firstSheet, {
      header: 1,
      raw: false,
      blankrows: false,
    }) as unknown[][];

    if (!jsonData.length) {
      (self as any).postMessage({ ok: true, data: null });
      return;
    }

    const data: PreviewPayload = {
      headers: (jsonData[0] || []).map((cell) => String(cell ?? '')),
      rows: jsonData.slice(1, 6).map((row) =>
        row.map((cell) => String(cell ?? '')),
      ),
      totalRows: Math.max(jsonData.length - 1, 0),
    };

    (self as any).postMessage({ ok: true, data });
  } catch (error) {
    (self as any).postMessage({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    });
  }
};

export {};
