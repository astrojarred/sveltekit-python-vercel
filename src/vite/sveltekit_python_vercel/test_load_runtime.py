import types
import unittest

from load_runtime import (
    SKPVError,
    inject_load_helpers,
    parse_load_result,
    redirect,
    run_load,
    wrap_event,
)


class ParseLoadResultTests(unittest.TestCase):
    def test_data(self):
        self.assertEqual(
            parse_load_result({"ok": True}),
            {"type": "data", "data": {"ok": True}},
        )

    def test_error_tuple(self):
        self.assertEqual(
            parse_load_result(("error", 404, "Not found")),
            {"type": "error", "status": 404, "body": "Not found"},
        )

    def test_redirect_tuple(self):
        self.assertEqual(
            parse_load_result(("redirect", 307, "/login")),
            {"type": "redirect", "status": 307, "location": "/login"},
        )

    def test_tuple_data_not_misread(self):
        self.assertEqual(
            parse_load_result(("items", 1, 2)),
            {"type": "data", "data": ("items", 1, 2)},
        )


class RunLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_injected_error(self):
        mod = types.ModuleType("test")
        exec(
            compile(
                "async def load(event):\n    error(403, 'denied')\n",
                "<test>",
                "exec",
            ),
            mod.__dict__,
        )
        result = await run_load(mod, {"params": {}})
        self.assertEqual(result["type"], "error")
        self.assertEqual(result["status"], 403)

    async def test_injected_redirect(self):
        mod = types.ModuleType("test")
        exec(
            compile(
                "async def load(event):\n    redirect(307, '/home')\n",
                "<test>",
                "exec",
            ),
            mod.__dict__,
        )
        result = await run_load(mod, {"params": {}})
        self.assertEqual(result["type"], "redirect")
        self.assertEqual(result["location"], "/home")

    async def test_return_tuple_error(self):
        mod = types.ModuleType("test")

        async def load(event):
            return ("error", 404, "missing")

        mod.load = load
        result = await run_load(mod, {"params": {}})
        self.assertEqual(result, {"type": "error", "status": 404, "body": "missing"})

    async def test_wrap_event_parent_and_cookies(self):
        mod = types.ModuleType("test")
        captured = {}

        async def load(event):
            captured["theme"] = event.parent.theme
            captured["session"] = event.cookies.get("session")
            return {"ok": True}

        mod.load = load
        await run_load(
            mod,
            {
                "params": {"id": "1"},
                "parent": {"theme": "dark"},
                "cookies": {"session": "abc"},
            },
        )
        self.assertEqual(captured["theme"], "dark")
        self.assertEqual(captured["session"], "abc")

    async def test_user_error_helper_not_overwritten(self):
        mod = types.ModuleType("test")

        def custom_error(status, body):
            raise SKPVError(418, "teapot")

        mod.error = custom_error

        async def load(event):
            custom_error(404, "ignored")

        mod.load = load
        inject_load_helpers(mod)
        with self.assertRaises(SKPVError) as ctx:
            await mod.load(wrap_event({}))
        self.assertEqual(ctx.exception.status, 418)


if __name__ == "__main__":
    unittest.main()
