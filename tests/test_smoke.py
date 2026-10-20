import harness
def run(b):
    r = harness.Report('smoke')
    g = harness.Game(b)
    r.check(g.T('APP_VER') is not None, 'APP_VER')
    g.T("(()=>{ newRun(); setupStage(1); state='play'; ov.hidden=true; introT=0; })()")
    r.check(g.step(1) == 'play', 'play 1 sec')
    r.check(not g.errors, 'errors: ' + str(g.errors[:3]))
    g.close(); return r.done()
