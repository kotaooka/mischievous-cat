# どのものも、ネコが段の上でパンチして、近いほうの端から落とせるか（触りにくい置き方がないか）。全28面 × 4日分
# 4.51.8：エアコンの右端（壁の手前）で、ものが壁で跳ね返って落ちなかった
# 各ものについて、左右どちらかに立って、ふつうのパンチと必殺パンチを交互に最大 6 回（ものを追いかけながら）で段から落ちれば（くずれれば）OK
import harness

JS = r"""(L => {
  const out = []; newRun(); setupStage(L); const n0 = items.length;
  const targets = items.map((o, i) => [i, o]).filter(([i, o]) => !o.extra && o.plat && o.plat !== PL.floor && o.state === 'rest');
  for (const [i] of targets) {
    let ok = false, tried = [];
    // 近いほうの端へ押して落とせること（壁まで届く段＝本棚の上・バンの屋根は左へだけ）
    const it0 = items[i], p0 = it0.plat, wallR = p0.x1 > W - 6;
    const sides = wallR ? [1] : [(it0.x - p0.x0) < (p0.x1 - it0.x) ? 1 : -1];   // side：ネコが立つ側（-1＝左に立って右へ押す、1＝右に立って左へ押す）
    for (const side of sides) {
      newRun(); setupStage(L); state = 'play'; ov.hidden = true; introT = 0; owner.mode = 'away'; owner.t = 999; timeLeft = 999; rival = null; foe = null; mouse = null; chick = null; dog = null; vac = null;
      const it = items[i], p = it.plat; if (!it || !p) break;
      // ほかのものはどける（このものだけを調べる）
      for (const o of items) if (o !== it && o.plat === p) { o.plat = PL.floor; o.y = FLOOR; o.x = 30; }
      let n = 0;
      for (; n < 6 && items.includes(it) && it.plat === p && it.state !== 'fall'; n++) {
        const x = clamp(it.x + side * 22, p.x0 + 2, p.x1 - 2);
        if ((x - it.x) * side < 4) break;   // ものの横に立てない
        Object.assign(cat, { plat: p, y: p.y, x, vx: 0, vy: 0, face: -side, stun: 0, punchCd: 0, pDown: false, pHeld: 0, ledge: null, hang: false });
        punchDown(); if (n % 2) cat.pHeld = 0.4; punchUp();   // ふつうのパンチと必殺パンチを交互に
        for (let f = 0; f < 70 && items.includes(it) && it.plat === p && it.state !== 'fall'; f++) update(1 / 60);
      }
      tried.push((side < 0 ? 'L' : 'R') + n);
      if (!items.includes(it) || it.plat !== p || it.state === 'fall') { ok = true; break; }
    }
    if (!ok) { const it = items[i]; out.push(room + ' L' + L + ' lay' + layoutIx + ' ' + it.t + '@' + Math.round(it.x) + ' on ' + Object.keys(PL).find(k => PL[k] === it.plat) + ' [' + Math.round(it.plat.x0) + '-' + Math.round(it.plat.x1) + '] ' + tried.join(',')); }
  }
  return out;
})"""

def run(b):
    r = harness.Report('touch')
    g = harness.Game(b)
    for k in range(4):
        day = g.T(f"(()=>{{ if (!window.__D0) window.__D0 = Date.now; const D = window.__D0; Date.now = () => D() + {k} * 864e5; return jstDay(); }})()")
        for L in range(1, 29):
            bad = g.T(f'({JS})({L})')
            r.check(not bad, f'{day} 落とせないもの：' + ' / '.join(bad))
    r.check(not g.errors, f'エラー {g.errors[:2]}')
    g.close()
    return r.done()
