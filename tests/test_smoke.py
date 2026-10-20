import harness
def run(b):
    r = harness.Report('smoke')
    g = harness.Game(b)
    r.check(g.T('APP_VER') is not None, 'APP_VER')
    g.T("(()=>{ newRun(); setupStage(1); state='play'; ov.hidden=true; introT=0; })()")
    r.check(g.step(1) == 'play', 'play 1 sec')
    # ジャンプの高さ（4.52.0）：すぐ離すと低く（それでも段差 75px より高く）、押し続けると最大。どのネコでも
    for ci in range(6):
        h = g.T(f"""(()=>{{ const o=[]; for (const hold of [0, 1]) {{ selCat={ci}; newRun(); setupStage(2); state='play'; ov.hidden=true; introT=0; owner.mode='away'; owner.t=99; rival=null; Object.assign(cat,{{plat:PL.floor,y:FLOOR,x:40,vx:0,vy:0}});
          jumpPress(); let t=0, m=FLOOR; while(t<1.5){{ if (t>=hold && jumpHeld) jumpRelease(); update(1/60); t+=1/60; m=Math.min(m,cat.y); if (cat.plat===PL.floor && t>0.2) break; }} o.push(FLOOR-m); }} jumpRelease(); return o; }})()""")
        r.check(78 <= h[0] <= h[1] and (h[1] - h[0] >= 8 or h[1] < 100), f'ジャンプ CATS[{ci}]：すぐ離す {h[0]:.0f}px・押し続ける {h[1]:.0f}px')
    # ネコとおしゃれ：選んで「けってい」でトップに戻る（ここからは始まらない）。選んだネコは残る
    g.T("(()=>{ catsOpen.add('cha'); showCatShop(); })()"); g.wait(0.2)
    g.page.click('.cats button[data-i="1"]'); g.wait(0.2)
    r.check(g.T("!!document.getElementById('goBtn') && !!ov.querySelector('.cats')") is False, 'おしゃれ画面に「あそぶ」がない')
    g.page.click('#csBack'); g.wait(0.3)
    r.check(g.T("state === 'title' && !!document.getElementById('goBtn') && !ov.querySelector('.cats')"), '「けってい」でトップに戻る')
    r.check(g.T("selCat") == 1 and g.storage().get('nekoCat') == '1', '選んだネコが残る')
    r.check(not g.errors, 'errors: ' + str(g.errors[:3]))
    g.close(); return r.done()
