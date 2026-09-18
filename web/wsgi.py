"""The entry point: the one line that turns the app/ package into a running site.

Locally:

    cd web
    python wsgi.py          # then open http://localhost:5000

On the server, the web host does not run this file -- it imports `app` from it.
PythonAnywhere's WSGI configuration file needs exactly one line for that:

    from wsgi import app as application

If you rename this file, that line has to change with it.

The name is the standard one for this job. WSGI is the interface Python web
servers speak, and a "wsgi.py" holding an importable `app` is what a host looks
for. It cannot be called app.py, because app/ next to it is the package and
Python would not know which one `import app` meant.
"""
from app import create_app

app = create_app()


if __name__ == '__main__':
    # Local development only. The debugger runs code typed into the browser, so
    # it is set here, where it only applies to `python wsgi.py`, rather than in
    # config.py where the deployed site would pick it up too.
    app.run(debug=True)
