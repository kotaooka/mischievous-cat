# 集めるもの（いたずらカード・被害額の称号・エンディング・きせかえ・ネコ）が、ゲームの本当の流れで全部手に入るかを確かめる
# 大事なのは「条件が成り立つ瞬間」のあとに、ゲームを自然に進めたときに cardsGot と localStorage（nekoCards など）に入ること。
# 例：4.51.4 より前は、面クリアの瞬間や見つかった瞬間に成り立つカードが、遊んでいる間しか調べていなかったので取れなかった。
#
# まとまり（文脈 = localStorage がまっさらなブラウザ 1 つ）
#   A 遊んでいる間に成り立つカード：条件をつくり（できるものはゲームの関数で）、その面を 1 秒ほど遊ばせる
#   B 1 日目の朝から 7 日目の夜まで通しで遊ぶ（面クリアは置いてあるものを本当に割って checkClear させる）
#     → 面クリアで成り立つカード、エンディング 5 種類、ネコ、ごほうびのきせかえ
#   C 見つかる・時間切れで成り立つカード、被害額の称号、通算（LIFE）のカード、隠しコマンド・シェアのきせかえ
import json
import harness

# ゲームの中で使う手伝いの関数（__T の中で作るので、ゲームの変数に触れる）
HELPERS = r"""
window.__H = {
  // 飼い主を外に出し、怪しまれ度と時間をもどす（テストの途中で見つからないように）
  calm() { setMode('away', 99); owner.x = -60; owner.lureT = 0; sus = 0; susQ = 0; chaseT = 0; chaseN = 0; timeLeft = Math.max(timeLeft, 60); if (run) run.charm = 0; charm = null; },
  // 今の run のまま L 面を遊ぶ状態にする
  toPlay(L) { if (L) setupStage(L); ov.hidden = true; state = 'play'; introT = 0; __H.calm(); },
  // あそぶ を押したのと同じ（新しい run）。L があればその面へ
  start(L) { startGame(); __H.toPlay(L > 1 ? L : 0); },
  // クリアに必要なものを全部、床に落として割る（本物の breakItem を通す）
  smash() { for (const it of mains().slice()) { const i = items.indexOf(it); if (i >= 0) items.splice(i, 1); breakItem(it, PL.floor); } __H.calm(); },
  smashOne() { const it = mains()[0]; if (!it) return false; items.splice(items.indexOf(it), 1); breakItem(it, PL.floor); __H.calm(); return true; },
  // 見つかる：updSus が怪しまれ度 100%（追いかけっこを使い切ったあと）で呼ぶのと同じ caught() を呼ぶ。お守りはなし（復活しない）
  getCaught() { run.charm = 0; charm = null; sus = 100; caught(); },
  got(id) { let ls = []; try { ls = JSON.parse(localStorage.getItem('nekoCards') || '[]'); } catch (e) {} return cardsGot.has(id) && ls.includes(id); },
};
true
"""


def setup(g):
    g.T(HELPERS)


def got(g, cid):
    return g.T(f'__H.got({json.dumps(cid)})')


def until(g, cond, maxsec, chunk=0.25):
    # cond（JS の式）が真になるまで update を回す。真になれば True
    t = 0
    while t < maxsec:
        if g.T(cond):
            return True
        g.step(chunk)
        t += chunk
    return bool(g.T(cond))


def clear_stage(g, r, what):
    # 置いてあるものを全部割って、checkClear から 'clear' になるのを待つ
    g.T('__H.calm(); __H.smash()')
    ok = until(g, "state !== 'play'", 2, chunk=1 / 60)
    st = g.T('state')
    r.check(ok and st == 'clear', f'{what}: 面クリアにならない（state={st}, 残り={g.T("mains().length")}）')
    return st == 'clear'


def next_play(g, r, what, maxsec=12):
    # クリア札・その日のおしまいを本当に進めて、次の面が始まるまで
    ok = until(g, "state === 'play' || state === 'ending'", maxsec)
    r.check(ok, f'{what}: 次の面に進まない（state={g.T("state")}）')
    if g.T("state === 'play'"):
        g.T('__H.calm()')
    return ok


def to_endmenu(g, r, what):
    # エンディング → スタッフロール →（ほんとうのおしまいは後日談）→ 締めの画面
    ok = until(g, "state === 'endmenu'", 160, chunk=2)
    r.check(ok, f'{what}: 締めの画面にならない（state={g.T("state")}）')
    return ok


def to_over(g, r, what):
    ok = until(g, "state === 'over'", 8)
    r.check(ok, f'{what}: 結果画面にならない（state={g.T("state")}）')
    if ok:
        g.page.wait_for_selector('#bShare', timeout=5000)
    return ok


# ---------- A：遊んでいる間に成り立つカード ----------
# (カードid, その面（None は今の面のまま）, 条件をつくる JS)
# ゲームの関数で起こせるもの（foeDown・bigTrigger・taskHit・spaceCat・damage・breakItem）はそれを使い、
# 物理の操作が要るもの（ボールを転がす・ランプにぶら下がる 等）は、ゲームがその瞬間に書く run の値を直接入れる
PLAY = [
    ('first', 1, '__H.smashOne()'),
    # この 2 つは家具崩し（bigTrigger）で本棚のものがまとめて落ちても自然に成り立つので、先に確かめる
    ('t_streak', None, 'run.maxStreak = 5'),
    ('t_space', None, 'cat.danceT = 0; spaceCat()'),
    ('foe_vacbot', 13, 'foe && foeDown(W / 2, 200)'),
    ('foe_crow', 18, 'foe && foeDown(W / 2, 200)'),
    ('foe_toybot', 23, 'foe && foeDown(W / 2, 200)'),
    ('foe_drone', 25, 'foe && foeDown(W / 2, 200)'),
    ('t_foe4', None, ''),                                  # 1 回で 4 種類（上の 4 つで成り立つ）
    ('dognight', 20, 'run.ev.bone = (run.ev.bone || 0) + 1'),   # punchBones（2642 行）が書く値
    ('bossnight', 24, 'run.ev.combo = (run.ev.combo || 0) + 1'),  # ボスとの連携（2717 行）
    ('chain3', 1, 'run.maxChain = 3'),
    ('phone', None, 'run.broke.phone = 1'),
    ('water', None, 'run.water++'),
    ('tissue', None, 'run.broke.tissue = 1'),
    ('cloth', None, 'run.cloth++'),
    ('lamp', None, 'run.lamp++'),
    ('bath', 7, 'run.bathFall++'),
    ('sink', None, "taskHit('sink')"),
    ('cuke', None, 'run.cuke++'),
    ('ride', 1, 'run.rideT = 3'),
    ('snack', 2, "taskHit('snack')"),
    ('data', 3, "damage(5000, 'data', 100, 300)"),
    ('alarm', None, 'run.broke.alarm = 1'),
    ('bounce', 8, "taskHit('bounce'); taskHit('bounce'); taskHit('bounce')"),
    ('chick', 5, 'run.chick++'),
    ('fish', 6, 'run.fish++'),
    ('boss', None, 'run.boss++'),
    ('mouse', None, 'run.mice++'),
    ('scare', None, 'run.scare++'),
    ('hide', None, "taskHit('hide')"),
    ('lure', None, "taskHit('lure')"),
    ('kaku', None, 'run.kakushin++'),
    ('scratch', None, "run.mis++"),
    ('rub', None, 'run.rubT = 2'),
    ('escape', None, 'run.escapes++'),
    ('top', None, 'run.top = true'),
    ('tv', None, 'run.tv++'),
    ('churu', None, 'run.churu++'),
    ('dog', None, 'run.barks++'),
    ('big_living', 1, 'bigTrigger()'),
    ('big_kitchen', 2, 'bigTrigger()'),
    ('big_study', 3, 'bigTrigger()'),
    ('big_garden', 5, 'bigTrigger()'),
    ('big_kids', 6, 'bigTrigger()'),
    ('big_bath', 7, 'bigTrigger()'),
    ('big_bed', 8, 'bigTrigger()'),
    ('t_print', None, 'run.prints = 40'),
    ('t_book', None, 'run.bookBroke = 3'),
    ('t_food', None, 'run.fed = 3'),
    ('t_stars', None, 'run.stars = 9'),
    ('t_bowl', None, 'run.ballHits = 3'),
    ('t_big5', None, 'run.bigN = 5'),
]


def part_play(b, r, covered):
    g = harness.Game(b); setup(g)
    g.T('__H.start(1)')
    for cid, L, js in PLAY:
        covered.add(cid)
        if L:
            g.T(f'__H.toPlay({L})')
        if g.T("state") != 'play':
            g.T('__H.toPlay(level)')
        if js:
            r.check(not got(g, cid), f'A {cid}: 条件をつくる前から取れている')
        if cid == 'foe_drone':
            r.check(not got(g, 't_foe4'), 'A t_foe4: 相手 3 種類で取れている')
        if js:
            g.T(f'(() => {{ {js}; }})()')
        g.T('__H.calm()')
        g.step(0.7)
        r.check(got(g, cid), f'A {cid}: 遊んでいる間に取れない（state={g.T("state")}）')
    # 家具崩しでメインクーンが出る（bigTrigger → openCat('maine')）
    r.check(g.T("catsOpen.has('maine')") and 'maine' in json.loads(g.storage().get('nekoCats', '[]')), 'A ネコ maine: 家具崩しで出ない')
    # カードのきせかえ
    for a in ['bell', 'ribbon', 'scarf', 'glasses']:
        r.check(g.T(f"accOk(ACCS.find(a => a.id === '{a}'))"), f'A きせかえ {a}: カードを取っても使えない')
    r.check(not g.errors, 'A errors: ' + str(g.errors[:3]))
    g.close()


# ---------- B：通しで遊ぶ（面クリア・エンディング・ネコ） ----------
def ending_seen(g, et):
    ls = json.loads(g.storage().get('nekoEndings', '[]'))
    return g.T(f"endingsSeen.has('{et}')") and et in ls


def part_full(b, r, covered):
    g = harness.Game(b); setup(g)
    g.T('__H.start(1)')
    for cid in ['t_ghost', 't_fast', 't_perfect', 't_guest', 't_day', 'festival', 'lastnight', 't_nohit', 't_endings', 't_family']:
        covered.add(cid)
    # 1 日目の朝から 3 日目の夜まで、毎面ほんとうにクリアする（怪しまれ度 0 のまま → 完全犯罪のエンディングになるはず）
    # 面クリアで立つ値（ghost・perfect・guestClear・fast・days）は、クリア札 →（その日のおしまい）→ 次の面を遊ぶ、まで進めてから確かめる
    after = {1: ['t_ghost'], 2: ['t_fast'], 3: ['t_perfect'], 4: ['t_guest', 't_day']}
    for L in range(1, 13):
        if g.T('level') != L:
            r.check(False, f'B: {L} 面のはずが level={g.T("level")}'); break
        for cid in after.get(L, []):
            r.check(not got(g, cid), f'B {cid}: {L} 面をクリアする前から取れている')
        if not clear_stage(g, r, f'B {L} 面'):
            break
        if L == 1:
            r.check(g.T("catsOpen.has('kuro')") and 'kuro' in json.loads(g.storage().get('nekoCats', '[]')), 'B ネコ kuro: 怪しまれ度 20% 未満でクリアしても出ない')
        if L == 12:
            break
        next_play(g, r, f'B {L} 面のあと')
        g.step(0.7)
        for cid in after.get(L, []):
            r.check(got(g, cid), f'B {cid}: {L} 面をクリアして次の面を遊んでも取れない')
    # 3 日目の夜を越えた → エンディング
    r.check(until(g, "state === 'ending'", 6), f'B: 12 面のあとエンディングにならない（state={g.T("state")}）')
    r.check(g.T('run.endType') == 'perfect', f'B: 通しで怪しまれ度 0 → 完全犯罪のはずが {g.T("run.endType")}')
    if to_endmenu(g, r, 'B 1 回目のエンディング'):
        r.check(ending_seen(g, 'perfect'), 'B エンディング perfect: nekoEndings に入らない')
        r.check(g.T("accOk(ACCS.find(a => a.id === 'medal'))"), 'B きせかえ medal: エンディングを見ても使えない')
        r.check(g.T("catsOpen.has('siam')") and 'siam' in json.loads(g.storage().get('nekoCats', '[]')), 'B ネコ siam: エンディングで出ない')
        # 4 日目へつづける（本物のボタン）
        g.page.click('#enCont')
        g.T('__H.calm()')
    # 4 日目〜7 日目もクリアしていく（お祭りの夜 = 16 面、最後の夜 = 28 面）
    for L in range(13, 29):
        if g.T('level') != L or g.T('state') != 'play':
            r.check(False, f'B: {L} 面のはずが level={g.T("level")} state={g.T("state")}'); break
        if L == 16:
            r.check(not got(g, 'festival'), 'B festival: お祭りの夜より前に取れている')
        if L == 28:
            r.check(not got(g, 'lastnight'), 'B lastnight: 最後の夜より前に取れている')
        if not clear_stage(g, r, f'B {L} 面'):
            break
        if L == 28:
            break   # 最後の夜のあとは遊ぶ面がない → ほんとうのおしまいへ
        next_play(g, r, f'B {L} 面のあと')
        if L == 16:
            g.step(0.7)
            r.check(got(g, 'festival'), 'B festival: お祭りの夜を越えて 5 日目を遊んでも取れない')
    r.check(until(g, "state === 'ending'", 6), f'B: 28 面のあと、ほんとうのおしまいにならない（state={g.T("state")}）')
    r.check(g.T('run.endType') == 'true', f'B: 28 面のあとは true のはずが {g.T("run.endType")}')
    if to_endmenu(g, r, 'B ほんとうのおしまい'):
        r.check(ending_seen(g, 'true'), 'B エンディング true: nekoEndings に入らない')
        r.check(got(g, 'lastnight'), 'B lastnight: 最後の夜を越えて締めの画面まで進んでも取れない')
        r.check(got(g, 't_nohit'), 'B t_nohit: 相手に当たらず 7 日目の夜を越えても取れない')
        r.check(g.T("accOk(ACCS.find(a => a.id === 'star'))"), 'B きせかえ star: 7 日目の夜を越えても使えない')
        # 三毛猫：7 日間ぜんぶ割ると 1 回で ¥100 万をこえる（breakItem / checkClear の openCat('mike')）
        r.check(g.T('run.yen') >= 1000000, f'B: 7 日間の被害額が ¥{g.T("run.yen"):,}（¥100 万に届かない）')
        r.check(g.T("catsOpen.has('mike')") and 'mike' in json.loads(g.storage().get('nekoCats', '[]')), 'B ネコ mike: 1 回で ¥100 万をこえても出ない')
        g.page.click('#enRes')   # 結果をみる → gameOver
        to_over(g, r, 'B ほんとうのおしまいの結果')

    # のこりのエンディング：3 日目の夜（12 面）だけをクリアする run を、遊び方を変えて
    def end_run(et, prep, what):
        g.T('__H.start(1)')
        g.T(f'(() => {{ {prep}; }})()')
        g.T('__H.toPlay(12)')
        if clear_stage(g, r, f'B {what} 12 面'):
            r.check(until(g, "state === 'ending'", 6), f'B {what}: エンディングにならない')
            r.check(g.T('run.endType') == et, f'B {what}: {et} のはずが {g.T("run.endType")}')
            if to_endmenu(g, r, f'B {what}'):
                r.check(ending_seen(g, et), f'B エンディング {et}: nekoEndings に入らない')
                if et != 'wrecker':
                    g.page.click('#enRes'); to_over(g, r, f'B {what} の結果')

    # いい子（自称）：追いかけっこなし・続きなし（クリアは 1 面だけなので完全犯罪にはならない）
    end_run('good', '', 'いい子')
    # いつもの夜：追いかけっこを 1 回（本物の startChase。逃げ切ったことにして終わらせる）
    end_run('normal', 'startChase(); chaseT = 0; __H.calm()', 'いつもの夜')
    # 解体の日々：リビング・キッチン・書斎で家具を崩す（本物の bigTrigger → メインクーンも出る）
    r.check(not got(g, 't_endings') and not got(g, 't_family'), 'B: 全エンディング・ネコ一家が早すぎる')
    end_run('wrecker', "bigTrigger(); __H.toPlay(2); bigTrigger(); __H.toPlay(3); bigTrigger()", '解体の日々')
    r.check(got(g, 't_endings'), f'B t_endings: 5 種類見ても取れない（{g.T("[...endingsSeen].join()")}）')
    r.check(got(g, 't_family'), f'B t_family: 6 匹そろっても取れない（{g.T("[...catsOpen].join()")}）')
    r.check(g.T("accOk(ACCS.find(a => a.id === 'hat'))"), 'B きせかえ hat: お祭りの夜のカードで使えない')
    r.check(not g.errors, 'B errors: ' + str(g.errors[:3]))
    g.close()


# ---------- C：見つかる・時間切れ・称号・通算・隠しコマンド・シェア ----------
def part_over(b, r, covered):
    g = harness.Game(b); setup(g)
    # 隠しコマンド：タイトルで にゃー（X キー）を 10 回
    g.page.wait_for_selector('.first-cat', timeout=5000)
    r.check(not g.T("accOk(ACCS.find(a => a.id === 'shades'))"), 'C shades: 最初から使える')
    for _ in range(10):
        g.page.keyboard.press('x'); g.wait(0.05)
    r.check(g.T("accOk(ACCS.find(a => a.id === 'shades'))"), 'C きせかえ shades: タイトルで にゃー 10 回で使えない')

    plays = 0

    def finish(what, prep=''):
        # 遊んで見つかって結果画面まで
        nonlocal plays
        if prep:
            g.T(f'(() => {{ {prep}; }})()')
        g.T('__H.getCaught()')
        ok = to_over(g, r, what)
        plays += 1
        return ok

    # 何もしていないときに見つかる
    covered.add('t_idle')
    g.T('__H.start(1)'); g.step(0.3); g.T('__H.calm()')
    finish('C idle')
    r.check(g.T('run.idle') is True, 'C idle: 止まっていたのに run.idle にならない')
    r.check(got(g, 't_idle'), 'C t_idle: 何もしていないときに見つかっても取れない')
    r.check(g.T("unlocked.has('t1')") and 't1' in json.loads(g.storage().get('nekoTitles', '[]')), 'C 称号 t1: 1 回遊んでも入らない')
    # シェアのきせかえ：結果画面の「シェア」を押す
    g.page.click('#bShare'); g.wait(0.2)
    r.check(g.T("accOk(ACCS.find(a => a.id === 'camera'))"), 'C きせかえ camera: シェアを押しても使えない')

    # 被害額 ¥0 のまま時間切れ（本当に時間を 0 にする）
    covered.add('t_zero')
    g.T('__H.start(1)'); g.T('timeLeft = 0.05')
    ok = until(g, "state !== 'play'", 1, chunk=1 / 60)
    r.check(ok and g.T('state') == 'caught' and g.T('run.timeup') is True, f'C zero: 時間切れにならない（state={g.T("state")}）')
    to_over(g, r, 'C zero'); plays += 1
    r.check(got(g, 't_zero'), 'C t_zero: ¥0 のまま時間切れでも取れない')

    # 被害額の称号：ちょうどその額で終える。ひとつ上は入らないこと
    tiers = g.T("TITLES.filter(t => t.tier).map(t => [t.id, t.tier])")
    for i, (tid, tier) in enumerate(tiers):
        g.T('__H.start(1)')
        finish(f'C 称号 {tid}', f'run.yen = {tier}')
        st = json.loads(g.storage().get('nekoTitles', '[]'))
        r.check(g.T(f"unlocked.has('{tid}')") and tid in st, f'C 称号 {tid}: ¥{tier:,} で終えても入らない')
        if i + 1 < len(tiers):
            nx = tiers[i + 1][0]
            r.check(nx not in st, f'C 称号 {nx}: ¥{tier:,} なのに入っている')

    # 通算：¥100 万（上の称号の run で通算をこえている）
    covered.add('t_million')
    r.check(got(g, 't_million'), f'C t_million: 通算 ¥{g.T("LIFE.yen"):,} でも取れない')

    # 通算：コップ 30 個・夜の被害額 ¥100,000・ダンボール 10 回（taskHit('hide') を 10 回）
    covered.update(['t_cups', 't_night', 't_boxer'])
    g.T('__H.start(1)')
    g.T("for (let k = 0; k < 10; k++) taskHit('hide')")
    r.check(g.T('run.ev.hide') == 10, 'C boxer: taskHit で ev.hide が数えられない')
    finish('C 通算', 'run.broke.cup = 30; run.todYen[3] = 100000')
    for cid in ['t_cups', 't_night', 't_boxer']:
        r.check(got(g, cid), f'C {cid}: 通算の条件をこえても取れない')

    # 家じゅう制覇：1 回の run で 1〜28 面の部屋を順にまわる（setupStage が run.rooms に足す）
    covered.add('t_rooms')
    g.T('__H.start(1)')
    g.T('for (let L = 1; L <= 28; L++) setupStage(L); __H.toPlay(0)')
    n = g.T('run.rooms.length'); total = g.T('Object.keys(ROOM_NAME).length')
    r.check(n == total, f'C rooms: 28 面まわって部屋が {n}/{total}')
    finish('C rooms')
    r.check(got(g, 't_rooms'), 'C t_rooms: 全部の部屋をまわっても取れない')

    # 全室解体：家具崩しのある 7 部屋で本物の bigTrigger
    covered.add('t_wrecker7')
    g.T('__H.start(1)')
    for L in [1, 2, 3, 5, 6, 7, 8]:
        g.T(f'__H.toPlay({L}); bigTrigger()')
    r.check(g.T('run.bigs.length') == g.T('Object.keys(BIG).length'), f'C wrecker7: 崩した部屋 {g.T("run.bigs.join()")}')
    finish('C wrecker7')
    r.check(got(g, 't_wrecker7'), 'C t_wrecker7: 7 部屋を崩しても取れない')
    r.check(g.T("accOk(ACCS.find(a => a.id === 'crown'))"), 'C きせかえ crown: 全室解体で使えない')

    # 三日坊主卒業：日付（Date.now）を 1 日ずつ進めて 3 回遊ぶ
    covered.add('t_days3')
    base = g.T('Date.now()') + 30 * 86400e3
    g.T('window.__realNow = Date.now')
    for k in range(3):
        r.check(not got(g, 't_days3'), f'C days3: {k} 日目で取れている')
        g.T(f'Date.now = () => {base + k * 86400e3}')
        g.T('__H.start(1)'); finish(f'C days3 {k + 1} 日目')
    g.T('Date.now = window.__realNow')
    r.check(got(g, 't_days3'), f'C t_days3: 3 日続けて遊んでも取れない（dayStreak={g.T("LIFE.dayStreak")}）')

    # 常連ネコ：10 回遊ぶ
    covered.add('t_regular')
    while plays < 10:
        r.check(not got(g, 't_regular'), f'C regular: {plays} 回で取れている')
        g.T('__H.start(1)'); finish(f'C regular {plays + 1}')
    r.check(got(g, 't_regular'), f'C t_regular: {g.T("LIFE.plays")} 回遊んでも取れない')
    r.check(not g.errors, 'C errors: ' + str(g.errors[:3]))
    g.close()


def run(b):
    r = harness.Report('collect')
    covered = set()
    part_play(b, r, covered)
    part_full(b, r, covered)
    part_over(b, r, covered)
    # 抜けがないか：CARDS の全部をどこかで確かめたか
    g = harness.Game(b)
    ids = g.T('CARDS.map(c => c.id)')
    r.check(len(ids) == 72, f'CARDS は 72 枚のはずが {len(ids)}')
    miss = [c for c in ids if c not in covered]
    r.check(not miss, f'確かめていないカード: {miss}')
    g.close()
    return r.done()
