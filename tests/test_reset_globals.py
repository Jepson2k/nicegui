import sys

from nicegui import Client, ui
from nicegui.testing import general


def test_reset_globals_preserves_main_module():
    main_module = sys.modules['__main__']
    page = None
    try:
        with general.nicegui_reset_globals():
            @ui.page('/page-in-main-file')
            def page():
                ui.label('Hello')
            # runpy executes an app's main file with run_name='__main__' (as the User and
            # Screen fixtures do), so the file's page functions are owned by that module
            page.__module__ = '__main__'
        assert '__main__' in sys.modules, \
            'multiprocessing reads sys.modules["__main__"] when preparing every spawn/forkserver worker'
    finally:
        sys.modules.setdefault('__main__', main_module)
        if page is not None:
            Client.page_routes.pop(page, None)
