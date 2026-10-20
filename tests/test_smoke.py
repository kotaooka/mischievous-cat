import harness
def run(b):
    r = harness.Report('smoke')
    g = harness.Game(b)
    r.check(g.T('APP_VER') is not None, 'APP_VER')
    g.T("(()=>{ newRun(); setupStage(1); state='play'; ov.hidden=true; introT=0; })()")
    r.check(g.step(1) == 'play', 'play 1 sec')
    # ネコとおしゃれ：選んで「けってい」でトップに戻る（ここからは始まらない）。選んだネコは残る
    g.T("(()=>{ catsOpen.add('cha'); showCatShop(); })()"); g.wait(0.2)
    g.page.click('.cats button[data-i="1"]'); g.wait(0.2)
    r.check(g.T("!!document.getElementById('goBtn') && !!ov.querySelector('.cats')") is False, 'おしゃれ画面に「あそぶ」がない')
    g.page.click('#csBack'); g.wait(0.3)
    r.check(g.T("state === 'title' && !!document.getElementById('goBtn') && !ov.querySelector('.cats')"), '「けってい」でトップに戻る')
    r.check(g.T("selCat") == 1 and g.storage().get('nekoCat') == '1', '選んだネコが残る')
    r.check(not g.errors, 'errors: ' + str(g.errors[:3]))
    g.close(); return r.done()
