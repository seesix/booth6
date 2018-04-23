import pygame
from abc import ABCMeta, abstractmethod
from io import BytesIO

from PIL import Image as PILImage
from wand.image import Image as WandImage
from wand.color import Color

import config
from utils import grouper
from itertools import izip

from wand.image import Image
from wand.color import Color
from wand.drawing import Drawing as WandDrawing


class GIFMaker(object):
    """ Abstract base class for making 4up gif from photos """

    __metaclass__ = ABCMeta

    n_photos = config.n_frames * config.photos_per_frame
    frame_d = (config.photo_w * 2, config.photo_h * 2+50)

    @abstractmethod
    def make_frame(self, streams):
        raise NotImplemented

    def make_frames(self, photos):
#        for chunk in grouper(config.photos_per_frame, photos):
         for chunk in grouper(config.photos_per_frame, photos):
            yield self.make_frame(chunk)

    @abstractmethod
    def make_gif(self, frames):
        raise NotImplemented

    @abstractmethod
    def make_pygame_frame(self, frame):
        raise NotImplemented


class PILGIFMaker(GIFMaker):
    """ Class for making a 4up gif using PIL. Output is not compressed """

    def make_frame(self, streams):
        frame = PILImage.new('RGB', self.frame_d)
        for n, stream in enumerate(streams):
            img = PILImage.open(stream)
            x = config.photo_w * ((n >> 1) & 1)
            y = config.photo_h * (n & 1)
            box = (x, y, x+config.photo_w, y+config.photo_h)
            frame.paste(img, box)
        return frame

    def make_gif(self, frames):
        stream = BytesIO()
        frames[0].save(
            stream, format='GIF',
            save_all=True, append_images=frames[1:], loop=0,
            duration=config.frame_duration_ms, optimize=True
        )
        stream.seek(0)
        return stream

    def make_pygame_frame(self, frame):
        # TODO benchmark vs writing to bytesIO
        # TODO test the impact of convert()
        return pygame.image.fromstring(frame.tobytes(), frame.size, frame.mode).convert()


class WandGIFMaker(GIFMaker):
    """ Class for making a 4up gif using ImageMagick via Wand. Output is compressed """

    def make_frame(self, streams):
        frame = WandImage(width=self.frame_d[0],background=Color('white'), height=self.frame_d[1])   

        for n, stream in enumerate(streams):
            img = WandImage(file=stream)
            x = config.photo_w * ((n >> 1) & 1)
            y = config.photo_h * (n & 1)
            frame.composite(img, left=x+18, top=y+18)
            drawing = WandDrawing()
#            drawing.font = '/home/pi/booth4/fonts/Steelworks.otf'
            drawing.font = '/home/pi/booth6/fonts/Vulturemotor.otf'
            drawing.font_size = 20
#            drawing.font_style = 'italic'
#            drawing.fill_color = Color('orange')
#            drawing.stroke_color = Color('brown')
            drawing.text(310, 660, 'The Mighty Booth') 
            drawing(frame)
        return frame

    def make_gif(self, frames):
        anim = WandImage()
        for image in frames:
            anim.sequence.append(image)

        for n in xrange(len(anim.sequence)):
            with anim.sequence[n] as frame:
                frame.delay = config.frame_duration_ms / 10       

        anim.format = 'gif'
        anim.type = 'optimize'  
        

        stream = BytesIO()
        anim.save(file=stream)
        stream.seek(0)
        return stream

    def make_pygame_frame(self, frame):
        return pygame.image.load(BytesIO(frame.make_blob('gif'))).convert()
