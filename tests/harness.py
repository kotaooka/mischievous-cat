# テストの共通処理：テスト用のコピーを作って（window.__T でゲームの中の変数に触れるようにする）、手もとのサーバーで開く
# 使い方：python tests/run_all.py（Playwright for Python が必要：pip install playwright → python -m playwright install chromium）
import os, shutil, threading, functools, http.server, socketserver, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.environ.get('NEKO_SITE') or os.path.join(ROOT, 'tests', '.site')   # 並べて実行するときは NEKO_SITE で別の場所に
_server = None


def build():
    # 本物のファイルは書きかえない。tests/.site にコピーして、index.html の最後に __T を足す
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)
    for name in os.listdir(ROOT):
        if name in ('.git', 'tests', 'docs'):
            continue
        src = os.path.join(ROOT, name)
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, os.path.join(SITE, name))
    p = os.path.join(SITE, 'index.html')
    s = open(p, encoding='utf-8').read()
    i = s.rfind('})();')
    open(p, 'w', encoding='utf-8').write(s[:i] + 'window.__T = s => eval(s);\n' + s[i:])
    # サービスワーカーは使わない（古い版がキャッシュから出ないように）
    open(os.path.join(SITE, 'sw.js'), 'w', encoding='utf-8').write('// テストでは使わない\n')


def serve():
    global _server
    if _server:
        return _server.server_address[1]
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = functools.partial(Quiet, directory=SITE)
    socketserver.TCPServer.allow_reuse_address = True
    _server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return _server.server_address[1]


class Game:
    """1つのブラウザの文脈（localStorage は毎回まっさら）でゲームを開く"""

    def __init__(self, browser, lang='ja', storage=None, mobile=True, tut_done=True):
        self.ctx = browser.new_context(viewport={'width': 390, 'height': 720}, device_scale_factor=1,
                                       locale='ja-JP' if lang == 'ja' else 'en-US', has_touch=mobile, is_mobile=mobile)
        # 外への通信（Firestore など）は全部止める。送る中身はテストの中で受け取る
        self.sent = []

        def route(r):
            u = r.request.url
            if u.startswith('http://127.0.0.1'):
                return r.continue_()
            self.sent.append({'url': u, 'method': r.request.method, 'body': r.request.post_data})
            if 'firestore.googleapis.com' in u and r.request.method == 'POST' and ':runQuery' not in u:
                return r.fulfill(status=200, content_type='application/json', body='{}')
            if ':runQuery' in u:
                return r.fulfill(status=200, content_type='application/json', body='[]')
            return r.abort()
        self.ctx.route('**/*', route)
        init = {'nekoLang': lang}
        if tut_done:
            init['nekoTut'] = '1'
        init.update(storage or {})
        self.ctx.add_init_script('(() => { if (sessionStorage.getItem("__init")) return; sessionStorage.setItem("__init", "1"); '
                                 + ''.join(f'localStorage.setItem({json.dumps(k)}, {json.dumps(v)});' for k, v in init.items()) + '})();')
        self.page = self.ctx.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('console', lambda m: self.errors.append('console: ' + m.text) if m.type == 'error' else None)
        self.open()

    def open(self):
        self.page.goto(f'http://127.0.0.1:{serve()}/index.html')
        self.page.wait_for_function('() => !!window.__T')
        self.page.wait_for_timeout(300)

    def T(self, js):
        return self.page.evaluate('s => __T(s)', js)

    def wait(self, sec):
        self.page.wait_for_timeout(int(sec * 1000))

    def step(self, sec, dt=1 / 60):
        # 時間を進める（requestAnimationFrame を待たずに update を回す）
        return self.T(f'(() => {{ let t = 0; while (t < {sec}) {{ update({dt}); t += {dt}; }} return state; }})()')

    def storage(self):
        return self.page.evaluate('() => Object.assign({}, localStorage)')

    def close(self):
        self.ctx.close()


class Report:
    def __init__(self, name):
        self.name, self.fails, self.n = name, [], 0

    def check(self, ok, what):
        self.n += 1
        if not ok:
            self.fails.append(what)
        return ok

    def done(self):
        print(f'[{self.name}] {self.n - len(self.fails)}/{self.n} ok')
        for f in self.fails:
            print('  NG ' + f)
        return not self.fails
