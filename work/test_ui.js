const { chromium } = require('C:/Users/pedro/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(process.argv[2]);
    await page.locator('#preview').waitFor({ state: 'visible' });
    const boxes = await Promise.all(['capture', 'start', 'stop'].map(id => page.locator('#' + id).boundingBox()));
    if (!boxes.every(box => Math.abs(box.width - boxes[0].width) < 1)) throw new Error('Larguras dos botões divergem');
    if (!(boxes[0].y < boxes[1].y && boxes[1].y < boxes[2].y)) throw new Error('Ordem vertical incorreta');

    const wrap = await page.locator('#previewwrap').boundingBox();
    const cx = wrap.x + wrap.width / 2, cy = wrap.y + wrap.height / 2;
    const oldVersion = await page.evaluate(async () => (await (await fetch('/api/plan')).json()).version);
    await page.mouse.move(cx - 40, cy - 30);
    await page.mouse.down();
    await page.mouse.move(cx + 40, cy + 30, { steps: 5 });
    await page.mouse.up();
    const afterPlainDrag = await page.evaluate(async () => (await (await fetch('/api/plan')).json()).version);
    if (afterPlainDrag !== oldVersion) throw new Error('Arraste sem Shift mudou a área em 100%');
    await page.mouse.move(cx, cy);
    await page.mouse.wheel(0, -400);
    await page.waitForFunction(() => document.querySelector('#zoomvalue').textContent !== '100%');
    const zoomText = await page.locator('#zoomvalue').textContent();
    const beforePan = await page.locator('#preview').evaluate(element => element.style.transform);
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    await page.mouse.move(cx - 80, cy - 45, { steps: 5 });
    await page.mouse.up();
    const afterPan = await page.locator('#preview').evaluate(element => element.style.transform);
    if (beforePan === afterPan) throw new Error('Arraste não moveu a imagem ampliada');
    if ((await page.locator('#zoomvalue').textContent()) === '100%') throw new Error('Zoom se perdeu ao arrastar');
    const afterPanVersion = await page.evaluate(async () => (await (await fetch('/api/plan')).json()).version);
    if (afterPanVersion !== oldVersion) throw new Error('Arraste mudou a área selecionada');
    await page.screenshot({ path: 'work/ui_zoom.png' });

    await page.locator('#resetzoom').click();
    if ((await page.locator('#zoomvalue').textContent()) !== '100%') throw new Error('Zoom não foi redefinido');
    await page.mouse.move(cx, cy);
    await page.mouse.wheel(0, -400);
    await page.waitForFunction(() => document.querySelector('#zoomvalue').textContent !== '100%');

    await page.keyboard.down('Shift');
    await page.mouse.move(cx - 35, cy - 30);
    await page.mouse.down();
    await page.mouse.move(cx + 80, cy + 65, { steps: 6 });
    await page.mouse.up();
    await page.keyboard.up('Shift');
    await page.waitForFunction(version => document.querySelector('#preview').src.includes('v=' + (version + 1)), oldVersion);
    const afterSelectVersion = await page.evaluate(async () => (await (await fetch('/api/plan')).json()).version);
    if (afterSelectVersion !== oldVersion + 1) throw new Error('Shift+arrastar não selecionou a área');
    await page.waitForFunction(() => document.querySelector('#zoomvalue').textContent === '100%');
    if (errors.length) throw new Error('Erros da página: ' + errors.join('; '));
    console.log('OK: botões iguais, zoom ' + zoomText + ', arraste, Shift+seleção e reset');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
