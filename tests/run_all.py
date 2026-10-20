# すべてのテストを実行する：python tests/run_all.py [名前の一部 ...]
import sys, os, importlib, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from playwright.sync_api import sync_playwright

SUITES = ['test_smoke', 'test_collect', 'test_flows', 'test_saves', 'test_ranking', 'test_daily', 'test_english', 'test_touch']

def main():
    only = sys.argv[1:]
    harness.build(); harness.serve()
    ok = True
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name in SUITES:
            if only and not any(o in name for o in only):
                continue
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + '.py')
            if not os.path.exists(path):
                print(f'[{name}] （まだない）'); continue
            t0 = time.time()
            mod = importlib.import_module(name)
            r = mod.run(b)
            print(f'  （{time.time() - t0:.0f} 秒）')
            ok = r and ok
        b.close()
    print('ALL OK' if ok else 'FAILED')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
