# ランキングへの送信：ゲームが Firestore に POST する中身が、firestore.rules の create の条件をすべて満たすかを確かめる
# - firestore.rules の valid() を Python で書き直し（キー・型・値の範囲・名前・v・署名・デイリーのコレクション名）
# - 本物の流れ（面をクリア → 見つかる／エンディング → gameOver → postAndRefresh → sendScore）で記録を作り、送った本文を調べる
# - 送らないはずの場面（名前なし・テスト・被害額 0・自己ベストでない）で送っていないことも確かめる
# ルールではじかれる値（ランキングから黙って消える）と、ルールは通すがゲームでは出せない値を報告する
import json, hashlib, re, datetime
import harness

SIG_KEY = 'mc-k7f3a9c2'   # firestore.rules の署名の鍵（index.html の SIG_KEY と同じはず）
KEYS = ['name', 'y', 's', 'st', 'c', 'uid', 'sk', 'k', 'v', 'h']
CATS = ['kuro', 'cha', 'saba', 'maine', 'mike', 'siam']
INT64 = (-2 ** 63, 2 ** 63 - 1)


def cap_y(s):
    return 100000 * s * s + 500000 * s


# ---------- Firestore REST の値をほどく ----------
def decode(v):
    # 返り値：(型, 値)。型は rules の is int / is string に合わせる
    if 'stringValue' in v:
        return 'string', v['stringValue']
    if 'integerValue' in v:
        return 'int', int(v['integerValue'])
    if 'doubleValue' in v:
        return 'float', float(v['doubleValue'])
    if 'booleanValue' in v:
        return 'bool', v['booleanValue']
    if 'nullValue' in v:
        return 'null', None
    return 'other', v


def rules_size(s):
    # rules の string.size() はコードポイントの数。正しくない UTF-16（片割れのサロゲート）は Firestore が受け付けない
    try:
        s.encode('utf-8')
    except UnicodeEncodeError:
        return None
    return len(s)


def rules_errors(coll, fields):
    """firestore.rules の create 条件（valid と、コレクションの match）を Python で。通らない理由のリストを返す（空なら OK）"""
    e = []
    if coll != 'scores' and not re.fullmatch(r'daily-[0-9]{4}-[0-9]{2}-[0-9]{2}', coll):
        e.append(f'collection {coll!r} はどの match にも当たらない')
    keys = set(fields)
    if not keys <= set(KEYS):
        e.append(f'余分なキー {sorted(keys - set(KEYS))}')
    if not set(KEYS) <= keys:
        e.append(f'足りないキー {sorted(set(KEYS) - keys)}')
        return e
    d = {k: decode(v) for k, v in fields.items()}
    t = lambda k: d[k][0]
    val = lambda k: d[k][1]
    for k in ['y', 's', 'st', 'sk', 'k', 'v']:
        if t(k) != 'int':
            e.append(f'{k} が int でない（{t(k)}）')
        elif not INT64[0] <= val(k) <= INT64[1]:
            e.append(f'{k} が int64 の範囲外')
    for k in ['name', 'uid', 'h', 'c']:
        if t(k) != 'string':
            e.append(f'{k} が string でない（{t(k)}）')
    if e:
        return e
    n = rules_size(val('name'))
    if n is None:
        e.append(f'name が正しい UTF-16 でない（片割れのサロゲート）：{val("name")!r}')
    elif not 1 <= n <= 10:
        e.append(f'name の長さ {n}（1〜10）')
    s, y, st, sk, k = val('s'), val('y'), val('st'), val('sk'), val('k')
    if not 1 <= s <= 28:
        e.append(f's={s}（1〜28）')
    if not 1 <= y <= cap_y(s):
        e.append(f'y={y}（1〜{cap_y(s)}）')
    if not 0 <= st <= s * 3:
        e.append(f'st={st}（0〜{s * 3}）')
    if val('c') not in CATS:
        e.append(f'c={val("c")!r}')
    un = rules_size(val('uid'))
    if un is None or not 8 <= un <= 40:
        e.append(f'uid の長さ {un}（8〜40）')
    if not 0 <= sk <= y:
        e.append(f'sk={sk}（0〜y={y}）')
    if not 0 <= k <= 999:
        e.append(f'k={k}（0〜999）')
    if val('v') != 6:
        e.append(f'v={val("v")}（6）')
    want = hashlib.sha256(f'{y}|{s}|{st}|{sk}|{k}|{val("uid")}|{SIG_KEY}'.encode('utf-8', 'surrogatepass')).hexdigest()
    if val('h').lower() != want:
        e.append('署名 h が合わない')
    return e


def plain(fields):
    return {k: decode(v)[1] for k, v in fields.items()}


# ---------- ゲームを進める道具（ゲームの中で動かす）----------
HELPERS = r"""
window.__clr = function() {
  // その面のもの（小物以外）を全部落として、お題を全部こなす（飼い主は留守のまま）。落とし方は本物（updItems → breakItem）
  setMode('away', 99);
  for (const it of items.filter(o => !o.extra)) if (it.state === 'rest' && it.plat) { it.y0 = it.plat.y; it.y = it.plat.y; it.plat = null; it.state = 'fall'; it.vy = 0; it.vx = 0; it.vr = 1; }
  for (let t = 0; t < 1.5 && state === 'play'; t += 1 / 60) { setMode('away', 99); update(1 / 60); }
  for (const it of items.filter(o => !o.extra)) { items.splice(items.indexOf(it), 1); breakItem(it, PL.floor); }   // 柔らかい所などに止まったもの
  for (const k of tasks) if (!k.done) taskHit(k.id, k.need);
  update(1 / 60);
  return state;
};
window.__adv = function(maxT) {
  // 次の面が始まる・締めの画面・結果画面になるまで時間を進める（クリア札・日の終わり・エンディング・スタッフロール）
  const L0 = level; let t = 0;
  while (t < maxT && !(state === 'play' && level !== L0) && state !== 'endmenu' && state !== 'over') { update(1 / 30); t += 1 / 30; }
  return [state, level];
};
window.__some = function(n) {
  // その面で n 個だけ落とす（クリアしない）
  setMode('away', 99);
  for (const it of items.filter(o => !o.extra).slice(0, n)) { items.splice(items.indexOf(it), 1); breakItem(it, PL.floor); }
  return run.yen;
};
window.__caught = function() {
  // 見つかる（お守りなし）→ 演出のあと gameOver
  run.charm = 0; caught(false); let t = 0;
  while (state === 'caught' && t < 10) { update(1 / 30); t += 1 / 30; }
  return state;
};
"""


def writes(g, since=0):
    """Firestore への書き込み（runQuery 以外の POST）を (コレクション, fields, url) で"""
    out = []
    for r in g.sent[since:]:
        u = r['url']
        if 'firestore.googleapis.com' not in u or r['method'] != 'POST' or ':runQuery' in u:
            continue
        m = re.search(r'/documents/([^/?]+)(?:/([^?]*))?\?', u)
        coll = m.group(1) if m else '?'
        body = json.loads(r['body'] or '{}')
        out.append((coll, body.get('fields', {}), u, m and m.group(2)))
    return out


def wait_res(g, sec=4.0):
    # sendScore が終わる（run.res が入る）まで待つ
    for _ in range(int(sec / 0.1)):
        if g.T('!!(run && run.res)'):
            return True
        g.wait(0.1)
    return False


def jst_dates(g):
    # その時点のページの時計での日本時間の日付
    ms = g.T('Date.now()')
    return (datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime('%Y-%m-%d')


def new_game(b, name='', extra=None):
    st = {'nekoScoreV': '2'}   # 4.44.0 の「自己ベストを一度だけ消す」を済ませておく（でないと仕込んだ自己ベストが消える）
    if name:
        st['nekoName'] = name
    st.update(extra or {})
    g = harness.Game(b, storage=st)
    g.T(HELPERS)
    return g


def run(b):
    r = harness.Report('ranking')
    info = []
    max_ratio = [0.0, '']

    def check_writes(g, ws, what, expect=None, day=None, real=True):
        # 送った記録が全部ルールを通るか。expect：期待する値（s, k など）
        for coll, f, u, docid in ws:
            errs = rules_errors(coll, f)
            r.check(not errs, f'{what}: {coll} への記録がルールではじかれる → {errs}  {plain(f)}')
            r.check(not docid, f'{what}: 文書 ID 付きで送っている（{docid}）。ルールの match は /scores/{{id}} で、create は自動 ID 前提')
            p = plain(f)
            if coll.startswith('daily-') and day:
                r.check(coll in ('daily-' + day[0], 'daily-' + day[1]), f'{what}: デイリーのコレクション {coll} が日本時間の日付 {day} と違う')
            for k, v in (expect or {}).items():
                r.check(p.get(k) == v, f'{what}: {k}={p.get(k)!r}（期待 {v!r}）')
            if real and 's' in p and 'y' in p and p['s'] >= 1:   # 上限の余裕は、ゲームで作った記録だけで測る
                ratio = p['y'] / cap_y(p['s'])
                if ratio > max_ratio[0]:
                    max_ratio[0], max_ratio[1] = ratio, f"{what} s={p['s']} y={p['y']}"
        colls = sorted(c for c, *_ in ws)
        return colls

    def today(g):
        d = jst_dates(g)
        return d

    # ===== 1. 1 日目で見つかる → この面からやりなおす → また見つかる =====
    g = new_game(b, 'ねこ太郎')
    g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
    g.T('__clr()'); g.T('__adv(20)')
    g.T('__some(1)')
    r.check(g.T('__caught()') == 'over', '1日目：見つかって結果画面になる')
    r.check(wait_res(g), '1日目：送信が終わる')
    ws = writes(g)
    d0 = today(g)
    colls = check_writes(g, ws, '1日目で見つかった', {'s': 2, 'k': 0, 'name': 'ねこ太郎', 'c': g.T('CATS[selCat].id')}, (d0, d0))
    r.check(colls == sorted(['scores', 'daily-' + d0]), f'1日目：総合と今日の両方に送る（{colls}）')
    # この面からやりなおす（続けた回数 k が 1 になる）→ 2〜3 面クリア → 4 面で見つかる
    n0 = len(g.sent)
    r.check(g.page.locator('#bRetry').count() == 1, '1日目：「この面からやりなおす」がある')
    if g.page.locator('#bRetry').count():
        g.page.click('#bRetry')
        g.T('__clr()'); g.T('__adv(20)'); g.T('__clr()'); g.T('__adv(20)')
        g.T('__some(2)'); g.T('run.res = null'); g.T('__caught()')
        r.check(wait_res(g), 'やりなおし：送信が終わる')
        ws = writes(g, n0)
        check_writes(g, ws, 'やりなおして4面で見つかった', {'s': 4, 'k': 1}, (today(g), today(g)))
        r.check(len(ws) == 2, f'やりなおし：自己ベストを更新したので 2 件送る（{len(ws)} 件）')
    r.check(not g.errors, '1日目：エラー ' + str(g.errors[:3]))
    g.close()

    # ===== 2. 3 日目のエンディングまで（名前は 10 文字ちょうど）→ ここでおわって結果 =====
    g = new_game(b, 'abcdefghij')
    g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
    for _ in range(12):
        g.T('__clr()'); st = g.T('__adv(120)')
    r.check(st[0] == 'endmenu' and st[1] == 12, f'3日目の夜を越えて締めの画面（{st}）')
    r.check(wait_res(g), 'エンディング：送信が終わる')
    ws = writes(g)
    check_writes(g, ws, 'エンディング（3日目）', {'s': 12, 'k': 0, 'name': 'abcdefghij'}, (today(g), today(g)))
    r.check(len(ws) == 2, f'エンディング：2 件送る（{len(ws)} 件）')
    n0 = len(g.sent)
    g.page.click('#enRes'); g.wait(0.6)
    r.check(g.T('state') == 'over', 'エンディング：ここでおわって結果画面')
    g.wait(0.8)
    r.check(len(writes(g, n0)) == 0, 'エンディングのあと結果画面：同じ記録をもう一度送らない（自己ベストでない）')
    r.check(not g.errors, 'エンディング：エラー ' + str(g.errors[:3]))
    g.close()

    # ===== 3. 7 日目まで（絵文字の名前・きせかえで多めに稼ぐ・5 日目で見つかって朝から続ける）=====
    g = new_game(b, '😺ネコ🐾', {'nekoEnded': '1'})
    g.T("(()=>{ newRun(); selAcc='hat'; state='play'; ov.hidden=true; })()")
    for _ in range(12):
        g.T('__clr()'); g.T('__adv(120)')
    wait_res(g)
    g.page.click('#enCont'); g.wait(0.2)
    r.check(g.T('[state, level]') == ['play', 13], '4日目へつづける')
    g.T("selAcc='crown'")
    for _ in range(13, 18):
        g.T('__clr()'); g.T('__adv(120)')
    r.check(g.T('level') == 18, f'5日目の2面まで進む（{g.T("level")}）')
    g.T('__some(3)'); n0 = len(g.sent); g.T('run.res = null'); g.T('__caught()')
    r.check(wait_res(g), '5日目で見つかる：送信が終わる')
    check_writes(g, writes(g, n0), '5日目で見つかった', {'s': 18, 'k': 0}, (today(g), today(g)))
    r.check(g.page.locator('#bCont').count() == 1, '5日目：朝からつづけるがある')
    g.page.click('#bCont'); g.wait(0.2)
    r.check(g.T('[level, run.conts]') == [17, 1], f'朝から続ける：17面・続けた回数 1（{g.T("[level, run.conts]")}）')
    g.T("selAcc='medal'")
    n0 = len(g.sent)
    for _ in range(17, 29):
        g.T('__clr()'); st = g.T('__adv(200)')
    r.check(st[0] == 'endmenu' and st[1] == 28, f'7日目の夜を越えてほんとうのおしまい（{st}）')
    r.check(wait_res(g), 'ほんとうのおしまい：送信が終わる')
    ws = writes(g, n0)
    check_writes(g, ws, 'ほんとうのおしまい（7日目・続け1回）', {'s': 28, 'k': 1, 'name': '😺ネコ🐾'}, (today(g), today(g)))
    r.check(len(ws) == 2, f'ほんとうのおしまい：2 件送る（{len(ws)} 件）')
    final = plain(ws[-1][1]) if ws else {}
    info.append(f'7日間の「全部落とす」走り：y={final.get("y")} sk={final.get("sk")} st={final.get("st")} cap(28)={cap_y(28)}')
    r.check(not g.errors, '7日目まで：エラー ' + str(g.errors[:3]))
    g.close()

    # ===== 4. 被害額の端（本物の sendScore に、ありうる値・ありえない値を入れる）=====
    g = new_game(b, 'edge')
    reset = "(()=>{ for (const k of Object.keys(localStorage)) if (k.startsWith('nekoDailyBest') || k === 'nekoWorldBest') localStorage.removeItem(k); })()"

    def send_with(js, label):
        g.T(reset)
        g.T("(()=>{ newRun(); state='over'; ov.hidden=false; })()")
        g.T(js)
        n = len(g.sent)
        g.T('run.res = null; sendScore()')
        wait_res(g, 3)
        return writes(g, n), g.T('run.res')

    for s in [1, 4, 12, 28]:
        ws, res = send_with(f"run.stage={s}; run.yen={cap_y(s)}; run.skill={cap_y(s)}; run.stars={3 * s}; run.conts=999", f'cap s={s}')
        check_writes(g, ws, f'上限ちょうど s={s}（sk=y・st=3s・k=999）', {'y': cap_y(s), 'sk': cap_y(s), 'st': 3 * s, 'k': 999}, real=False)
        r.check(len(ws) == 2, f'上限ちょうど s={s}：送る')
        ws, res = send_with(f"run.stage={s}; run.yen={cap_y(s) + 1}", f'cap+1 s={s}')
        r.check(len(ws) == 0 and res and res.get('world', {}).get('code') == 'cap', f'上限+1 s={s}：送らず cap のエラーにする（{res}）')
    ws, res = send_with("run.stage=1; run.yen=1; run.skill=0", 'y=1')
    check_writes(g, ws, '被害額 ¥1', {'y': 1, 'sk': 0}, real=False)
    r.check(len(ws) == 2, '被害額 ¥1：送る')
    ws, res = send_with("run.stage=1; run.yen=0.4; run.skill=0.4", 'y=0.4')
    r.check(len(ws) == 0, f'被害額 ¥0.4（四捨五入で 0）：送らない（{len(ws)} 件）')
    ws, res = send_with("run.stage=3; run.yen=1234.5; run.skill=99999", 'frac')
    check_writes(g, ws, '端数と腕前>被害額', {'y': 1235, 'sk': 1235}, real=False)
    ws, res = send_with("run.stage=5; run.yen=50000; run.conts=5000", 'k>999')
    check_writes(g, ws, '続けた回数 5000', {'k': 999}, real=False)
    # 端末の ID が短い・長い（古い版の値など）
    g.T("myUid = 'abc'")
    ws, res = send_with("run.stage=2; run.yen=5000", 'uid short')
    for coll, f, *_ in ws:
        if rules_errors(coll, f):
            info.append(f'端末 ID が 8 文字未満（localStorage nekoUid が壊れた等）だとルールではじかれる：{rules_errors(coll, f)}（ゲームが作る ID は 9〜16 文字なので通常は起きない）')
            break
    g.close()

    # ===== 5. 送らないはずの場面 =====
    def no_write(name, js, label, storage=None, expect=0, page_js=None):
        g = new_game(b, name, storage)
        if page_js:
            page_js(g)
        g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
        g.T(js)
        n = len(g.sent)
        g.T('__caught()')
        wait_res(g, 2 if expect else 1.2)
        ws = writes(g, n)
        r.check(len(ws) == expect, f'{label}：書き込み {len(ws)} 件（期待 {expect}）{[c for c, *_ in ws]}')
        g.close()
        return ws

    no_write('', "__clr(); __adv(20); __some(2)", '名前なし')
    no_write('tester', "run.test = true; __clr(); __adv(20); __some(2)", 'テストの回（run.test）')
    no_write('tester', "", '被害額 0')
    big = '999999999'
    g = new_game(b, 'tester', {'nekoWorldBest': big})
    d = jst_dates(g)
    g.close()
    no_write('tester', "__clr(); __adv(20); __some(2)", '自己ベストでない（総合も今日も上）', {'nekoWorldBest': big, 'nekoDailyBest-' + d: big})
    ws = no_write('tester', "__clr(); __adv(20); __some(2)", '総合だけ自己ベストでない → 今日だけ送る', {'nekoWorldBest': big}, expect=1)
    r.check([c for c, *_ in ws] == ['daily-' + d], f'今日だけ送る先 {[c for c, *_ in ws]}')
    # 一覧（runQuery）に自分のもっと良い記録があるとき：端末に覚えていなくても送らない
    def own_list(g):
        uid = g.T('myUid')
        doc = [{'document': {'name': 'x', 'fields': {'name': {'stringValue': 'tester'}, 'y': {'integerValue': str(cap_y(28))}, 's': {'integerValue': '28'},
                                                     'st': {'integerValue': '0'}, 'c': {'stringValue': 'cha'}, 'uid': {'stringValue': uid}, 'sk': {'integerValue': '0'},
                                                     'k': {'integerValue': '0'}, 'v': {'integerValue': '6'}}, 'createTime': '2026-01-01T00:00:00Z'}}]
        g.page.route('**/*:runQuery*', lambda rt: rt.fulfill(status=200, content_type='application/json', body=json.dumps(doc)))
    no_write('tester', "__clr(); __adv(20); __some(2)", '一覧に自分のもっと良い記録がある（端末の記録は消えた）', page_js=own_list)

    # ===== 6. 結果画面で名前を登録して送る（本物の入力欄から）=====
    for typed, want in [('  ねこ<b>た  ', 'ねこbた'), ('Ｎｅｋｏ🐈‍⬛', 'Ｎｅｋｏ🐈‍⬛'), ('あいうえおかきくけ😺', 'あいうえおかきくけ'), ('x', 'x')]:
        g = new_game(b, '')
        g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
        g.T('__clr(); __adv(20); __some(1)'); g.T('__caught()')
        n = len(g.sent)
        g.page.click('#nmIn'); g.page.keyboard.insert_text(typed); g.page.click('#nmGo')
        wait_res(g, 3)
        ws = writes(g, n)
        r.check(len(ws) == 2, f'名前 {typed!r} を登録：2 件送る（{len(ws)}）')
        check_writes(g, ws, f'名前 {typed!r}', {'name': want}, (today(g), today(g)))
        g.close()
    g = new_game(b, '')
    g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
    g.T('__clr(); __adv(20); __some(1)'); g.T('__caught()')
    for bad in ['   ', 'fuckcat', '<<>>']:
        n = len(g.sent)
        g.page.fill('#nmIn', ''); g.page.click('#nmIn'); g.page.keyboard.insert_text(bad); g.page.click('#nmGo'); g.wait(0.5)
        r.check(len(writes(g, n)) == 0 and g.page.inner_text('#nmErr') != '', f'名前 {bad!r}：送らずにエラーを出す')
    # cleanName だけを直接：10 単位目でサロゲートを切る（入力欄の maxlength は切らないので、ふつうは起きない）
    cut = g.T("JSON.stringify(cleanName(' あいうえおかきくけ😺'))")
    if '\\ud83d' in cut:
        info.append(f'cleanName は UTF-16 の 10 単位で切るので、絵文字の片割れが残ることがある（{cut}）。入力欄は maxlength=10 で片割れを作らないため、いまの画面からは起きない')
    g.close()

    # ===== 7. 日付の境目：日本時間 23:59:59 に始めて 0:00 をまたいで送る =====
    g = new_game(b, 'midnight')
    # 次の日本時間 0:00 の 1.2 秒前に時計を合わせる
    g.T("(()=>{ const D = Date.now, n = D(), j = n + 9 * 3600e3, next = (Math.floor(j / 864e5) + 1) * 864e5 - 9 * 3600e3; const k = next - 1200 - n; Date.now = () => D() + k; })()")
    d_before = jst_dates(g)
    g.T("(()=>{ newRun(); state='play'; ov.hidden=true; })()")
    g.T('__some(2)')
    g.wait(1.5)
    d_after = jst_dates(g)
    n = len(g.sent)
    g.T('__caught()'); wait_res(g, 3)
    ws = writes(g, n)
    check_writes(g, ws, '0:00 をまたいだ', None, (d_after, d_after))
    if d_before != d_after:
        info.append(f'日本時間 0:00 をまたいだ回：{d_before} の配置で遊んだ記録が daily-{d_after} に載る（ルールは日付を確かめない。仕様として受け入れるかは要判断）')
    g.close()

    # ===== 7b. ルールの書き直し自体の確認：わざと壊した記録をはじくこと =====
    I = lambda v: {'integerValue': str(v)}
    S = lambda v: {'stringValue': v}

    def rec(**kw):
        p = dict(name='n', y=1000, s=2, st=3, c='cha', uid='abcdefgh1', sk=10, k=0, v=6)
        p.update(kw)
        h = hashlib.sha256(f"{p['y']}|{p['s']}|{p['st']}|{p['sk']}|{p['k']}|{p['uid']}|{SIG_KEY}".encode('utf-8', 'surrogatepass')).hexdigest()
        f = {k: (S(v) if isinstance(v, str) else I(v)) for k, v in p.items()}
        f['h'] = S(h)
        return f
    r.check(not rules_errors('scores', rec()) and not rules_errors('daily-2026-10-20', rec()), '検査役：正しい記録を通す')
    bad = [('daily-2026-1-01', rec()), ('scores', rec(s=29)), ('scores', rec(y=cap_y(2) + 1)), ('scores', rec(st=7)), ('scores', rec(sk=1001)),
           ('scores', rec(k=1000)), ('scores', rec(v=5)), ('scores', rec(c='tora')), ('scores', rec(name='')), ('scores', rec(name='12345678901')),
           ('scores', rec(uid='short')), ('scores', rec(name='a\ud83d')), ('scores', dict(rec(), y={'doubleValue': 1000.0})), ('scores', dict(rec(), x=I(1))),
           ('scores', dict(rec(), h=S('0' * 64)))]
    for coll, f in bad:
        r.check(bool(rules_errors(coll, f)), f'検査役：壊した記録をはじく {coll} {plain(f)!r}')

    # ===== 8. ルールは通すが、ゲームでは出せない値（ルールの読み取りからの報告）=====
    info += [
        f'ルールの被害額の上限は 100000·s²+500000·s。全部の面で全部まとめて落とし、きせかえも使った走りでも上限の {max_ratio[0] * 100:.0f}%（{max_ratio[1]}）。上限は約 {1 / max(max_ratio[0], 1e-9):.1f} 倍の余裕',
        'ルールは sk ≤ y だけを見る：sk = y（被害額が全部腕前）や、st = 3·s でも被害額が ¥1 のような組み合わせも通る（ゲームでは出ない）',
        'ルールは k ≤ 999 だけを見る：1 面目（s=1）で k>0 も通る（ゲームでは続けられるのは 1 日目の 2 面目以降のやりなおしと 2 日目以降の朝から）',
        'ルールは daily-YYYY-MM-DD の日付が今日かを見ない：過去・未来の日のデイリーにも書ける（ゲームは今日の日付にしか送らない）',
        'ルールは name の中身（制御文字・< >・よくない言葉）を見ない：ゲームの cleanName ではじくものも、直接 POST すれば通る',
        'ルールは c がその端末で使えるネコかを見ない・uid と送り主を結び付けない（署名の鍵はページに書いてある）',
    ]
    for line in info:
        print('  INFO ' + line)
    return r.done()
