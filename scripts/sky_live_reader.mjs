// Read-only bridge for the Computer Use Node REPL. Pass its initialized sky
// object and a window returned by sky; never guesses handles or sends input.
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const run = promisify(execFile);

class SkyReader {
  constructor({sky, window, python, root}) {
    this.sky = sky; this.window = window; this.python = python; this.root = root;
  }
  async observe() {
    const capturedAt = new Date().toISOString();
    const state = await this.sky.get_window_state({window: this.window});
    this.window = state.window;
    if (state.screenshots.length !== 1) throw new Error('Ambiguous screenshot surface');
    const shot = state.screenshots[0];
    if (!/^data:image\/(?:png|jpeg);base64,/.test(shot.url)) throw new Error('Unsupported image encoding');
    const cache = path.join(this.root, '.cache');
    await fs.mkdir(cache,{recursive:true});
    const dir = await fs.mkdtemp(path.join(cache,'observation-'));
    const file = path.join(dir,'screen.png');
    await fs.writeFile(file,Buffer.from(shot.url.split(',')[1],'base64'));
    let result;
    try {
      const output = await run(this.python,[path.join(this.root,'read_screen.py'),file,'--captured-at',capturedAt],
        {cwd:this.root,windowsHide:true,timeout:60000,maxBuffer:1024*1024});
      result = JSON.parse(output.stdout);
    } catch (error) {
      if (error.code === 2 && error.stdout) result = JSON.parse(error.stdout);
      else throw error;
    } finally {
      // Only the exact file and private empty temporary directory created above.
      await fs.unlink(file);
      await fs.rmdir(dir);
    }
    return {capturedAt, finishedAt:new Date().toISOString(), evidence:result,
      inputEnabled:false};
  }
}
export {SkyReader};

