// One OCR worker for all cropped fields in a screen. No desktop control.
const {createWorker}=require('tesseract.js');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const requests=JSON.parse(fs.readFileSync(0,'utf8'));
  let worker;
  try{
    worker=await createWorker('eng',1,require('./ocr_options.cjs')());
    const result={};
    for(const request of requests){
      await worker.setParameters({tessedit_pageseg_mode:String(request.psm||7),
        tessedit_char_whitelist:request.whitelist||''});
      const {data}=await worker.recognize(Buffer.from(request.image,'base64'));
      result[request.name]=data.text.trim();
    }
    process.stdout.write(JSON.stringify(result));
  }finally{if(worker)await worker.terminate();}
})().catch(error=>{process.stderr.write(String(error.message));process.exitCode=1;});
