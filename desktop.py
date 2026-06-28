import logging
import threading
import webview
from app import triggers
from app.web import create_app
from app.config import settings, setup_logging

log = logging.getLogger(__name__)

def start_server():
    app = create_app(scrape_trigger=triggers.scrape)
    # Run the server. use_reloader=False is necessary when running in a thread with pywebview.
    app.run(host="127.0.0.1", port=settings.flask_port, debug=False, use_reloader=False)

if __name__ == '__main__':
    setup_logging()
    log.info("desktop app เริ่มทำงาน (Flask + webview, ไม่มี scheduler)")
    # Start Flask in a background thread
    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()

    # Create and start the PyWebView Desktop Window
    webview.create_window(
        title='PC Price Tracker',
        url=f'http://127.0.0.1:{settings.flask_port}',
        width=1280,
        height=800,
        min_size=(800, 600)
    )
    webview.start()
