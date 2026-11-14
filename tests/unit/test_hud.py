from unittest.mock import Mock
import unittest
import numpy as np
from idleon_darts.hud import HudReader,wind_ink


class WindTextTests(unittest.TestCase):
    def test_bright_wind_letters_include_white_highlights_but_ignore_transparency(self):
        image=np.array([[[255,255,255,255],[220,90,210,255],[20,25,50,255],[255,255,255,0]]],dtype='uint8')
        self.assertEqual(wind_ink(image).tolist(),[[1,1,0,0]])

    def test_wind_digits_exclude_the_coloured_header(self):
        reader=object.__new__(HudReader);reader.none_mask=None;reader.cache=None
        reader.config=dict(wind_region=[0,0,100,47],arrow_split=64,scale=1.)
        reader.digits_in=Mock(return_value=None)
        image=np.zeros((47,100,3),dtype='uint8');image[2:8,2:8]=(20,180,250)
        image[24:32,10:16]=255
        self.assertIsNone(reader.wind(image))
        mask=reader.digits_in.call_args.args[0]
        self.assertEqual(mask.shape,(31,64));self.assertEqual(int(mask.sum()),48)
