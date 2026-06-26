"""
main.py
────────
Punto de entrada de la aplicación.
Lanza pywebview apuntando al dist_ui/ compilado por Vite.
"""

import webview
from api import AudioToolsAPI

def main():
    api = AudioToolsAPI()

    window = webview.create_window(
        title     = 'Audio Tools',
        url       = 'dist_ui/index.html',
        js_api    = api,
        width     = 960,
        height    = 640,
        min_size  = (800, 560),
        resizable = True,
        frameless = False,
    )

    api.set_window(window)

    webview.start(debug=False)

if __name__ == '__main__':
    main()