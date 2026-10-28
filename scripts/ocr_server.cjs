// Local JSON-lines OCR worker. Reuse language initialization across screen reads.
const {createWorker}=require('tesseract.js');
const readline=require('node:readline');
const path=require('node:path');
const fs=require('node:fs');
(async()=>{
  const cachePath=path.resolve(__dirname,'../.cache/ocr');
  fs.mkdirSync(cachePath,{recursive:true});
  const worker=await createWorker('eng',1,{cachePath,logger:()=>{}});
  try{
    for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
      try{
        const requests=JSON.parse(line),result={};
        for(const request of requests){
          await worker.setParameters({tessedit_pageseg_mode:String(request.psm??7),tessedit_char_whitelist:request.whitelist||''});
          const {data}=await worker.recognize(Buffer.from(request.image,'base64'));
          result[request.name]=data.text.trim();
        }
        process.stdout.write(JSON.stringify({result})+'\n');
      }catch(error){process.stdout.write(JSON.stringify({error:String(error.message)})+'\n');}
    }
  }finally{await worker.terminate();}
})().catch(error=>{process.stdout.write(JSON.stringify({error:String(error.message)})+'\n');process.exitCode=1;});
