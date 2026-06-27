"""
main.py
────────
Punto de entrada de la aplicación.
Lanza pywebview apuntando al dist_ui/ compilado por Vite.
"""

import webview
from api import AudioToolsAPI
import ctypes

def get_screen_center(width, height):
    user32 = ctypes.windll.user32
    sw = user32.GetSystemMetrics(0)  # ancho de pantalla
    sh = user32.GetSystemMetrics(1)  # alto de pantalla
    x = (sw - width) // 2
    y = (sh - height) // 2
    return x, y

def main():
    api = AudioToolsAPI()

    W, H = 960, 640
    x, y = get_screen_center(W, H)

    window = webview.create_window(
        title     = 'Audio Tools',
        url       = 'dist_ui/index.html',
        js_api    = api,
        width     = W,
        height    = H,
        min_size  = (800, 560),
        resizable = True,
        frameless = False,
        x         = x,
        y         = y,
    )

    api.set_window(window)

    webview.start(debug=True)

if __name__ == '__main__':
    main()