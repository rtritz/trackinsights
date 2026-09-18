"""Turn a Markdown document in this folder into a PDF you can hand out.

    python docs/make_pdf.py                    # PROJECT_GUIDE.md -> PROJECT_GUIDE.pdf
    python docs/make_pdf.py design.md          # any other .md in docs/

Two steps: Markdown -> HTML (the `markdown` package, installed with the `dev`
extra), then HTML -> PDF using the copy of Chrome or Edge already on the
machine, in headless mode. That second step is why there is nothing to install
beyond one small Python package -- no LaTeX, no wkhtmltopdf, no pandoc.

The PDF is a build output, like output.css. It is not tracked in git: rerun this
after editing the Markdown rather than passing an old PDF around.
"""
import os
import subprocess
import sys
import webbrowser

DOCS = os.path.dirname(os.path.abspath(__file__))

# Where the browsers install themselves on Windows. The first one found wins;
# either renders identically for our purposes.
BROWSERS = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]

# Print styling. The rules that matter are the break-* ones: without them a
# directory tree or a table splits across a page boundary and becomes unreadable
# on paper, which is the whole point of making a PDF.
CSS = """
@page { size: Letter; margin: 0.75in 0.7in; }

body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.5;
  color: #1a1a1a;
  max-width: 100%;
}

h1 { font-size: 22pt; margin: 0 0 0.1in; border-bottom: 3px solid #c2410c;
     padding-bottom: 6px; }
h2 { font-size: 15pt; margin: 22pt 0 8pt; color: #9a3412;
     border-bottom: 1px solid #e5e5e5; padding-bottom: 4px; }
h3 { font-size: 12pt; margin: 16pt 0 6pt; color: #1a1a1a; }
h1, h2, h3 { break-after: avoid; }

p, li { orphans: 2; widows: 2; }
ul, ol { padding-left: 22px; }
li { margin: 3px 0; }

/* Box-drawing characters in the directory trees need a font that has them.
   Consolas and Cascadia Mono both do; the generic fallback may not. */
code, pre {
  font-family: Consolas, "Cascadia Mono", "DejaVu Sans Mono", monospace;
}
code { font-size: 9.5pt; background: #f3f4f6; padding: 1px 4px;
       border-radius: 3px; }
pre {
  background: #f8f8f7;
  border: 1px solid #e5e5e5;
  border-left: 3px solid #c2410c;
  border-radius: 4px;
  padding: 9px 11px;
  font-size: 8pt;
  line-height: 1.35;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: inherit; }

table { border-collapse: collapse; width: 100%; margin: 10pt 0;
        font-size: 9.5pt; break-inside: avoid; }
th, td { border: 1px solid #ddd; padding: 5px 8px; text-align: left;
         vertical-align: top; }
th { background: #f3f4f6; font-weight: 600; }

hr { border: none; border-top: 1px solid #e5e5e5; margin: 18pt 0; }
a { color: #9a3412; text-decoration: none; }

strong { color: #111; }
blockquote { border-left: 3px solid #ddd; margin-left: 0; padding-left: 12px;
             color: #555; }

.footer { margin-top: 24pt; padding-top: 8pt; border-top: 1px solid #e5e5e5;
          font-size: 8.5pt; color: #777; }
"""


def find_browser():
    for path in BROWSERS:
        if os.path.exists(path):
            return path
    return None


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'PROJECT_GUIDE.md'
    if not name.endswith('.md'):
        name += '.md'
    src = os.path.join(DOCS, name)
    if not os.path.exists(src):
        sys.exit('No such file: %s' % src)

    try:
        import markdown
    except ImportError:
        sys.exit('Install it first:  pip install markdown\n'
                 '(or reinstall the dev extra: pip install -e ".[web,dev]")')

    with open(src, encoding='utf-8') as fh:
        text = fh.read()

    body = markdown.markdown(
        text, extensions=['tables', 'fenced_code', 'sane_lists', 'attr_list'])

    title = name[:-3].replace('_', ' ').title()
    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<title>%s</title><style>%s</style></head><body>%s'
        '<p class="footer">Track Insights &mdash; generated from docs/%s. '
        'Edit the Markdown, not this PDF.</p>'
        '</body></html>' % (title, CSS, body, name)
    )

    html_path = os.path.join(DOCS, '.%s.html' % name[:-3])
    pdf_path = os.path.join(DOCS, '%s.pdf' % name[:-3])
    with open(html_path, 'w', encoding='utf-8') as fh:
        fh.write(html)

    browser = find_browser()
    if not browser:
        # No browser where we expected one: hand over the HTML and let the
        # reader print it themselves. Ctrl+P -> Save as PDF does the same job.
        webbrowser.open('file:///' + html_path.replace('\\', '/'))
        print('Could not find Chrome or Edge, so the HTML is open in your '
              'browser instead.\nPrint it with Ctrl+P -> Save as PDF.')
        return

    subprocess.run([
        browser,
        '--headless',
        '--disable-gpu',
        '--no-pdf-header-footer',
        '--print-to-pdf=%s' % pdf_path,
        'file:///' + html_path.replace('\\', '/'),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    os.remove(html_path)
    print('%s  (%.0f KB)' % (pdf_path, os.path.getsize(pdf_path) / 1024.0))


if __name__ == '__main__':
    main()
