import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compose_collage as compose
import make_sticker as sticker

class QualityTests(unittest.TestCase):
    def test_alpha_preserved_in_shadow(self):
        img = Image.new('RGBA', (4, 4), (200, 100, 50, 128))
        result = sticker.add_drop_shadow(img, opacity=0)
        self.assertEqual(result.getpixel((17, 17)), img.getpixel((1, 1)))

    def test_backend_cannot_replace_original_rgb(self):
        original = Image.new('RGBA', (20, 10), (17, 73, 129, 255))
        fake = Image.new('RGBA', (5, 5), (255, 0, 0, 128))
        with patch.dict(sys.modules, {'rembg': SimpleNamespace(remove=lambda _: fake)}):
            result = sticker.cutout_with_rembg(original)
        self.assertEqual(result.size, original.size)
        self.assertEqual(result.getpixel((10, 5)), (17, 73, 129, 128))

    def test_transparent_padding_does_not_hide_upscale(self):
        with tempfile.TemporaryDirectory() as d:
            img=Image.new('RGBA', (100, 100))
            img.paste((200, 100, 50, 255), (40, 40, 60, 60))
            p=Path(d)/'p.png'; img.save(p)
            with self.assertRaises(ValueError):
                compose.place_element(Image.new('RGBA',(100,100)), {'path':str(p),'width':40,'x':50,'y':50}, {})

    def test_exact_pixels_at_native_scale(self):
        with tempfile.TemporaryDirectory() as d:
            img=Image.new('RGBA',(20,10),(17,73,129,255)); p=Path(d)/'p.png';img.save(p)
            canvas=Image.new('RGBA',(20,10))
            compose.place_element(canvas, {'path':str(p),'width':20,'x':10,'y':5}, {})
            self.assertEqual(canvas.tobytes(),img.tobytes())

    def test_cli_defaults_failure_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out.png'
            command=[sys.executable,compose.__file__,'--output',str(out),'--json']
            result=subprocess.run(command+['{}'],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with Image.open(out) as im: self.assertEqual(im.size,(2160,2880))
            self.assertEqual(json.loads(out.with_suffix('.quality.json').read_text())['canvas'],[2160,2880])
            out.unlink()
            result=subprocess.run(command+[json.dumps({'elements':[{'path':str(Path(d)/'missing.png'),'x':0,'y':0}]})],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(out.exists())

if __name__=='__main__': unittest.main()
