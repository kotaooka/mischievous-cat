# デイリー：「日本時間の同じ日なら、同じ面になる」を確かめる
# 日付（Date.now をずらす）ごとに、1〜28 面のそれぞれで、次の 3 通りの作り方の面を比べる
#   (a) まっさらな newRun() のあと setupStage(L)
#   (b) 1〜L-1 面を順に遊んでから L 面（少し遊ぶ・持ち越し時間あり）。まっさらな端末と、遊び慣れた端末（learned をそろえた）の 2 つ
#   (c) (b) で L 面の始まりに作られたセーブを、ページを開き直して resumeSave() で再開
# 比べるもの：もの（種類・x・置き場所）、お題、制限時間（持ち越しを除く）、レイアウト番号、足場の形、天気
# 仕掛けの有無（ネズミ・ボス猫・きゅうり・照明・ボール・お掃除ロボ・罠・カメラ・犬・きしみ・お守り）は端末の履歴（learned / lastGims）で
# 変わる仕様なので「受け入れ済み」として別に数え、失敗にはしない
import json
import harness

DATES = [0, 1, 45]          # 今日からずらす日数
LS = list(range(1, 29))

SIG = r"""
window.__sig = function(c0) {
  // 面の「指紋」。c0：setupStage の前の持ち越し時間（制限時間から引く）
  const R = v => Math.round(v);
  return {
    items: items.map(o => [o.t, R(o.x), o.home, !!o.extra, !!o.water]),
    tasks: tasks.map(t => t.id),
    timeBase: timeMax - (c0 || 0), layoutIx, weather, room,
    pl: Object.fromEntries(Object.keys(PL).sort().map(k => [k, [R(PL[k].x0), R(PL[k].x1), R(PL[k].y)]])),
    gims: { mouse: !!mouse, rival: !!rival, cuke: !!cuke, lamp: !!lamp, ball: !!ball, vac: !!vac, trap: traps.length > 0, cam: cams.length, dog: !!dog, creak: creaks.length > 0, charm: !!charm },
    gpos: { traps: traps.map(t => [R(t.x), t.type]), cuke: cuke && R(cuke.x), creaks: creaks.map(q => R(q.x)), lamp: lamp && [R(lamp.ax), R(lamp.L)], ball: ball && R(ball.x), vac: vac && R(vac.x) },
    day: jstDay()
  };
};
window.__shift = function(k) { if (!window.__D0) window.__D0 = Date.now; const D = window.__D0; Date.now = () => D() + k * 864e5; return jstDay(); };
window.__play = function(sec, rng) {
  // それらしく遊ぶ：左右に歩く・跳ぶ・たたく・ものを1つ落とす。見つかったり時間切れになっても気にしない
  let s = rng; const R = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const t0 = performance.now();
  try {
    for (let t = 0; t < sec && state === 'play'; t += 1 / 30) {
      if (R() < 0.08) { keys.L = R() < 0.5; keys.R = !keys.L; }
      if (R() < 0.03) jumpPress();
      if (R() < 0.02) { punchDown(); punchUp(); }
      if (R() < 0.01) { const m = items.filter(o => !o.extra && o.state === 'rest' && o.plat); if (m.length) { const it = m[0]; it.y0 = it.plat.y; it.plat = null; it.state = 'fall'; it.vy = 0; it.vx = 0; it.vr = 1; } }
      update(1 / 30);
    }
  } finally { keys.L = keys.R = false; }
  return state;
};
"""


def diff_keys(a, b, keys):
    return [k for k in keys if a[k] != b[k]]


def describe(a, b, k):
    if k == 'items':
        ia, ib = a['items'], b['items']
        return f'items {len(ia)}→{len(ib)} 例 {next(([x, y] for x, y in zip(ia, ib) if x != y), (ia[len(ib):] or ib[len(ia):])[:1])}'
    if k == 'pl':
        return 'pl ' + ', '.join(f'{p}:{a["pl"][p]}→{b["pl"][p]}' for p in a['pl'] if a['pl'][p] != b['pl'].get(p))
    return f'{k} {a[k]}→{b[k]}'


STRICT = ['items', 'tasks', 'timeBase', 'layoutIx', 'pl', 'weather', 'room']


def run(b):
    r = harness.Report('daily')
    accepted = {}      # 受け入れ済みの違い（仕掛けの有無）：名前 → 回数
    info = []
    seasoned = {'nekoLearned': json.dumps(['see_' + k for k in ['cuke', 'lamp', 'creak', 'trap', 'cam', 'tv', 'cloth', 'mouse', 'chick', 'tank', 'guest', 'door', 'shelf', 'mis', 'vac', 'ball', 'bone',
                                                               'foe_vacbot', 'foe_crow', 'foe_toybot', 'foe_drone', 'dog', 'rival']] + ['mis', 'lever', 'ball', 'high']),
                'nekoClr': json.dumps(LS), 'nekoEnded': '1', 'nekoTrueEnd': '1'}
    by_date = {}
    midday = [0]
    dayof = lambda L: (L - 1) // 4 + 1

    def compare(x, y, what, L, strict=STRICT, gpos=True, gims=True):
        bad = diff_keys(x, y, strict)
        gd = [k for k in x['gims'] if x['gims'][k] != y['gims'][k]]
        # 4.51.6 から：仕掛けの有無も日付と面だけで決まる（端末の履歴を見ない）ので、違えば失敗。
        # ただし (a) で日の途中の面をいきなり作ったとき（天気を引く分、乱数がずれる）は比べない
        if gims:
            r.check(not gd, f'{what} L={L}: 仕掛けの有無が違う {gd}')
        else:
            for k in gd:
                accepted[k] = accepted.get(k, 0) + 1
        # 仕掛けの位置：両方にあるときは同じはず（置く乱数は間引きの前に引く）
        pd = [k for k in x['gpos'] if gpos and x['gpos'][k] and y['gpos'][k] and x['gpos'][k] != y['gpos'][k] and (k != 'traps' or (x['gims']['trap'] and y['gims']['trap']))]
        note = f'（このとき仕掛けの有無も違う：{gd}）' if gd else ''
        r.check(not bad, f'{what} L={L}: ' + '; '.join(describe(x, y, k) for k in bad) + note)
        r.check(not pd, f'{what} L={L}: 仕掛けの位置が違う ' + '; '.join(f'{k} {x["gpos"][k]}→{y["gpos"][k]}' for k in pd))
        return bad

    for k in DATES:
        # ---- (a) まっさら ----
        g = harness.Game(b)
        g.T(SIG)
        day = g.T(f'__shift({k})')
        A = {}
        for L in LS:
            A[L] = g.T(f"(()=>{{ newRun(); state='play'; ov.hidden=true; carryT=0; setupStage({L}); return __sig(0); }})()")
        r.check(not g.errors, f'(a) {day}: エラー {g.errors[:2]}')
        g.close()

        # ---- (b) 順に遊ぶ（まっさらな端末・遊び慣れた端末）、(c) そのセーブから再開 ----
        for label, storage in [('まっさらな端末', None), ('遊び慣れた端末', seasoned)]:
            g = harness.Game(b, storage=storage)
            g.T(SIG)
            g.T(f'__shift({k})')
            B, saves = {}, {}
            g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
            B[1] = g.T('__sig(0)')
            for L in LS[1:]:
                g.T(f'__play({1.5 + (L % 3)}, {L * 7919 + k + 1})')
                c0 = (L * 3) % 9   # 前の面からの持ち越し時間（0〜8 秒）
                B[L] = g.T(f"(()=>{{ if (run.caughtOver) {{ run.caughtOver = false; }} state='play'; ov.hidden=true; carryT={c0}; setupStage({L}); return __sig({c0}); }})()")
                saves[L] = g.T("localStorage.getItem('nekoSave')")
            r.check(not g.errors, f'(b) {label} {day}: エラー {g.errors[:2]}')
            for L in LS:
                # (a) で日の途中の面をいきなり作ると、その日の天気（run.wx）をその面で引くので、後の乱数（罠・きゅうり・ネズミ…）が (b) とずれる。
                # ランキングに載る遊び方（順に進む・朝から続ける・セーブから再開）では起きないので、日の途中の面は天気・お題・仕掛けの位置を比べない
                mid = dayof(L) >= 2 and (L - 1) % 4 != 0
                if mid:
                    if A[L]['weather'] != B[L]['weather']:
                        midday[0] += 1
                    compare(A[L], B[L], f'(a)まっさら↔(b){label} {day}', L, ['items', 'timeBase', 'layoutIx', 'pl', 'room'], gpos=False, gims=False)
                else:
                    compare(A[L], B[L], f'(a)まっさら↔(b){label} {day}', L)
            # (c) セーブから：ページを開き直して resumeSave
            C = {}
            for L in LS[1:]:
                sv = saves[L]
                if not r.check(bool(sv) and json.loads(sv).get('level') == L, f'(c) {label} {day} L={L}: setupStage がこの面のセーブを残す'):
                    continue
                g.page.evaluate('s => localStorage.setItem("nekoSave", s)', sv)
                g.open(); g.T(SIG); g.T(f'__shift({k})')
                C[L] = g.T(f"(()=>{{ const c0 = (loadSave() || {{}}).carryT || 0; resumeSave(); return __sig(c0); }})()")
                r.check(g.T('[state, level]') == ['play', L], f'(c) {label} {day} L={L}: 再開してその面を遊べる')
                compare(B[L], C[L], f'(b){label}↔(c)セーブから再開 {day}', L)
            r.check(not g.errors, f'(c) {label} {day}: エラー {g.errors[:2]}')
            by_date.setdefault(k, {})[label] = B
            g.close()
        by_date[k]['a'] = A
        # 同じ日の (b) 2 つの端末どうし
        for L in LS:
            compare(by_date[k]['まっさらな端末'][L], by_date[k]['遊び慣れた端末'][L], f'(b)まっさら↔(b)遊び慣れた {day}', L)

    # ---- 夜中の 0 時をまたいだ回（4.51.7）：途中の面も、始めた日の配置のまま ----
    for k in DATES[:2]:
        g = harness.Game(b)
        g.T(SIG); g.T(f'__shift({k})')
        g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
        same = {L: g.T(f"(()=>{{ state='play'; carryT=0; setupStage({L}); return __sig(0); }})()") for L in (2, 5, 9)}
        g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()"); g.T(f'__shift({k + 1})')   # 1面目のあとで日付が変わった
        for L in (2, 5, 9):
            x = g.T(f"(()=>{{ state='play'; carryT=0; setupStage({L}); return __sig(0); }})()")
            # 天気は面ごとに引くので比べる。仕掛けの有無も同じはず
            r.check(x['items'] == same[L]['items'] and x['tasks'] == same[L]['tasks'] and x['layoutIx'] == same[L]['layoutIx'] and x['gims'] == same[L]['gims'],
                    f'0時をまたいだ回の L={L}：始めた日の配置のまま')
        r.check(g.T('run.day') != g.T('jstDay()'), '0時をまたいだ回：run.day は始めた日')
        g.close()

    # ---- 日付が違えば、たいてい配置も違う ----
    ks = list(by_date)
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            A1, A2 = by_date[ks[i]]['a'], by_date[ks[j]]['a']
            same = [L for L in LS if A1[L]['items'] == A2[L]['items']]
            r.check(len(same) <= 2, f'日付 {A1[1]["day"]} と {A2[1]["day"]} で、ものの配置が同じ面が多すぎる：{same}')
            lay = sum(A1[L]['layoutIx'] != A2[L]['layoutIx'] for L in LS)
            r.check(lay >= 5, f'日付 {A1[1]["day"]} と {A2[1]["day"]} で、レイアウト番号が違う面が少ない（{lay}/28）')
            r.check(A1[1]['day'] != A2[1]['day'], 'Date.now のずらしが jstDay に効いている')

    # ---- ネコの種類で配置が変わるか（招き猫）：仕様の確認として報告だけ ----
    g = harness.Game(b, storage={'nekoCats': json.dumps(['mike'])})
    g.T(SIG)
    lucky = g.T('CATS.findIndex(c => c.lucky)')
    if lucky >= 0:
        diffs = []
        for L in LS:
            x = g.T(f"(()=>{{ selCat = {1 if lucky == 0 else 0}; newRun(); state='play'; carryT=0; setupStage({L}); return __sig(0); }})()")
            y = g.T(f"(()=>{{ selCat = {lucky}; newRun(); state='play'; carryT=0; setupStage({L}); return __sig(0); }})()")
            if x['items'] != y['items'] or x['tasks'] != y['tasks']:
                diffs.append(L)
        info.append(f'招き猫（{g.T(f"CATS[{lucky}].id")}）を選ぶと、同じ日でもものの組（と、それに合わせたお題）が変わる面：{len(diffs)}/28（仕様：被害額の目安 1.3 倍。今日のランキングは「同じ面」にならない）')
    g.close()

    print('  INFO (a) 日の途中の面をいきなり作ったときの仕掛けの有無の違い（テストの作り方による。失敗にしない）：' + (', '.join(f'{k}×{n}' for k, n in sorted(accepted.items())) or 'なし'))
    info.append(f'(a) まっさらな run で日の途中の面をいきなり作ると天気が (b) と違った回数：{midday[0]}（テストの作り方によるもので、ランキングに載る遊び方では起きない。テストメニューの面選びは run.test なので対象外）')
    for line in info:
        print('  INFO ' + line)
    return r.done()
