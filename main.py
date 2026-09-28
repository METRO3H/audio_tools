import sys
import ctypes
import webview
from api import AudioToolsAPI


def get_screen_center(width, height):
    user32 = ctypes.windll.user32
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    x = (sw - width) // 2
    y = (sh - height) // 2
    return x, y


def main():
    debug = "--debug" in sys.argv

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

    def on_closing():
        api.cancel()

    window.events.closing += on_closing
    api.set_window(window)
    webview.start(debug=debug)


if __name__ == '__main__':
    main()