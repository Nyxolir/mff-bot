// Portable fallback when native Tesseract is absent. No desktop control.
const { createWorker } = require('tesseract.js');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const settings = JSON.parse(process.argv[2]);
  let worker;
  try {
    worker = await createWorker('eng', 1, require('./ocr_options.cjs')());
    await worker.setParameters({
      tessedit_pageseg_mode: String(settings.psm),
      tessedit_char_whitelist: settings.whitelist || '',
    });
    const { data } = await worker.recognize(fs.readFileSync(0));
    process.stdout.write(JSON.stringify({ text: data.text.trim() }));
  } finally {
    if (worker) await worker.terminate();
  }
})().catch(error => {
  process.stderr.write(String(error.message));
  process.exitCode = 1;
});
