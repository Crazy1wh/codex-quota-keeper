import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codex_quota_keeper as keeper


class FormatTests(unittest.TestCase):
    def test_usage_formats_fullwidth(self):
        self.assertEqual(keeper.format_usage(0), "　０％")
        self.assertEqual(keeper.format_usage(31), "３１％")
        self.assertEqual(keeper.format_usage(100), "１００％")
        self.assertEqual(keeper.format_usage(None), "暂未获取")


class VerificationTests(unittest.TestCase):
    def setUp(self):
        log_patcher = mock.patch.object(keeper, "log")
        log_patcher.start()
        self.addCleanup(log_patcher.stop)
        self.state = keeper.default_state()
        self.info = {
            "used_percent": 1,
            "reset_at": 2_000,
            "window_minutes": 300,
            "weekly": None,
        }

    @mock.patch.object(keeper, "notify_refresh_success")
    @mock.patch.object(keeper, "save_state")
    @mock.patch.object(keeper, "get_rate_limits")
    @mock.patch.object(keeper.time, "sleep")
    @mock.patch.object(keeper.time, "time", return_value=1_000)
    def test_only_confirmed_success_notifies(
        self, _time, _sleep, get_rate_limits, _save_state, notify
    ):
        get_rate_limits.return_value = self.info

        self.assertTrue(keeper.verify_after_activation(self.state, 1_000))
        notify.assert_called_once_with(self.info)

        notify.reset_mock()
        get_rate_limits.return_value = dict(self.info, reset_at=1_050)
        self.assertFalse(keeper.verify_after_activation(self.state, 1_000))
        notify.assert_not_called()

    @mock.patch.object(keeper, "notify_refresh_success", return_value=False)
    @mock.patch.object(keeper, "save_state")
    @mock.patch.object(keeper, "get_rate_limits")
    @mock.patch.object(keeper.time, "sleep")
    @mock.patch.object(keeper.time, "time", return_value=1_000)
    def test_notification_failure_preserves_confirmed_state(
        self, _time, _sleep, get_rate_limits, save_state, _notify
    ):
        get_rate_limits.return_value = self.info

        self.assertTrue(keeper.verify_after_activation(self.state, 1_000))
        self.assertTrue(self.state["last_activation_success"])
        self.assertEqual(self.state["reset_at"], 2_000)
        save_state.assert_called_once_with(self.state)


class FilesystemTests(unittest.TestCase):
    def test_parent_directories_are_created(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "state" / "nested" / "state.json"
            log_file = root / "log" / "nested" / "keeper.log"

            with mock.patch.object(keeper, "STATE_FILE", state_file), mock.patch.object(
                keeper, "LOG_FILE", log_file
            ):
                keeper.save_state({"ok": True})
                keeper.log("test")

            self.assertEqual(json.loads(state_file.read_text()), {"ok": True})
            self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)
            self.assertIn("test", log_file.read_text())
            self.assertEqual(log_file.stat().st_mode & 0o777, 0o600)


class NotificationTests(unittest.TestCase):
    def test_notification_payload_and_failure(self):
        import io
        from urllib.parse import urlsplit, unquote, parse_qs
        info = {'used_percent': 0, 'reset_at': 0,
                'weekly': {'used_percent': 31, 'reset_at': 0}}
        with mock.patch.object(keeper, 'bark_url', return_value='https://example.invalid/test'), \
             mock.patch.object(keeper, 'log'), \
             mock.patch.object(keeper, 'urlopen', return_value=io.StringIO('{"code":200}')) as send:
            self.assertTrue(keeper.notify_refresh_success(info))
            url = urlsplit(send.call_args.args[0])
            expected = keeper.format_reset(0)
            self.assertTrue(unquote(url.path).endswith(
                f'５小时 · 已用 　０％ · {expected}\n周额度 · 已用 ３１％ · {expected}'))
            self.assertEqual(parse_qs(url.query)['isArchive'], ['1'])
            send.side_effect = OSError('network failure')
            self.assertFalse(keeper.notify_refresh_success(info))


class BarkConfigurationTests(unittest.TestCase):
    def test_missing_bark_configuration_is_silent(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ,
            {"BARK_URL_FILE": str(Path(temp_dir) / "missing")},
            clear=False,
        ), mock.patch.dict(os.environ, {"BARK_URL": ""}, clear=False), mock.patch.object(
            keeper, "log"
        ) as log:
            self.assertFalse(keeper.notify_refresh_success({}))
            log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
