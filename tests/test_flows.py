# 失敗・続きの流れのテスト：見つかった／時間切れ／お守りで復活／エンディングのあと／やめて再開／ポーズのやりなおす
# 28 面のボット（見つからないようにしてある）では通らない道を、本物のボタンを押して確かめる
import json
import harness

# ---------- ゲームを進める道具（test_saves からも使う。古い版でも同じ名前の関数がある） ----------

# 面のメインのものを全部「床に落ちて割れた」ことにして、本物の checkClear でクリアさせる
CLEAR_JS = '''(() => {
  if (state !== 'play') return 'not-play:' + state;
  introT = 0; sus = 0;
  for (const it of mains().slice()) { const i = items.indexOf(it); if (i >= 0) items.splice(i, 1); breakItem(it, PL.floor); }
  checkClear(); return state; })()'''

# 条件が満たされるまで update を回す（最大 lim フレーム）
def advance(g, cond, sec=60, dt=1 / 60):
    # update の中で例外が出たら（本物のループなら console.error になる）、g.errors に入れて止める
    lim = int(sec / dt)
    res = g.T(f'(() => {{ let n = 0; try {{ while (n < {lim} && !({cond})) {{ update({dt}); n++; }} }} catch (e) {{ return {{ state, level, n, ok: false, err: String(e && e.stack || e).split(String.fromCharCode(10)).slice(0, 3).join(String.fromCharCode(32, 47, 32)) }}; }} return {{ state, level, n, ok: !!({cond}) }}; }})()')
    if res.get('err'):
        g.errors.append('update: ' + res['err'])
    return res


# 今の面をクリアして、次の面の始まり（またはエンディングの締めの画面）まで進める
def clear_stage(g):
    L = g.T('level')
    st = g.T(CLEAR_JS)
    if st != 'clear':
        return {'state': st, 'level': L, 'ok': False}
    return advance(g, f"(state === 'play' && level === {L + 1}) || state === 'endmenu' || state === 'over'", sec=200)


# 面 L の始まりまで進める（途中で止まったら False）
def play_to(g, L):
    while g.T('level') < L:
        r = clear_stage(g)
        if not r.get('ok') or r['state'] != 'play':
            return False
    return g.T('state') == 'play' and g.T('level') == L


# 見つかる（timeup=True は時間切れ）。結果画面（over）か、お守りでの復活（play）まで進める
def get_caught(g, timeup=False):
    g.T(f'caught({"true" if timeup else ""})')
    return advance(g, "state === 'over' || state === 'play'", sec=10)


SNAP_JS = '''(() => { let sv = null; try { sv = loadSave(); } catch (e) {}
  const c = JSON.parse(localStorage.getItem('nekoCards') || '[]'), t = JSON.parse(localStorage.getItem('nekoTitles') || '[]');
  return { state, level, yen: run.yen, stars: run.stars, skill: run.skill, conts: run.conts || 0, album: (run.album || []).length,
    timeup: !!run.timeup, charm: run.charm || 0, ended: !!run.ended, caughtOver: !!run.caughtOver, ck: run.ck ? run.ck.level : null,
    cards: [...cardsGot], storedCards: c, storedTitles: t, titles: [...unlocked], newCards: newCards.map(n => (CARDS.find(c => c.name === n) || { id: String(n) }).id), lifeConts: LIFE.conts || 0,
    life: JSON.parse(JSON.stringify(LIFE)), sus, chaseT, chaseN, revives: run.revives || 0,
    save: sv ? { level: sv.level, cont: !!sv.cont, yen: sv.pk.run.yen, stars: sv.pk.run.stars, conts: sv.pk.run.conts || 0 } : null }; })()'''


def snap(g):
    return g.T(SNAP_JS)


def no_dup(a):
    return len(a) == len(set(a))


def text(g, sel):
    el = g.page.query_selector(sel)
    return el.inner_text() if el else None


def click(g, sel, r=None, what=''):
    # 本物のボタンを押す（見えない・ないときは失敗として記録し、先へ進む）
    try:
        g.page.click(sel, timeout=3000)
        return True
    except Exception as e:
        if r is not None:
            r.check(False, f'{what}：{sel} を押せない（{str(e).splitlines()[0]}） state={g.T("state")}')
        return False


def new_run(g):
    # 新しい回を始める（タイトルの「あそぶ」と同じ startGame）
    g.T('startGame()')
    return g.T('state') == 'play' and g.T('level') == 1


def errs(r, g, what):
    r.check(not g.errors, f'{what}: エラーなし ' + str(g.errors[:3]))


# ---------- それぞれの流れ ----------

def t_continue_day(b, r):
    # 2 日目の途中で見つかる → 「2日目の朝からつづける」で、朝の状態に戻る
    g = harness.Game(b)
    new_run(g)
    r.check(play_to(g, 5), '朝から：2日目の朝（5面）まで進める')
    morning = snap(g)
    r.check(morning['ck'] == 5, f"朝から：5面で朝の記録 run.ck={morning['ck']}")
    r.check(play_to(g, 6), '朝から：6面へ')
    pre = snap(g)
    r.check(pre['yen'] > morning['yen'], '朝から：昼のあいだに被害額が増えている')
    res = get_caught(g)
    r.check(res['state'] == 'over', f"朝から：見つかって結果画面 {res}")
    over = snap(g)
    r.check(over['save'] is not None and over['save']['level'] == 5 and over['save']['cont'],
            f"朝から：結果画面の時点でセーブは 5面・つづき扱い {over['save']}")
    r.check(over['save'] and over['save']['yen'] == morning['yen'], f"朝から：セーブの被害額は朝の値 {over['save']} / {morning['yen']}")
    bt = text(g, '#bCont')
    r.check(bt is not None and '2日目の朝からつづける' in bt, f'朝から：ボタン「2日目の朝からつづける」 {bt!r}')
    r.check(text(g, '#bRetry') is None, '朝から：2日目では「その面からやりなおす」は出ない')
    cards_before = set(over['cards'])
    click(g, '#bCont', r, 'click')
    g.wait(0.2)
    a = snap(g)
    r.check(a['state'] == 'play' and a['level'] == 5, f"朝から：5面から再開 {a['state']} {a['level']}")
    r.check(a['yen'] == morning['yen'], f"朝から：被害額が朝の値 {a['yen']} / {morning['yen']}")
    r.check(a['stars'] == morning['stars'], f"朝から：★が朝の値 {a['stars']} / {morning['stars']}")
    r.check(a['skill'] == morning['skill'], f"朝から：腕前が朝の値 {a['skill']} / {morning['skill']}")
    r.check(a['album'] == morning['album'], f"朝から：写真の枚数が朝の値 {a['album']} / {morning['album']}")
    r.check(a['conts'] == pre['conts'] + 1, f"朝から：続けた回数 +1 {pre['conts']} → {a['conts']}")
    r.check(a['lifeConts'] == pre['lifeConts'] + 1, f"朝から：通算の続けた回数 +1 {pre['lifeConts']} → {a['lifeConts']}")
    r.check(not a['caughtOver'] and not a['timeup'], '朝から：見つかった印が消えている')
    r.check(a['ck'] == 5, f"朝から：朝の記録は 5面のまま {a['ck']}")
    r.check(set(a['cards']) >= cards_before, '朝から：取ったカードは消えない')
    r.check(no_dup(a['storedCards']) and no_dup(a['storedTitles']), '朝から：カード・称号の保存に重なりなし')
    r.check(not a['newCards'], f"朝から：NEW カードは空から {a['newCards']}")
    r.check(a['save'] and a['save']['level'] == 5 and not a['save']['cont'] and a['save']['yen'] == morning['yen'],
            f"朝から：再開後のセーブ（5面・ふつう・朝の被害額） {a['save']}")
    # 同じ日をもう一度進めて、また見つかる → 2 回目のつづき
    r.check(play_to(g, 6), '朝から：もう一度 6面へ')
    pre2 = snap(g)
    r.check(pre2['yen'] >= morning['yen'], '朝から：被害額はまた増える')
    get_caught(g)
    r.check(text(g, '#bCont') is not None, '朝から：2回目も「朝からつづける」が出る')
    over2 = snap(g)
    r.check(not (set(over2['newCards']) & cards_before), f"朝から：前に取ったカードが NEW に出ない {set(over2['newCards']) & cards_before}")
    click(g, '#bCont', r, 'click')
    g.wait(0.2)
    a2 = snap(g)
    r.check(a2['conts'] == pre['conts'] + 2 and a2['level'] == 5 and a2['yen'] == morning['yen'],
            f"朝から：2回目のつづき（回数 +2、5面、朝の被害額） {a2['conts']} {a2['level']} {a2['yen']}")
    # 結果画面の時点で、通算の被害額が二重に数えられていないか（4.51.5 で直した：つづけた回は、前に数えた所から増えた分だけ足す）
    ly1, ly2 = over['life'].get('yen') or 0, over2['life'].get('yen') or 0
    r.check(ly2 <= ly1 + max(0, pre2['yen'] - pre['yen']) + 1, f'通算の被害額が二重に数えられていない {ly1} → {ly2}（その回 {pre["yen"]} → {pre2["yen"]}）')
    errs(r, g, '朝から')
    g.close()
    return {'life_yen_note': (over['life'].get('yen'), over2['life'].get('yen'), pre['yen'], pre2['yen'])}


def t_retry_day1(b, r):
    # 1 日目の 2 面目で見つかる → 「その面からやりなおす」で面の始まりに戻る
    g = harness.Game(b)
    new_run(g)
    r.check(play_to(g, 2), 'やりなおし：2面へ')
    start = snap(g)
    g.T(CLEAR_JS.replace("checkClear(); return state;", "return state;"))   # 割るだけ（クリアはしない）
    mid = snap(g)
    r.check(mid['yen'] > start['yen'], 'やりなおし：面の途中で被害額が増えた')
    res = get_caught(g)
    r.check(res['state'] == 'over', f'やりなおし：結果画面 {res}')
    bt = text(g, '#bRetry')
    r.check(bt is not None and 'やりなおす' in bt, f'やりなおし：ボタン「…の面からやりなおす」 {bt!r}')
    r.check(text(g, '#bCont') is None, 'やりなおし：1日目は「朝からつづける」が出ない')
    click(g, '#bRetry', r, 'click')
    g.wait(0.2)
    a = snap(g)
    r.check(a['state'] == 'play' and a['level'] == 2, f"やりなおし：2面から {a['state']} {a['level']}")
    r.check(a['yen'] == start['yen'] and a['stars'] == start['stars'] and a['skill'] == start['skill'],
            f"やりなおし：面の始まりの値 {a['yen']}/{start['yen']} ★{a['stars']}/{start['stars']}")
    r.check(a['conts'] == mid['conts'] + 1, f"やりなおし：続けた回数 +1 {mid['conts']} → {a['conts']}")
    r.check(a['lifeConts'] == mid['lifeConts'] + 1, 'やりなおし：通算の続けた回数 +1')
    r.check(a['save'] and a['save']['level'] == 2, f"やりなおし：セーブは 2面 {a['save']}")
    r.check(play_to(g, 3), 'やりなおし：そのまま 3面へ進める')
    errs(r, g, 'やりなおし')
    g.close()


def t_timeup(b, r):
    # 時間切れ（本物の制限時間が 0 になる）も、見つかったのと同じく朝から続けられる。お守りがあっても時間切れでは復活しない
    g = harness.Game(b)
    new_run(g)
    r.check(play_to(g, 5), '時間切れ：5面へ')
    morning = snap(g)
    r.check(play_to(g, 6), '時間切れ：6面へ')
    g.T('run.charm = 1; timeLeft = 0.05')
    res = advance(g, "state === 'over' || state === 'play' && run.revives > 0", sec=10)
    r.check(res['state'] == 'over', f'時間切れ：お守りがあっても結果画面へ {res}')
    s = snap(g)
    r.check(s['timeup'] and s['caughtOver'], f"時間切れ：run.timeup と見つかった印 {s['timeup']} {s['caughtOver']}")
    r.check(s['life'].get('timeups', 0) >= 1, '時間切れ：通算の時間切れに数える')
    r.check(text(g, '#bCont') is not None, '時間切れ：「朝からつづける」が出る')
    click(g, '#bCont', r, 'click')
    g.wait(0.2)
    a = snap(g)
    r.check(a['level'] == 5 and a['yen'] == morning['yen'], f"時間切れ：朝から {a['level']} {a['yen']}/{morning['yen']}")
    r.check(not a['timeup'], '時間切れ：つづけたら run.timeup は消える')
    r.check(a['conts'] == s['conts'] + 1, '時間切れ：続けた回数 +1')
    # 時間は面の始まりの値に戻っている（0 のままではない）
    r.check(g.T('timeLeft') > 10, f"時間切れ：制限時間が戻る {g.T('timeLeft')}")
    errs(r, g, '時間切れ')
    g.close()


def t_charm(b, r):
    # お守り：見つかっても演出のあとで遊びに戻る（怪しまれ度 25、追いかけっこはまた使える）
    g = harness.Game(b)
    new_run(g)
    r.check(play_to(g, 6), 'お守り：6面へ')
    g.T('run.charm = 1; chaseN = 2; sus = 90')
    before = snap(g)
    g.T('caught()')
    s0 = snap(g)
    r.check(s0['state'] == 'caught' and not s0['caughtOver'], 'お守り：見つかった演出（まだおしまいではない）')
    res = g.T('''(() => { let n = 0; while (n < 600 && state !== 'play' && state !== 'over') { update(1 / 60); n++; }
      return { state, level, sus, chaseT, chaseN, charm: run.charm, revives: run.revives || 0, timeup: run.timeup, caughtOver: !!run.caughtOver, mode: owner.mode, timeLeft }; })()''')
    r.check(res['state'] == 'play', f"お守り：遊びに戻る {res['state']}")
    r.check(res['level'] == 6, 'お守り：同じ面のまま')
    r.check(res['sus'] == 25, f"お守り：怪しまれ度 25 {res['sus']}")
    r.check(res['chaseT'] == 0 and res['chaseN'] == 0, f"お守り：追いかけっこが戻る chaseT={res['chaseT']} chaseN={res['chaseN']}")
    r.check(res['charm'] == 0 and res['revives'] == 1, f"お守り：お守りを使った {res['charm']} {res['revives']}")
    r.check(not res['caughtOver'] and res['mode'] == 'away', f"お守り：飼い主は部屋を出る {res['mode']}")
    r.check(res['timeLeft'] >= 10, 'お守り：制限時間は 10 秒以上')
    s = snap(g)
    r.check(s['save'] and s['save']['level'] == 6 and not s['save']['cont'], f"お守り：セーブは 6面のまま {s['save']}")
    r.check(s['yen'] == before['yen'], 'お守り：被害額はそのまま')
    g.step(1)
    r.check(play_to(g, 7), 'お守り：そのまま 7面へ進める')
    s2 = snap(g)
    r.check(s2['save'] and s2['save']['level'] == 7 and s2['yen'] >= before['yen'], f"お守り：セーブは 7面 {s2['save']}")
    # 2 回目はお守りがないので、結果画面
    res2 = get_caught(g)
    r.check(res2['state'] == 'over', f'お守り：使ったあとはふつうに結果画面 {res2}')
    r.check((g.T('LIFE.revive') or 0) >= 1, 'お守り：通算の復活に数える')
    errs(r, g, 'お守り')
    g.close()


def to_ending(g, r, tag):
    new_run(g)
    r.check(play_to(g, 12), f'{tag}：3日目の夜（12面）まで')
    y = g.T('run.yen')
    res = clear_stage(g)
    r.check(res['state'] == 'endmenu', f'{tag}：エンディングの締めの画面 {res}')
    return y


def t_ending(b, r):
    g = harness.Game(b)
    # (1) 「4日目へつづける」
    to_ending(g, r, 'エンディング1')
    y = g.T('run.yen')
    bt = text(g, '#enCont')
    r.check(bt is not None and '4日目へつづける' in bt, f'エンディング1：ボタン「4日目へつづける」 {bt!r}')
    r.check(g.T("localStorage.getItem('nekoEnded')") == '1', 'エンディング1：nekoEnded')
    r.check(g.T("catsOpen.has('siam')"), 'エンディング1：シャム猫の解禁')
    click(g, '#enCont', r, 'click')
    g.wait(0.2)
    a = snap(g)
    r.check(a['state'] == 'play' and a['level'] == 13, f"エンディング1：13面から {a['state']} {a['level']}")
    r.check(a['yen'] == y, f"エンディング1：被害額をそのまま {a['yen']}/{y}")
    r.check(a['ended'] and a['ck'] == 13, f"エンディング1：エンディング済み・朝の記録 13 {a['ended']} {a['ck']}")
    r.check(a['save'] and a['save']['level'] == 13 and a['save']['yen'] == y, f"エンディング1：セーブ 13面 {a['save']}")
    r.check(play_to(g, 14), 'エンディング1：14面へ進める')
    # 4 日目で見つかる → 4 日目の朝から
    get_caught(g)
    bt = text(g, '#bCont')
    r.check(bt is not None and '4日目の朝から' in bt, f'エンディング1：4日目の朝からつづける {bt!r}')
    r.check(text(g, '#bNext') is None, 'エンディング1：見つかったときは「…からつづける（次の日）」は出ない')
    click(g, '#bCont', r, 'click')
    g.wait(0.2)
    a = snap(g)
    r.check(a['level'] == 13 and a['yen'] == y, f"エンディング1：13面・朝の被害額 {a['level']} {a['yen']}/{y}")
    errs(r, g, 'エンディング1')

    # (2) 「ここでおわって結果をみる」→ 結果画面の「4日目からつづける」
    life0 = g.T('LIFE.endings || 0')
    to_ending(g, r, 'エンディング2')
    y = g.T('run.yen')
    click(g, '#enRes', r, 'click')
    g.wait(0.2)
    s = snap(g)
    r.check(s['state'] == 'over', f"エンディング2：結果画面 {s['state']}")
    r.check(s['save'] and s['save']['level'] == 13 and not s['save']['cont'], f"エンディング2：セーブは 4日目の始まり（つづきに数えない） {s['save']}")
    r.check(g.T('LIFE.endings || 0') == life0 + 1, 'エンディング2：通算のエンディング +1')
    rt = text(g, '.res-yen')
    r.check(rt is not None and '3日間の被害額' in rt, f'エンディング2：「3日間の被害額」 {rt!r}')
    bt = text(g, '#bNext')
    r.check(bt is not None and '4日目からつづける' in bt, f'エンディング2：ボタン「4日目からつづける」 {bt!r}')
    r.check(text(g, '#bCont') is None, 'エンディング2：「朝からつづける」は出ない')
    conts = s['conts']
    click(g, '#bNext', r, 'click')
    g.wait(0.2)
    a = snap(g)
    r.check(a['state'] == 'play' and a['level'] == 13, f"エンディング2：13面から {a['state']} {a['level']}")
    r.check(a['yen'] == y, f"エンディング2：被害額をそのまま {a['yen']}/{y}")
    r.check(a['conts'] == conts, 'エンディング2：続けた回数は増えない')
    r.check(a['save'] and a['save']['level'] == 13, f"エンディング2：セーブ 13面 {a['save']}")
    r.check(play_to(g, 14), 'エンディング2：14面へ進める')
    # 4 日目で見つかって終えた結果画面は「本日の被害額」（完走版ではない）
    get_caught(g)
    rt = text(g, '.res-yen')
    r.check(rt is not None and '本日の被害額' in rt, f'エンディング2：4日目で見つかった結果は「本日の被害額」 {rt!r}')
    errs(r, g, 'エンディング2')
    g.close()


def t_quit_resume(b, r, veteran):
    # 途中でやめて開き直す → タイトルの「つづきから」で同じ所から
    tag = '再開（2回目以降の人）' if veteran else '再開（はじめての人）'
    st = {'nekoLife': json.dumps({'plays': 1, 'yen': 1000}), 'nekoBestYen': '1000'} if veteran else {}
    g = harness.Game(b, storage=st)
    new_run(g)
    r.check(play_to(g, 6), f'{tag}：6面へ')
    s = snap(g)
    r.check(s['save'] and s['save']['level'] == 6, f"{tag}：6面でセーブ {s['save']}")
    g.open()
    bt = text(g, '#resBtn')
    r.check(bt is not None and 'つづきから' in bt, f'{tag}：タイトルに「つづきから」 {bt!r}')
    if bt is None:
        g.close()
        return
    click(g, '#resBtn', r, 'click')
    g.wait(0.2)
    a = snap(g)
    r.check(a['state'] == 'play' and a['level'] == 6, f"{tag}：6面から {a['state']} {a['level']}")
    r.check(a['yen'] == s['yen'] and a['stars'] == s['stars'] and a['skill'] == s['skill'],
            f"{tag}：被害額・★・腕前 {a['yen']}/{s['yen']} {a['stars']}/{s['stars']} {a['skill']}/{s['skill']}")
    r.check(a['album'] == s['album'], f"{tag}：写真の枚数 {a['album']}/{s['album']}")
    r.check(set(a['cards']) == set(s['cards']), f'{tag}：カード')
    r.check(a['conts'] == s['conts'], f'{tag}：ふつうのセーブは続けた回数に数えない')
    r.check(a['ck'] == 5, f"{tag}：朝の記録 5面 {a['ck']}")
    prev = a
    for L in (7, 8):
        r.check(play_to(g, L), f'{tag}：{L}面へ')
        c = snap(g)
        r.check(c['yen'] >= prev['yen'] and c['stars'] >= prev['stars'] and c['album'] == prev['album'] + 1 and set(c['cards']) >= set(prev['cards']),
                f"{tag}：{L}面で合計が減らない yen {prev['yen']}→{c['yen']} album {prev['album']}→{c['album']}")
        prev = c
    # 再開したあと見つかっても、朝（5面）から続けられる
    get_caught(g)
    r.check(text(g, '#bCont') is not None, f'{tag}：再開後に見つかっても朝からつづけられる')
    errs(r, g, tag)
    g.close()


def t_pause(b, r):
    g = harness.Game(b)
    new_run(g)
    # セーブがない（1面）ときは 1 回で始めから
    click(g, '#bPause', r, 'click')
    r.check(g.T('state') == 'pause', 'ポーズ：ポーズになる')
    click(g, '#pRetry', r, 'click')
    g.wait(0.1)
    r.check(g.T('state') == 'play' and g.T('level') == 1, 'ポーズ：セーブがなければ 1 回で始めから')
    r.check(play_to(g, 3), 'ポーズ：3面へ')
    y = g.T('run.yen')
    r.check(g.T('!!loadSave()'), 'ポーズ：セーブあり')
    # 2 回押しの判定は「前に押してから 2 秒」。ページを開いてすぐ（performance.now() < 2 秒）は別に調べる（t_title_quick）
    g.page.wait_for_function('() => performance.now() > 2500')
    click(g, '#bPause', r, 'click')
    r.check(g.T('state') == 'pause', 'ポーズ：ポーズになる（セーブあり）')
    r.check('セーブずみ' in (text(g, '#ov') or ''), 'ポーズ：「セーブずみ」の説明')
    click(g, '#pRetry', r, 'click')
    g.wait(0.1)
    r.check(g.T('state') == 'pause' and g.T('level') == 3 and g.T('run.yen') == y, 'ポーズ：1回目は何も消さない')
    r.check(g.T('!!loadSave()'), 'ポーズ：1回目ではセーブは残る')
    r.check('もう一度押すと' in (text(g, '#toast') or ''), f"ポーズ：知らせが出る {text(g, '#toast')!r}")
    click(g, '#pRetry', r, 'click')
    g.wait(0.1)
    r.check(g.T('state') == 'play' and g.T('level') == 1 and g.T('run.yen') == 0, 'ポーズ：2回目で 1日目から')
    r.check(not g.T('!!loadSave()'), 'ポーズ：2回目でセーブが消える')
    # つづける：3・2・1 のあとで遊びに戻る
    click(g, '#bPause', r, 'click')
    click(g, '#pResume', r, 'click')
    g.wait(3.5)
    r.check(g.T('state') in ('play', 'caught', 'clear'), f"ポーズ：つづけるで戻る {g.T('state')}")
    errs(r, g, 'ポーズ')
    g.close()


def t_title_quick(b, r):
    # 開いてすぐ（2 秒以内）にトップの「あそぶ」を押しても、つづきは 1 回では消えない（2 回押しが必要）はず
    g = harness.Game(b, storage={'nekoLife': json.dumps({'plays': 1}), 'nekoBestYen': '1000'})
    new_run(g)
    play_to(g, 3)
    g.open()
    t0 = g.T('performance.now()')
    r.check(text(g, '#resBtn') is not None, 'トップ：つづきから が出る')
    click(g, '#goBtn', r, 'トップ')
    r.check(g.T('state') == 'title' and g.T('!!loadSave()'),
            f"トップ：開いて {t0 / 1000:.1f} 秒で「あそぶ」を 1 回押しても、つづきは消えない（state={g.T('state')} save={g.T('!!loadSave()')}）")
    errs(r, g, 'トップ')
    g.close()


def run(b):
    r = harness.Report('flows')
    note = t_continue_day(b, r)
    t_retry_day1(b, r)
    t_timeup(b, r)
    t_charm(b, r)
    t_ending(b, r)
    t_quit_resume(b, r, veteran=True)
    t_quit_resume(b, r, veteran=False)
    t_pause(b, r)
    t_title_quick(b, r)
    print('  参考（通算の被害額 LIFE.yen：1回目の結果, 2回目の結果 / その回の被害額 1回目, 2回目）:', note['life_yen_note'])
    return r.done()
