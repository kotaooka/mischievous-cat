# 画面の字体（M PLUS Rounded 1c）を、このゲームで使う文字だけに絞って fonts/ に書き出す
# 使い方（index.html の文章を変えて、新しい漢字が増えたときに実行する）：
#   1. pip install fonttools brotli
#   2. npm pack @fontsource/m-plus-rounded-1c を実行し、できた .tgz を展開する（package/files/ ができる）
#   3. python tools/subset-font.py <package/files のパス>
# 入れる文字：ASCII、全角の記号・英数字、ひらがな、カタカナ、index.html に出てくる文字
# ここにない文字（ニックネームなど）は、端末の日本語の字体で表示される
import os, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
src = sys.argv[1] if len(sys.argv) > 1 else 'package/files'
chars = set(chr(c) for c in range(0x20, 0x7f))
for a, b in [(0x3000, 0x3100), (0xff01, 0xff5f)]:
    chars |= set(chr(c) for c in range(a, b))
with open(os.path.join(root, 'index.html'), encoding='utf-8') as f:
    chars |= set(f.read())
text = ''.join(sorted(c for c in chars if c.isprintable()))
tmp = os.path.join(here, '_chars.txt')
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(text)
os.makedirs(os.path.join(root, 'fonts'), exist_ok=True)
for w in (500, 800):
    out = os.path.join(root, 'fonts', f'mplus-rounded-{w}.woff2')
    subprocess.run(['pyftsubset', os.path.join(src, f'm-plus-rounded-1c-japanese-{w}-normal.woff2'),
                    f'--text-file={tmp}', '--flavor=woff2', '--layout-features=*', f'--output-file={out}'], check=True)
    print(out, os.path.getsize(out), 'bytes')
os.remove(tmp)
