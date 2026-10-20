# 保存データの引き継ぎテスト：前の版で遊んだ人の localStorage を、いまの版で開いても壊れないか
# 前の版の index.html を git から取り出し、別の場所・別のポートで開いて本当に遊び（セーブ・カード・記録を作る）、
# その localStorage をまるごと、いまの版に持ってくる。壊れた値（JSON でないもの）でも落ちないかも調べる
# git の履歴が浅い（shallow）ときは、NEKO_GIT_DIR に全部の履歴がある git の場所を渡す（例：git clone --bare で作ったもの）
import os, json, shutil, subprocess, threading, functools, http.server, socketserver, tempfile
import harness
from test_flows import advance, play_to, clear_stage, get_caught, to_ending, click, text, new_run, CLEAR_JS

VERSIONS = ['4.40.0', '4.43.0', '4.45.0', '4.48.0', '4.50.0']
GIT_DIR = os.environ.get('NEKO_GIT_DIR')
OLD_ROOT = os.path.join(tempfile.gettempdir(), 'nk_old_' + str(os.getpid()))
_servers = {}


def git(*a):
    cmd = ['git'] + (['--git-dir', GIT_DIR] if GIT_DIR else ['-C', harness.ROOT]) + list(a)
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def find_rev(ver):
    for line in git('log', '--all', '--oneline').splitlines():
        h, _, msg = line.partition(' ')
        if msg.startswith(ver + ':'):
            return h
    return None


def build_old(ver, html):
    # 前の版を別の場所に作る（harness.build と同じく、最後に __T を足し、サービスワーカーは空にする）
    d = os.path.join(OLD_ROOT, ver)
    if os.path.isdir(d):
        shutil.rmtree(d)
    shutil.copytree(harness.SITE, d)   # 絵・音などはいまの版のものを使う（ページは前の版）
    i = html.rfind('})();')
    open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(html[:i] + 'window.__T = s => eval(s);\n' + html[i:])
    open(os.path.join(d, 'sw.js'), 'w', encoding='utf-8').write('// テストでは使わない\n')
    return d


def serve_dir(d):
    # 版ごとに別のポート（＝別のオリジン。localStorage も別になる）
    if d in _servers:
        return _servers[d].server_address[1]
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    s = socketserver.ThreadingTCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=d))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    _servers[d] = s
    return s.server_address[1]


class OldGame(harness.Game):
    # 前の版を開く Game（URL だけが違う）
    def __init__(self, browser, port, **kw):
        self.port = port
        super().__init__(browser, **kw)

    def open(self):
        self.page.goto(f'http://127.0.0.1:{self.port}/index.html')
        self.page.wait_for_function('() => !!window.__T')
        self.page.wait_for_timeout(300)


PREFS_JS = '''(() => {
  myName = 'テストネコ'; store.set('nekoName', myName);
  SET.bgm = 33; store.set('nekoBgmVol', '33'); SET.vib = false; store.set('nekoVib', '0'); store.set('nekoSwap', '1');
  const k = CATS.findIndex(c => c.id === 'kuro'), s = CATS.findIndex(c => c.id === 'siam'), i = catsOpen.has('kuro') ? k : catsOpen.has('siam') ? s : selCat;
  selCat = i; store.set('nekoCat', String(i));
  const a = ACCS.find(a => a.id === 'medal' && accOk(a)) || ACCS.find(a => a.id !== 'none' && accOk(a));
  if (a) { selAcc = a.id; store.set('nekoAcc', a.id); }
  return { cat: CATS[selCat].id, acc: selAcc }; })()'''


def play_old(b, ver, port, r):
    # 前の版で本当に遊ぶ：エンディング → 4日目 → 見つかる（A）→ 好みを設定 → 1日目から → 2日目で見つかる（B）
    g = OldGame(b, port)
    errs0 = []
    r.check(g.T('APP_VER') == ver, f"{ver}：前の版が開けた {g.T('APP_VER')}")
    to_ending(g, r, f'{ver} 前の版')
    r.check(click(g, '#enCont', r, f'{ver} 前の版'), f'{ver}：4日目へ')
    r.check(play_to(g, 14), f'{ver}：前の版で 14面へ')
    res = get_caught(g)
    r.check(res['state'] == 'over', f'{ver}：前の版で 4日目に見つかる {res}')
    st_a = g.storage()
    prefs = g.T(PREFS_JS)
    r.check(click(g, '#bAgain', r, f'{ver} 前の版'), f'{ver}：1日目からやりなおす')
    if g.T('state') == 'pause' or g.T('level') != 1:
        new_run(g)
    r.check(play_to(g, 6), f'{ver}：前の版で 6面へ')
    res = get_caught(g)
    r.check(res['state'] == 'over', f'{ver}：前の版で 2日目に見つかる {res}')
    st_b = g.storage()
    errs0 = list(g.errors)
    g.close()
    return st_a, st_b, prefs, errs0


def jl(s, k, d):
    try:
        v = json.loads(s.get(k) or 'null')
        return d if v is None else v
    except Exception:
        return d


CUR_JS = '''(() => ({ cards: [...cardsGot], titles: [...unlocked], cats: [...catsOpen], endings: [...endingsSeen], bestYen, rank: ranking.length,
  life: JSON.parse(JSON.stringify(LIFE)), selAcc, accValid: ACCS.some(a => a.id === selAcc && accOk(a)), cat: CATS[selCat].id,
  bgm: SET.bgm, vib: SET.vib, swap: SET.swap, name: myName, lang, state }))()'''


def check_new(b, r, ver, st, prefs, tag, exp_level):
    # いまの版で、前の版の localStorage をそのまま開く
    g = harness.Game(b, storage=st)
    r.check(not g.errors, f'{ver}{tag}：開いてエラーなし ' + str(g.errors[:3]))
    c = g.T(CUR_JS)
    r.check(c['state'] == 'title', f"{ver}{tag}：タイトル {c['state']}")
    old_cards, old_titles, old_cats = jl(st, 'nekoCards', []), jl(st, 'nekoTitles', []), jl(st, 'nekoCats', [])
    r.check(set(c['cards']) >= set(old_cards), f"{ver}{tag}：カードが残る {len(c['cards'])}/{len(old_cards)} 消えた {set(old_cards) - set(c['cards'])}")
    r.check(set(c['titles']) >= set(old_titles), f'{ver}{tag}：称号が残る')
    r.check(set(c['cats']) >= set(old_cats), f'{ver}{tag}：ネコが残る {old_cats} → {c["cats"]}')
    r.check(set(c['endings']) >= set(jl(st, 'nekoEndings', [])), f'{ver}{tag}：見たエンディング')
    r.check(c['bestYen'] == float(st.get('nekoBestYen') or 0), f"{ver}{tag}：自己ベスト {c['bestYen']} / {st.get('nekoBestYen')}")
    if st.get('nekoScoreV') == '2':   # 4.44.0 より前の端末のランキングは、点の付け方が違うので一度だけ消す（仕様）
        r.check(c['rank'] == len(jl(st, 'nekoRank', [])), f"{ver}{tag}：端末のランキング {c['rank']}")
    old_life = jl(st, 'nekoLife', {})
    low = [k for k, v in old_life.items() if isinstance(v, (int, float)) and (c['life'].get(k) or 0) < v]
    r.check(not low, f'{ver}{tag}：通算記録が減らない {low}')
    for k in ('broke', 'cause', 'rooms'):
        if isinstance(old_life.get(k), dict):
            r.check(all((c['life'].get(k) or {}).get(x, 0) >= v for x, v in old_life[k].items()), f'{ver}{tag}：通算記録 {k}')
    r.check(c['accValid'], f"{ver}{tag}：選んでいるきせかえが使える {c['selAcc']}")
    if prefs and st.get('nekoAcc') == prefs['acc']:
        r.check(c['selAcc'] == prefs['acc'], f"{ver}{tag}：きせかえを覚えている {c['selAcc']} / {prefs['acc']}")
        r.check(c['cat'] == prefs['cat'], f"{ver}{tag}：ネコを覚えている {c['cat']} / {prefs['cat']}")
        r.check(c['bgm'] == 33 and c['vib'] is False and c['swap'] is True, f"{ver}{tag}：設定 bgm={c['bgm']} vib={c['vib']} swap={c['swap']}")
        r.check(c['name'] == 'テストネコ', f"{ver}{tag}：名前 {c['name']!r}")
    # つづきから
    sv = jl(st, 'nekoSave', None)
    bt = text(g, '#resBtn')
    r.check(bt is not None and 'つづきから' in bt and '朝から' in bt, f'{ver}{tag}：「つづきから（朝から）」 {bt!r}')
    if not sv or bt is None:
        g.close(); return
    r.check(sv['level'] == exp_level, f"{ver}{tag}：前の版のセーブ {sv['level']}面")
    conts0, lconts0 = sv['pk']['run'].get('conts') or 0, old_life.get('conts') or 0
    click(g, '#resBtn', r, f'{ver}{tag}')
    g.wait(0.2)
    s = g.T('({ state, level, yen: run.yen, stars: run.stars, conts: run.conts || 0, lc: LIFE.conts || 0, ck: run.ck && run.ck.level, album: (run.album || []).length })')
    r.check(s['state'] == 'play' and s['level'] == exp_level, f"{ver}{tag}：{exp_level}面から再開 {s['state']} {s['level']}")
    r.check(s['yen'] == sv['pk']['run']['yen'] and s['stars'] == sv['pk']['run']['stars'], f"{ver}{tag}：被害額・★ {s['yen']}/{sv['pk']['run']['yen']}")
    r.check(s['conts'] == conts0 + 1 and s['lc'] == lconts0 + 1, f"{ver}{tag}：続けた回数 +1 {conts0}→{s['conts']} 通算 {lconts0}→{s['lc']}")
    r.check(s['album'] == len(sv['pk'].get('album') or []), f"{ver}{tag}：写真 {s['album']}")
    # 数秒ふつうに遊ぶ（見つかってもよい。エラーが出ないこと）
    st2 = g.step(3)
    r.check(not g.errors, f'{ver}{tag}：再開して 3 秒遊んでもエラーなし ' + str(g.errors[:3]))
    if st2 == 'play':
        r.check(play_to(g, exp_level + 1), f'{ver}{tag}：再開した面をクリアできる')
        res = get_caught(g)
        r.check(res['state'] == 'over' and text(g, '#bCont') is not None, f'{ver}{tag}：見つかったら朝からつづけられる')
        click(g, '#bCont', r, f'{ver}{tag}')
        r.check(g.T('level') == exp_level and g.T('state') == 'play', f"{ver}{tag}：朝から {g.T('level')}")
    r.check(not g.errors, f'{ver}{tag}：最後までエラーなし ' + str(g.errors[:3]))
    g.close()


def t_versions(b, r):
    ran = []
    for ver in VERSIONS:
        h = find_rev(ver)
        if not h:
            print(f'  （{ver} は git の履歴にない。NEKO_GIT_DIR に全部の履歴を渡すと調べる）')
            continue
        html = git('show', f'{h}:index.html')
        port = serve_dir(build_old(ver, html))
        st_a, st_b, prefs, e0 = play_old(b, ver, port, r)
        print(f"  {ver} で作ったデータ：カード {len(jl(st_b, 'nekoCards', []))} 枚・称号 {len(jl(st_b, 'nekoTitles', []))}・ネコ {jl(st_b, 'nekoCats', [])}"
              f"・きせかえ {st_b.get('nekoAcc')}・自己ベスト {st_b.get('nekoBestYen')}・ランキング {len(jl(st_b, 'nekoRank', []))} 件"
              f"・遊んだ回数 {jl(st_b, 'nekoLife', {}).get('plays')}・セーブ {jl(st_b, 'nekoSave', {}).get('level')}面（A は {jl(st_a, 'nekoSave', {}).get('level')}面）")
        r.check(len(jl(st_b, 'nekoCards', [])) > 0 and jl(st_b, 'nekoLife', {}).get('plays', 0) >= 2 and st_b.get('nekoEnded') == '1', f'{ver}：前の版で記録ができた')
        if e0:
            print(f'  参考：{ver} 自体のエラー', e0[:3])
        check_new(b, r, ver, st_a, None, '（4日目のセーブ）', 13)
        check_new(b, r, ver, st_b, prefs, '（2日目のセーブ）', 5)
        ran.append(ver)
    print('  調べた前の版:', ran)
    r.check(len(ran) >= 3, f'前の版を 3 つ以上調べた {ran}')


def t_corrupt(b, r):
    # JSON として読めない値
    bad = {k: '{bad' for k in ('nekoCards', 'nekoLife', 'nekoSave', 'nekoTitles', 'nekoCats', 'nekoRank', 'nekoEndings', 'nekoCardPics', 'nekoLearned', 'nekoFail', 'nekoClr', 'nekoLastErr')}
    play_corrupt(b, r, bad, '壊れた値（JSON でない）')
    # 数のはずの所に数でない値（ネコの番号・きせかえ・自己ベスト・音量）
    play_corrupt(b, r, {'nekoBestYen': 'abc', 'nekoCat': 'xyz', 'nekoAcc': 'nosuch'}, '数でない値')
    # 音量が数でない：BGM・効果音それぞれ。音が鳴らせて、エラーが出ないこと
    for k in ('nekoBgmVol', 'nekoSeVol'):
        g = harness.Game(b, storage={k: 'loud'})
        click(g, '#goBtn', r, k)
        g.wait(0.3)
        r.check(g.T('!!ac'), f'{k}=loud：音が使える（AudioContext ができる）')
        r.check(not g.errors, f'{k}=loud：エラーなし ' + str(g.errors[:2]))
        g.close()
    # JSON としては読めるが、形が違う値
    play_corrupt(b, r, {'nekoLife': '"abc"', 'nekoCards': '123', 'nekoTitles': '{}', 'nekoCats': '5', 'nekoRank': '{"y":1}', 'nekoEndings': 'true'}, '形が違う値')
    # セーブの中身が欠けている（v と level はあるが pk が空）
    g = harness.Game(b, storage={'nekoSave': json.dumps({'v': 1, 'level': 5, 'pk': {}}), 'nekoLife': json.dumps({'plays': 1}), 'nekoBestYen': '100'})
    r.check(not g.errors, '欠けたセーブ：開いてエラーなし ' + str(g.errors[:3]))
    if text(g, '#resBtn') is not None:
        click(g, '#resBtn', r, '欠けたセーブ')
        g.wait(0.3)
        r.check(not g.errors, '欠けたセーブ：「つづきから」を押してもエラーなし ' + str(g.errors[:2]))
        r.check(g.T('state') == 'play' or (g.T('state') == 'title' and not g.T('ov.hidden')),
                f"欠けたセーブ：遊べるか、タイトルが見えたまま（state={g.T('state')} ov.hidden={g.T('ov.hidden')}）")
    g.close()


def play_corrupt(b, r, st, tag):
    g = harness.Game(b, storage=st)
    r.check(not g.errors, f'{tag}：開いてエラーなし ' + str(g.errors[:3]))
    r.check(g.T('state') == 'title' and text(g, '#goBtn') is not None, f'{tag}：タイトルが出る')
    r.check(text(g, '#resBtn') is None, f'{tag}：壊れたセーブでは「つづきから」は出ない')
    click(g, '#goBtn', r, tag)
    if text(g, '#goBtn') is not None and g.T('state') == 'title':
        click(g, '#goBtn', r, tag)
    r.check(g.T('state') == 'play', f"{tag}：あそぶ {g.T('state')}")
    r.check(play_to(g, 3), f'{tag}：3面へ')
    res = get_caught(g)
    r.check(res['state'] == 'over' and text(g, '#bAgain') is not None, f'{tag}：見つかって結果画面 {res}')
    s = g.storage()
    for k in ('nekoLife', 'nekoCards'):
        try:
            v = json.loads(s.get(k) or 'null'); ok = isinstance(v, dict if k == 'nekoLife' else list)
        except Exception:
            ok = False
        r.check(ok, f'{tag}：{k} が正しい形で保存し直される {s.get(k, "")[:40]!r}')
    r.check(not g.errors, f'{tag}：最後までエラーなし ' + str(g.errors[:3]))
    g.close()


def run(b):
    r = harness.Report('saves')
    try:
        t_versions(b, r)
        t_corrupt(b, r)
    finally:
        shutil.rmtree(OLD_ROOT, ignore_errors=True)
    return r.done()
