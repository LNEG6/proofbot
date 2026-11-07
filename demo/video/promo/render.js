// Renders index.html frame by frame. Each frame is a pure function of time, so a render is exact and repeatable.
//   npm i puppeteer-core
//   node render.js stills 2 8 20 25        one PNG per timestamp
//   node render.js film out.mp4 music.wav  the whole film (FFMPEG=path if ffmpeg isn't on PATH)
const fs = require("fs"), path = require("path"), { spawn } = require("child_process");
const puppeteer = require(process.env.PUPPETEER_PATH || "puppeteer-core");
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const FPS = 30;

async function open() {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--force-device-scale-factor=1", "--hide-scrollbars"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto("file:///" + path.resolve(__dirname, "index.html").replace(/\\/g, "/"), { waitUntil: "networkidle0", timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  return { browser, page };
}

(async () => {
  const [mode, ...rest] = process.argv.slice(2);
  const { browser, page } = await open();
  if (mode === "stills") {
    const out = process.env.OUT || ".";
    for (const t of rest) {
      await page.evaluate(v => window.seek(v), Number(t));
      await page.screenshot({ path: path.join(out, `still_${t}.png`) });
    }
  } else {
    const [file, audio] = rest;
    const duration = await page.evaluate(() => window.DURATION);
    const total = Math.round(duration * FPS);
    const args = ["-y", "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-"];
    if (audio) args.push("-i", audio, "-c:a", "aac", "-b:a", "192k", "-shortest");
    args.push("-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
              "-color_range", "tv", "-movflags", "+faststart", file);
    const ff = spawn(process.env.FFMPEG || "ffmpeg", args, { stdio: ["pipe", "inherit", "inherit"] });
    const started = Date.now();
    for (let frame = 0; frame < total; frame++) {
      await page.evaluate(v => window.seek(v), frame / FPS);
      const shot = await page.screenshot({ type: "jpeg", quality: 96 });
      if (!ff.stdin.write(shot)) await new Promise(done => ff.stdin.once("drain", done));
      if (frame % 150 === 0) console.log(`frame ${frame}/${total} (${Math.round((Date.now() - started) / 1000)}s)`);
    }
    ff.stdin.end();
    await new Promise(done => ff.on("close", done));
    console.log("wrote", file);
  }
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
