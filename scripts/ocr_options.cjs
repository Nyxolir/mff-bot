// Source runs retain their existing cache; installed builds use per-user cache
// and the bundled English model. Local model loading requires no download.
const path=require('node:path');
const fs=require('node:fs');
module.exports=()=>{
  const cachePath=process.env.MFF_OCR_CACHE||path.resolve(__dirname,'../.cache/ocr');
  fs.mkdirSync(cachePath,{recursive:true});
  const options={cachePath,logger:()=>{}};
  if(process.env.MFF_OCR_LANG_PATH){options.langPath=process.env.MFF_OCR_LANG_PATH;options.gzip=false;}
  return options;
};
