import unittest

from pygments.token import Token
from PySide6.QtCore import QThread

from tests import qt

qt.app()

from premerge.ui import icons, jobs, theme  # noqa: E402
from premerge.ui.markdown import MarkdownView  # noqa: E402


class IconTests(unittest.TestCase):
    def test_every_shape_renders(self) -> None:
        for name in icons._SHAPES:
            pix = icons.pixmap(name, "#ffffff", 24)
            img = pix.toImage()
            opaque = any(img.pixelColor(x, y).alpha() for x in range(24) for y in range(24))
            self.assertTrue(opaque, name)
            self.assertFalse(icons.icon(name).isNull(), name)


class ThemeTests(unittest.TestCase):
    def test_syntax_color(self) -> None:
        self.assertEqual(theme.syntax_color(Token.Keyword)[0], theme.NIGHT.syntax["keyword"])
        self.assertTrue(theme.syntax_color(Token.Comment.Single)[2])
        self.assertEqual(theme.syntax_color(Token.Text), (theme.NIGHT.fg, False, False))
        self.assertEqual(theme.syntax_color(Token.Keyword.Constant)[0], theme.NIGHT.syntax["constant"])

    def test_stylesheet_and_apply(self) -> None:
        self.assertTrue(theme.stylesheet(theme.NIGHT).strip())
        theme.apply(qt.app())


class JobTests(unittest.TestCase):
    def test_done_on_gui_thread(self) -> None:
        got = []
        jobs.run(lambda: 42, on_done=lambda v: got.append((v, QThread.currentThread())))
        self.assertTrue(qt.wait_until(lambda: got))
        self.assertEqual(got[0][0], 42)
        self.assertIs(got[0][1], qt.app().thread())

    def test_error(self) -> None:
        got = []

        def boom() -> None:
            raise ValueError("bad")

        jobs.run(boom, on_error=got.append)
        self.assertTrue(qt.wait_until(lambda: got))
        self.assertIsInstance(got[0], ValueError)


class MarkdownTests(unittest.TestCase):
    def test_height_grows(self) -> None:
        small, big = MarkdownView(), MarkdownView()
        for view in (small, big):
            view.resize(400, 10)
        small.set_markdown("one line")
        big.set_markdown("# Hi\n\n- a\n- [x] b\n\n```py\nx=1\n```")
        self.assertGreater(big.height(), small.height())


if __name__ == "__main__":
    unittest.main()
