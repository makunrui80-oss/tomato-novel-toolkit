"""Run with: python3 -m unittest -v test_converter.py"""
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from epub_to_txt import ConversionError, TextExtractor, convert, read_book


def make_epub(path, *, version="3.0", missing=False, encrypted=None, encoding="utf-8"):
    container = '''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="Book/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
    package = f'''<package xmlns="http://www.idpf.org/2007/opf" version="{version}">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>中文测试书</dc:title><dc:creator>测试作者</dc:creator></metadata>
      <manifest>
        <item id="second" href="Text/second.xhtml" media-type="application/xhtml+xml"/>
        <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
        <item id="appendix" href="extra.xhtml" media-type="application/xhtml+xml"/>
        <item id="first" href="Text/first%20chapter.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine><itemref idref="nav"/><itemref idref="first"/><itemref idref="second"/><itemref idref="appendix" linear="no"/></spine>
    </package>'''
    first = f'''<?xml version="1.0" encoding="{encoding}"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>不该出现在正文的标题</title><style>hidden style</style></head><body><h1>第一章</h1><p>你好，<strong>世界</strong>！ &amp; A&nbsp;B</p><p>下一段<br/>下一行。<script>hidden script</script></p><p><ruby>汉<rt>hàn</rt></ruby>字。</p></body></html>'''
    with ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("Book/package.opf", package)
        z.writestr("Book/nav.xhtml", "<html><body>跳过目录页</body></html>")
        z.writestr("Book/extra.xhtml", "<html><body>跳过附加页</body></html>")
        if not missing:
            z.writestr("Book/Text/second.xhtml", "<html><body><h1>第二章</h1><p>结束。</p></body></html>")
        z.writestr("Book/Text/first chapter.xhtml", first.encode(encoding))
        if encrypted:
            z.writestr("META-INF/encryption.xml", f'''<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData><enc:CipherData><enc:CipherReference URI="{encrypted}"/></enc:CipherData></enc:EncryptedData></encryption>''')


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.source = self.folder / "中文书.epub"

    def tearDown(self):
        self.tmp.cleanup()

    def test_epub2_and_epub3_order_content_metadata_and_bom(self):
        for version in ("2.0", "3.0"):
            with self.subTest(version=version):
                make_epub(self.source, version=version)
                target = convert(self.source)
                self.assertTrue(target.read_bytes().startswith(b"\xef\xbb\xbf"))
                text = target.read_text(encoding="utf-8-sig")
                self.assertTrue(text.startswith("中文测试书\n作者：测试作者\n\n"))
                self.assertLess(text.index("第一章"), text.index("第二章"))
                self.assertIn("你好，世界！ & A B", text)
                self.assertIn("下一段\n下一行。", text)
                self.assertIn("汉字。", text)
                for unwanted in ("不该出现", "hidden", "跳过", "hàn"):
                    self.assertNotIn(unwanted, text)

    def test_existing_txt_is_never_overwritten_and_new_folder_is_created(self):
        make_epub(self.source)
        output = self.folder / "新的输出"
        output.mkdir()
        original = output / "中文书.txt"
        original.write_text("keep me", encoding="utf-8")
        self.assertEqual(convert(self.source, output).name, "中文书_2.txt")
        self.assertEqual(convert(self.source, output).name, "中文书_3.txt")
        self.assertEqual(original.read_text(encoding="utf-8"), "keep me")
        self.assertTrue(convert(self.source, output / "子目录").is_file())

    def test_gb18030_document(self):
        make_epub(self.source, encoding="gb18030")
        self.assertIn("你好，世界", read_book(self.source).chapters[0])

    def test_missing_chapter_fails_without_partial_txt(self):
        make_epub(self.source, missing=True)
        with self.assertRaisesRegex(ConversionError, "缺少内部文件"):
            convert(self.source)
        self.assertFalse(list(self.folder.glob("*.txt")))

    def test_drm_body_rejected_but_font_obfuscation_allowed(self):
        make_epub(self.source, encrypted="Book/Text/second.xhtml")
        with self.assertRaisesRegex(ConversionError, "DRM"):
            read_book(self.source)
        make_epub(self.source, encrypted="Book/fonts/font.otf")
        self.assertEqual(len(read_book(self.source).chapters), 2)

    def test_invalid_archive_and_image_only_book_report_errors(self):
        self.source.write_bytes(b"not a zip")
        with self.assertRaisesRegex(ConversionError, "无法读取"):
            read_book(self.source)
        make_epub(self.source)
        with ZipFile(self.source, "a") as z:
            # Replace both body documents with image-only documents via a fresh archive.
            entries = {name: z.read(name) for name in z.namelist()}
        entries["Book/Text/second.xhtml"] = b'<html><body><img src="a.png"/></body></html>'
        entries["Book/Text/first chapter.xhtml"] = entries["Book/Text/second.xhtml"]
        with ZipFile(self.source, "w") as z:
            for name, data in entries.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ConversionError, "OCR"):
            read_book(self.source)

    def test_self_closing_ignored_nodes_do_not_hide_body(self):
        parser = TextExtractor()
        parser.feed('<html><head><meta charset="utf-8"/><style>ignore</style></head><body><p>保留<svg/>正文</p></body></html>')
        self.assertEqual(parser.text(), "保留正文")


if __name__ == "__main__":
    unittest.main()
