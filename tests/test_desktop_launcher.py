import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import desktop_launcher


class DesktopLauncherTests(unittest.TestCase):
    def test_launcher_opens_local_page_and_stops_owned_server(self):
        handle = object()
        with mock.patch.object(
            desktop_launcher,
            "start_background_server",
            return_value=handle,
        ), mock.patch.object(
            desktop_launcher.webbrowser,
            "open",
        ) as open_browser, mock.patch.object(
            desktop_launcher,
            "wait_until_exit",
        ), mock.patch.object(
            desktop_launcher,
            "stop_background_server",
        ) as stop_server:
            exit_code = desktop_launcher.main()

        self.assertEqual(exit_code, 0)
        open_browser.assert_called_once_with("http://127.0.0.1:8787/")
        stop_server.assert_called_once_with(handle)

    def test_launcher_does_not_stop_server_it_did_not_start(self):
        with mock.patch.object(
            desktop_launcher,
            "start_background_server",
            return_value=None,
        ), mock.patch.object(desktop_launcher.webbrowser, "open"), mock.patch.object(
            desktop_launcher,
            "wait_until_exit",
        ) as wait, mock.patch.object(
            desktop_launcher,
            "stop_background_server",
        ) as stop_server:
            exit_code = desktop_launcher.main()

        self.assertEqual(exit_code, 0)
        wait.assert_not_called()
        stop_server.assert_not_called()

    def test_bundled_browser_path_is_exported_for_playwright(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ,
            {"DOUYIN_PARSE_ROOT": temp_dir},
            clear=True,
        ):
            browser_dir = Path(temp_dir) / "browsers"
            browser_dir.mkdir()

            desktop_launcher.configure_bundled_browser()

            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(browser_dir.resolve()))


if __name__ == "__main__":
    unittest.main()
