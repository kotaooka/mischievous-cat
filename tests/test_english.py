# 英語モード（lang 'en'）：画面に日本語が出ていないか、文字がはみ出していないかを確かめる
# - 1〜28 面のプレイ画面（面の始まり・仕掛けの札・遊んでいる途中・クリア・見つかった・日の終わり）をキャンバスに描く
# - 重ねる画面：タイトル（初回・ふだん）、ネコとおしゃれ、いたずら図鑑の全ページ、ランキングの3つのタブ、通算記録の全ページ、設定、ポーズ、
#   結果画面（見つかった：この面から／朝から／名前の登録／ランクイン／送れなかった）、エンディング（いつもの夜・ほんとうのおしまい）と結果、スタッフロール
# - DOM：#ov と画面全体の見えている文字に、ひらがな・カタカナ・漢字・全角の記号がないこと（意図した「#こっそりネコ」とロゴの副題は除く）
# - DOM：390px 幅で、ボタン・ラベル・段落がパネルからはみ出していないこと（scrollWidth と、パネルの左右の端）
# - キャンバス：fillText / strokeText をのぞいて、日本語の文字列・キャンバスより幅の広い文字列がないこと
# - シェアの文章（shareText）に、ハッシュタグ以外の日本語がないこと
# - 静的：index.html の lt()/tx() の英語側に日本語が入っていないこと
import re, json
import harness

JP = re.compile(r'[、-〿぀-ヿ㐀-䶿一-鿿！-｠￠-￦]')
# 意図して日本語を出している所（コードを読んで決めた）：
#   ハッシュタグ「#こっそりネコ」（shareText の tag）
#   英語版のロゴの副題「こっそりネコ」（applyLang の .logo small、タイトルの p.sub）と document.title
ALLOW_TEXT = {'#こっそりネコ', 'こっそりネコ'}

HOOK = r"""
(() => {
  if (window.__hooked) return; window.__hooked = true;
  window.__txt = []; window.__where = ''; window.__rec = true;
  const P = CanvasRenderingContext2D.prototype;
  for (const fn of ['fillText', 'strokeText']) {
    const o = P[fn];
    P[fn] = function (s, x, y, mw) {
      try {
        if (window.__rec) {
          s = String(s);
          const m = this.measureText(s), t = this.getTransform(), sc = Math.hypot(t.a, t.b) || 1;
          let w = m.width; if (mw != null && mw < w) w = mw;
          const al = this.textAlign, l0 = al === 'center' ? x - w / 2 : (al === 'right' || al === 'end') ? x - w : x;
          const rot = Math.abs(t.b) > 1e-6;
          const L = t.a * l0 + t.c * y + t.e, R = L + w * t.a;
          window.__txt.push({ s, w: w * sc, cw: this.canvas.width, l: L, r: R, rot, fn, where: window.__where, cid: this.canvas.id || (this.canvas.width + 'x' + this.canvas.height) });
        }
      } catch (e) {}
      return o.apply(this, arguments);
    };
  }
})();
"""

# 見えている文字と、はみ出しを調べる（#ov か、画面全体）
SCAN = r"""
(root => {
  const vis = el => { if (!el || !el.getClientRects().length) return false; const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity !== 0; };
  const path = el => { const a = []; for (let e = el; e && e !== document.body && a.length < 4; e = e.parentElement) a.unshift(e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).join('.') : '')); return a.join(' > '); };
  const texts = [];
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) { const t = n.nodeValue.trim(); if (!t) continue; const el = n.parentElement; if (!vis(el)) continue; if (el.closest('[hidden]')) continue; texts.push([t, path(el)]); }
  for (const el of root.querySelectorAll('[placeholder],[title]')) if (vis(el)) { if (el.placeholder) texts.push([el.placeholder, path(el) + '[placeholder]']); if (el.title) texts.push([el.title, path(el) + '[title]']); }
  const over = [];
  for (const el of root.querySelectorAll('button, label, p, a.btn, h4, td, b, small, span, .badge, .big-logo, input')) {
    if (!vis(el)) continue;
    const panel = el.closest('.panel') || root, pr = panel.getBoundingClientRect(), r = el.getBoundingClientRect();
    if (r.width === 0) continue;
    const cs = getComputedStyle(el);
    const t = (el.innerText || el.value || '').trim().slice(0, 60);
    if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1 && !['auto', 'scroll'].includes(cs.overflowX)) over.push(['scrollWidth ' + el.scrollWidth + ' > ' + el.clientWidth, t, path(el)]);
    if (cs.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1) over.push(['…で切れている', t, path(el)]);
    const scroller = el.closest('.rk-scroll, .pager');
    if (!scroller && (r.right > pr.right + 1 || r.left < pr.left - 1)) over.push([`パネルの外（${Math.round(r.left)}〜${Math.round(r.right)} / パネル ${Math.round(pr.left)}〜${Math.round(pr.right)}）`, t, path(el)]);
  }
  const vw = document.documentElement.clientWidth, sw = document.documentElement.scrollWidth;
  if (sw > vw + 1) over.push(['ページが横にスクロールする ' + sw + ' > ' + vw, '', 'html']);
  return { texts, over };
})
"""


SYM = re.compile(r'[？！]+')   # 全角の「？」「！」だけの印（飼い主の頭の上の ？、まだのカードの ？？？）。言語によらず同じ印として使っている
SYM_SEEN = set()


def jp_leaks(texts):
    out = []
    for t, where in texts:
        rest = t
        for a in sorted(ALLOW_TEXT, key=len, reverse=True):
            rest = rest.replace(a, '')
        if where.endswith('button#sLg.btn.w'):
            continue   # 設定の言語切りかえボタンは、切りかえ先の言語の名前（「日本語」）を出す。意図どおり
        if JP.search(rest) and not JP.search(SYM.sub('', rest)):
            SYM_SEEN.add(t)   # 全角の ？ だけ：報告だけ（失敗にしない）
            continue
        if JP.search(rest):
            out.append((t, where))
    return out


def static_scan(src):
    # lt('ja', 'en') / tx('ja', 'en') の英語側（単純な文字列リテラルだけ）
    out = []
    lit = r"""('(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`)"""
    pat = re.compile(r'\b(lt|tx)\(\s*' + lit + r'\s*,\s*' + lit + r'\s*\)')
    for i, line in enumerate(src.split('\n'), 1):
        for m in pat.finditer(line):
            en = m.group(3)[1:-1]
            en2 = re.sub(r'\$\{[^}]*\}', '', en)
            for a in ALLOW_TEXT:
                en2 = en2.replace(a, '')
            if JP.search(en2):
                out.append((i, en[:70]))
    return out


def run(b):
    r = harness.Report('english')
    info = []
    src = open(harness.os.path.join(harness.ROOT, 'index.html'), encoding='utf-8').read()

    # ---------- 静的：lt/tx の英語側 ----------
    for ln, en in static_scan(src):
        # ロゴ・タイトルの副題（英語版でこっそりネコを出す）は意図どおり
        if en.strip() in ('Mischievous <span>Cat</span><small>こっそりネコ</small>', 'Mischievous Cat - こっそりネコ', '#MischievousCat #こっそりネコ', '日本語'):
            continue
        r.check(False, f'静的 index.html:{ln} lt/tx の英語側に日本語：{en!r}')

    seen_dom, seen_over, seen_cv = set(), set(), set()
    cv_wide = []

    def scan(g, where, root='#ov', hidden=False):
        res = g.page.evaluate(f'(() => {{ const f = {SCAN}; return f(document.querySelector({json.dumps(root)}) || document.body); }})()')
        for t, p in jp_leaks(res['texts']):
            key = (re.sub(r'\d+', '#', t), p.split(' > ')[-1])
            if key in seen_dom:
                continue
            seen_dom.add(key)
            if hidden:
                info.append(f'隠しテストメニューの画面に日本語 [{where}] {t[:80]!r}  ← {p}')
                continue
            r.check(False, f'DOM 日本語 [{where}] {t[:80]!r}  ← {p}')
        for why, t, p in res['over']:
            key = (why.split('（')[0].split(' ')[0], re.sub(r'\d+', '#', t), p.split(' > ')[-1])
            if key in seen_over:
                continue
            seen_over.add(key)
            r.check(False, f'DOM はみ出し [{where}] {why}：{t!r}  ← {p}')

    def canvas_check(g):
        recs = g.T('(() => { const a = window.__txt; window.__txt = []; return a; })()')
        for x in recs:
            s = x['s']
            rest = s
            for a in ALLOW_TEXT:
                rest = rest.replace(a, '')
            if x['cid'] == '1200x630':
                x['where'] = 'シェア画像（makeCard）'
            if JP.search(rest) and not JP.search(SYM.sub('', rest)):
                SYM_SEEN.add(s)
            elif JP.search(rest) and (s, x['cid']) not in seen_cv:
                seen_cv.add((s, x['cid']))
                r.check(False, f'キャンバス 日本語 [{x["where"]}] {s[:60]!r}（{x["cid"]}）')
            if x['w'] > x['cw'] + 1 and ('w', s) not in seen_cv:
                seen_cv.add(('w', s))
                r.check(False, f'キャンバス 幅オーバー [{x["where"]}] {s[:60]!r} 幅 {x["w"]:.0f} > キャンバス {x["cw"]}（{x["cid"]}）')
            elif not x['rot'] and x['cid'] == 'c' and (x['l'] < -2 or x['r'] > x['cw'] + 2) and ('c', s) not in seen_cv:
                seen_cv.add(('c', s))
                cv_wide.append(f'[{x["where"]}] {s[:50]!r} {x["l"]:.0f}〜{x["r"]:.0f} / {x["cw"]}')

    HELP = r"""
window.__draws = function (sec, every, where) {
  // 時間を進めながら、ときどき描く（描いた文字はフックで集める）
  window.__where = where || window.__where; let k = 0;
  for (let t = 0; t < sec; t += 1 / 30, k++) { update(1 / 30); if (k % every === 0) { try { draw(); hud(); } catch (e) { throw e; } } }
  try { draw(); hud(); } catch (e) { throw e; }
  return state;
};
window.__clr = function () {
  setMode('away', 99);
  for (const it of items.filter(o => !o.extra)) { items.splice(items.indexOf(it), 1); breakItem(it, PL.floor); }
  for (const k of tasks) if (!k.done) taskHit(k.id, k.need);
  update(1 / 60); return state;
};
window.__adv = function (maxT, every) {
  const L0 = level; let t = 0, k = 0;
  while (t < maxT && !(state === 'play' && level !== L0) && state !== 'endmenu' && state !== 'over') { update(1 / 30); t += 1 / 30; if (every && (k++ % every === 0)) { window.__where = 'L' + L0 + ' のあと（' + state + '）'; draw(); } }
  return [state, level];
};
"""

    def game(storage=None, mobile=True):
        st = {'nekoScoreV': '2'}
        st.update(storage or {})
        g = harness.Game(b, lang='en', storage=st, mobile=mobile)
        g.page.evaluate(HOOK)
        g.T(HELP)
        r.check(g.T('lang') == 'en', '英語モードで開く')
        return g

    # ---------- 1. 初回のタイトル・ふだんのタイトル・各画面（まっさら・何も解いていない）----------
    g = game()
    g.T("window.__where = 'title-first'; showTitle()"); g.wait(0.3); scan(g, '初回のタイトル'); scan(g, '画面全体（タイトル）', 'body')
    g.T("showSettings(showTitle)"); scan(g, '設定')
    g.T("showCatShop()"); g.wait(0.2); scan(g, 'ネコとおしゃれ（未解禁）')
    n = g.T("(() => { showCards(0); return ov.querySelectorAll('.pg-dots i').length; })()")
    for i in range(n):
        g.T(f'showCards({i})'); scan(g, f'いたずら図鑑 p{i + 1}（未取得）')
    for i in range(4):
        g.T(f'showLife({i})'); scan(g, f'通算 p{i + 1}（記録なし）')
    for t in ['world', 'daily', 'local']:
        g.T(f"showRank('{t}')"); g.wait(0.4); scan(g, f'ランキング {t}（空）')
    canvas_check(g)
    r.check(not g.errors, 'まっさら：エラー ' + str(g.errors[:3]))
    g.close()

    # ---------- 2. 1〜28 面のプレイ画面（キャンバス）。全部の面を順に遊んで、エンディング・スタッフロールも ----------
    unlock = {'nekoCats': json.dumps(['kuro', 'cha', 'saba', 'maine', 'mike', 'siam']), 'nekoEnded': '1', 'nekoTrueEnd': '1', 'nekoShared': '1', 'nekoShades': '1'}
    g = game(unlock)
    g.page.route('**/*:runQuery*', lambda rt: rt.fulfill(status=200, content_type='application/json', body=json.dumps([
        {'document': {'name': f'x{i}', 'createTime': '2026-10-20T00:00:00Z', 'fields': {
            'name': {'stringValue': nm}, 'y': {'integerValue': str(9000000 - i * 1000000)}, 's': {'integerValue': str(28 - i * 3)}, 'st': {'integerValue': '30'},
            'c': {'stringValue': ['kuro', 'cha', 'saba', 'maine', 'mike', 'siam'][i % 6]}, 'uid': {'stringValue': f'uid{i}xxxxxx'}, 'sk': {'integerValue': '123456'},
            'k': {'integerValue': str(i)}, 'v': {'integerValue': '6'}}}} for i, nm in enumerate(['Whiskers', 'MMMMMMMMMM', 'WWWWWWWWWW', 'Tom', 'Mittens', 'Shadow', 'Luna'])])))
    g.T("(() => { newRun(); state = 'play'; ov.hidden = true; })()")
    for L in range(1, 29):
        r.check(g.T('level') == L, f'面 {L} に来ている（{g.T("level")}）')
        g.T(f"window.__where = 'L{L}'")
        g.T(f"__draws(0.2, 1, 'L{L} 始まり')")                  # 面の名前
        g.T(f"__draws(3.0, 6, 'L{L} 仕掛けの札')")             # 札・飼い主のせりふ
        g.T(f"(() => {{ const m = items.filter(o => !o.extra); if (m.length) {{ items.splice(items.indexOf(m[0]), 1); breakItem(m[0], PL.floor); }} if (tasks[0] && !tasks[0].done) taskHit(tasks[0].id, tasks[0].need); }})()")
        g.T(f"__draws(0.6, 3, 'L{L} 落とした')")
        if L in (2, 6, 13, 21):
            # 見つかる演出（お守りで復活）も描く
            g.T("run.charm = 1; caught(false)"); g.T(f"__draws(4.0, 6, 'L{L} 見つかった→お守り')")
            g.T("state = 'play'")
        g.T('__clr()')
        st = g.T(f"__adv(200, 4)")
        canvas_check(g)
        if L == 12:
            r.check(st[0] == 'endmenu', f'3日目のあとエンディングの締め（{st}）')
            scan(g, 'エンディング（3日目）の締め')
            g.wait(0.6); canvas_check(g)
            g.page.click('#enCont'); g.wait(0.2)
        elif L == 28:
            r.check(st[0] == 'endmenu', f'7日目のあとほんとうのおしまいの締め（{st}）')
            scan(g, 'ほんとうのおしまいの締め')
            r.check(g.T('run.endType') == 'true', 'ほんとうのおしまい：endType true')
            share = g.T('shareText()')
            r.check(not jp_leaks([(share, '')]), f'シェアの文章（完走）に日本語：{share!r}')
            g.wait(0.6); canvas_check(g)
            g.page.click('#enRes'); g.wait(0.6)
            scan(g, '結果画面（7日間完走）'); g.wait(0.5); canvas_check(g)
            share = g.T('shareText()')
            r.check(not jp_leaks([(share, '')]), f'シェアの文章（7日間の結果）に日本語：{share!r}')
    # スタッフロールの日記：英語は単語の切れ目で折る（4.51.6）。単語の途中で切れていないか
    for et in ['normal', 'true']:
        lines = g.T(f"(() => {{ const e = run.endType; run.endType = '{et}'; const L = creditLines(); run.endType = e; return L; }})()")
        ds = [x[1] for x in lines if x[0] == 'd']
        # 日記の元の文で「前の行の最後の語 + 空白 + 次の行の最初の語」が続いていれば、単語の切れ目で折っている
        full = ' '.join(g.T(f"(() => {{ const e = run.endType; run.endType = '{et}'; const n = '{et}' === 'true' ? TRUE_DAY : END_DAY; const o = []; for (let d = 1; d <= n; d++) o.push(String(diaryOf(d))); run.endType = e; return o; }})()"))
        cuts = [f'{a!r}|{b2!r}' for a, b2 in zip(ds, ds[1:]) if not re.match(r'^\d+: ', b2) and re.search(r'[A-Za-z]$', a) and re.match(r'^[A-Za-z]', b2)
                and (a.split()[-1] + ' ' + b2.split()[0]) not in full]
        r.check(not cuts, f'スタッフロール（{et}）の日記が英単語の途中で折り返される：{cuts[:4]}')
    # 記録の画面（遊んだあと：ランキング・図鑑・通算）
    g.T("state = 'title'")
    for t in ['world', 'daily', 'local']:
        g.T(f"showRank('{t}')"); g.wait(0.5); scan(g, f'ランキング {t}（記録あり）')
    n = g.T("(() => { showCards(0); return ov.querySelectorAll('.pg-dots i').length; })()")
    for i in range(n):
        g.T(f'showCards({i})'); scan(g, f'いたずら図鑑 p{i + 1}（遊んだあと）')
    for i in range(4):
        g.T(f'showLife({i})'); scan(g, f'通算 p{i + 1}（遊んだあと）')
    g.T('showCatShop()'); g.wait(0.2); scan(g, 'ネコとおしゃれ（解禁ずみ）')
    for a in g.T('ACCS.map(a => a.id)'):
        g.T(f"(() => {{ const b = ov.querySelector('button[data-a=\"{a}\"]'); if (b && !b.disabled) b.click(); }})()")
        scan(g, f'ネコとおしゃれ きせかえ {a}')
    for i in range(6):
        g.T(f"(() => {{ const b = ov.querySelector('button[data-i=\"{i}\"]'); if (b && !b.disabled) b.click(); }})()")
        scan(g, f'ネコとおしゃれ ネコ {i}')
    g.T('showTitle()'); g.wait(0.3); scan(g, 'タイトル（遊んだあと）'); canvas_check(g)
    r.check(not g.errors, '1〜28 面：エラー ' + str(g.errors[:3]))
    g.close()

    # ---------- 3. 見つかったときの結果画面いろいろ・ポーズ・セーブありのタイトル ----------
    g = game(unlock)
    g.T("(() => { newRun(); state = 'play'; ov.hidden = true; })()")
    g.T('__clr()'); g.T('__adv(20)')
    g.T("(() => { const m = items.filter(o => !o.extra); items.splice(items.indexOf(m[0]), 1); breakItem(m[0], PL.floor); })()")
    g.T("pauseGame()"); scan(g, 'ポーズ（セーブあり）'); g.T("state = 'play'; ov.hidden = true")
    g.T("run.charm = 0; caught(false)"); g.T("__draws(4, 6, '見つかった（1日目）')")
    r.check(g.T('state') == 'over', '見つかって結果画面')
    g.wait(0.6)
    scan(g, '結果画面（1日目・この面から・名前なし）'); canvas_check(g)
    share = g.T('shareText()')
    r.check(not jp_leaks([(share, '')]), f'シェアの文章（見つかった）に日本語：{share!r}')
    g.page.click('#nmIn'); g.page.keyboard.insert_text('Kitty'); g.page.click('#nmGo'); g.wait(0.8)
    scan(g, '結果画面（名前を登録）')
    for res, lab in [({'world': {'now': 3}, 'today': {'now': 1}}, 'ランクイン'), ({'world': {'now': 0}, 'today': {'skip': True}}, '50位圏外'),
                     ({'world': {'err': True, 'code': '403'}, 'today': {'err': True, 'code': '403'}}, '送れなかった')]:
        g.T(f"(() => {{ run.res = {json.dumps(res)}; const box = ov.querySelector('.online'); if (box) box.outerHTML = onlineBox(); }})()")
        scan(g, f'結果画面（{lab}）')
    # 2 日目で見つかる → 朝からつづける
    g.page.click('#bRetry'); g.wait(0.2)
    for _ in range(4):
        g.T('__clr()'); g.T('__adv(30)')
    g.T("(() => { const m = items.filter(o => !o.extra); items.splice(items.indexOf(m[0]), 1); breakItem(m[0], PL.floor); })()")
    g.T("run.charm = 0; caught(true)"); g.T("__draws(4, 6, '時間切れ（2日目）')")
    g.wait(0.6)
    scan(g, '結果画面（2日目・朝から・時間切れ）'); canvas_check(g)
    g.T('showTitle()'); g.wait(0.3); scan(g, 'タイトル（つづきから）')
    g.page.click('#resBtn'); g.wait(0.3); scan(g, '画面全体（つづきから再開のトースト）', 'body')
    g.T("(() => { run.charm = 0; caught(true); })()"); g.T("__draws(4, 6, '時間切れ（再開のあと）')"); g.wait(0.4)
    g.T("showRank('local')"); g.wait(0.3); scan(g, 'ランキング local（結果のあと）')
    r.check(not g.errors, '結果画面：エラー ' + str(g.errors[:3]))
    g.close()

    # ---------- 4. いろいろなエンディング（確認用の再生）のキャンバス ----------
    g = game(unlock)
    n = g.T('PREVIEW_ORDER.length')
    for i in range(n):
        g.T(f'previewEnding({i})')
        et = g.T('run.endType')
        g.T(f"__draws(80, 8, 'エンディング {et}')")
        canvas_check(g)
    scan(g, 'エンディング確認用の締め（隠しテストメニューから）', hidden=True)
    r.check(not g.errors, 'エンディング：エラー ' + str(g.errors[:3]))
    g.close()

    # ---------- 5. パソコン（キー操作の案内つき）のタイトル・ポーズ ----------
    g = game(unlock, mobile=False)
    g.T('showTitle()'); g.wait(0.3); scan(g, 'タイトル（PC）'); scan(g, '画面全体（PC タイトル）', 'body')
    g.T("(() => { newRun(); state = 'play'; ov.hidden = true; })()"); g.T("__draws(1, 3, 'PC プレイ')"); scan(g, '画面全体（PC プレイ）', 'body')
    g.T('pauseGame()'); scan(g, 'ポーズ（PC）')
    g.T('showSettings(showPause)'); scan(g, '設定（PC）')
    canvas_check(g)
    r.check(not g.errors, 'PC：エラー ' + str(g.errors[:3]))
    g.close()

    if SYM_SEEN:
        info.append(f'英語モードでも全角の「？」の印を使っている（失敗にしない）：{sorted(SYM_SEEN)}')
    if cv_wide:
        info.append(f'キャンバスの文字がゲーム画面の左右の端からはみ出す（回転なし・{len(cv_wide)} 種類。吹き出しの位置などで意図的なものもありうる）：' + '; '.join(cv_wide))
    for line in info:
        print('  INFO ' + line)
    return r.done()
