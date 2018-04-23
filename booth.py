#!/usr/bin/env python
import logging
import pygame
import os
import sys
import time
from pygame.locals import QUIT, KEYDOWN, K_ESCAPE, USEREVENT, K_SPACE

from io import BytesIO

from threading import Thread, Event
from Queue import Queue, Empty as QueueEmpty

import config
from config import upload_ts_fmt
from gifmaker import PILGIFMaker, WandGIFMaker
from utils import upload, AnyEvent, mock_take_photos

import picamera
import RPi.GPIO as GPIO
import atexit
#from PIL import Image
#import io
import paramiko

import glob
import jinja2
from jinja2 import Environment, FileSystemLoader

from config import render_template, upload_path_url, upload_server, upload_user


real_path = os.path.dirname(os.path.realpath(__file__))

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(name)s.%(funcName)s +%(lineno)s: %(levelname)-8s [%(process)d] %(message)s',
)

class BoothBackgroundThread(Thread):
    """ Worker thread to create 4up gif and upload it while the main thread runs the display """

    def __init__(self, input_q, frame_q, gif_q, upload_q, gifmaker_cls):
    
        super(BoothBackgroundThread, self).__init__()
        self.gifmaker = gifmaker_cls()
        self.input_q = input_q
        self.frame_q = frame_q
        self.gif_q = gif_q
        self.upload_q = upload_q

        self.request_stop = Event()
        self.processing = Event()
        self.done = Event()
        self.upload = Event()
#        self.upload_q = Event()

    def run(self):
        while not self.request_stop.is_set():

            # wait for input or exit
            AnyEvent(self.processing, self.request_stop).wait()
            if self.request_stop.is_set():
                logging.debug('quitting before starting')
                return

            # rely on processing event to signal that we are good to go, WON'T SCALE to multiple worker threads
            photos = self.input_q.get_nowait()
            logging.debug('got photos')

            frames = []
            for frame in self.gifmaker.make_frames(photos):
                frames.append(frame)
                # time.sleep(2) # test delay
                logging.debug('got frame')
                self.frame_q.put(frame)

                if self.request_stop.is_set():
                    logging.debug('stopping thread before making gif')
                    return

            gif = self.gifmaker.make_gif(frames)
            # time.sleep(5) # test delay
            self.gif_q.put(gif)
            

            # wait for upload trigger OR quit signal
            AnyEvent(self.upload, self.request_stop).wait()
            if self.request_stop.is_set():
                logging.debug('stopping thread before uploading')
                return

            logging.debug('uploading')
            path_name = config.upload_path_fmt.format(time.strftime(config.upload_ts_fmt))
            path_link = config.upload_path_lnk.format(time.strftime(config.upload_ts_fmt))
            path_qr = config.upload_path_qr.format(time.strftime(config.upload_ts_fmt))
            path_url = config.upload_path_url.format(time.strftime(config.upload_ts_fmt))
#            path_qr_url = 'http://indika.net/booth/output_' + (upload_ts_fmt) + '.html'


#            path_qr_url = config.upload_qr_url.format(time.strftime(config.upload_ts_fmt))




            
            templateLoader = jinja2.FileSystemLoader( searchpath="/home/pi/booth6/")
            templateEnv = jinja2.Environment( loader=templateLoader )
            TEMPLATE_FILE = "template.j2"
            template = templateEnv.get_template( TEMPLATE_FILE )
            template_vars = {
                "path_link": path_link
            }
            template.render()
            outputText = template.render(template_vars) 
            

#            template = templateEnv.get_template( TEMPLATE_FILE ).render(booth_url = path_url)

#            env = Environment(loader=FileSystemLoader(current_directory))
#
#            # Find all files with the j2 extension in the current directory
#            templates = glob.glob('*.j2') 
#            render_template = config.social_template
#            render_template = config.render_template
#            return env.get_template(render_template).render(path_link, path_url)
#            for f in templates:
#                rendered_string = render_template(f)
 

#           print(rendered_string)



            ssh = paramiko.SSHClient() 
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.load_host_keys('/home/pi/.ssh/known_hosts')
            ssh.connect(upload_server, username=upload_user)
            sftp = ssh.open_sftp()
#            Html_file = sftp.open('output_' + (config.upload_ts_fmt) + '.html',"w")
            Html_file = sftp.open(path_url,"w")
            Html_file.write(outputText)
            Html_file.close()

#    sftp.putfo(stream, path)  # assumes the stream is at the start or wherever the user intended
#    logging.debug('Uploaded {}'.format(path))
            sftp.close()
            ssh.close()
    



            qr_stream = upload(gif, config.upload_server, config.upload_user, path_name, path_qr)
            self.upload_q.put(qr_stream)  # you will need to add another stream to the thread class... or we could re-use the gif stream
            # time.sleep(5) # test delay
            logging.debug('upload done')

            self.upload.clear()
            self.processing.clear()
            self.done.set()

        logging.debug('stopping thread')

    def join(self, timeout=None):
        self.request_stop.set()
        super(BoothBackgroundThread, self).join(timeout)


def cleanup():
    logging.debug('Ended abruptly')
    pygame.quit()
    GPIO.cleanup()
    # TODO might need global access to thread here to ensure it has been joined?


def check_input(events, bg_thread):
    """
    Check pygame inputs and exit if requested.
    Unnecessary and arguably bad in the RPi codebase, but essential for testing on desktop
    """
    for event in events:  # Hit the ESC key to quit the slideshow.
        if (event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE)):
            logging.debug('STOPPING')
            # must join the thread in case it is blocked waiting
            bg_thread.join()
            pygame.quit()
            sys.exit()


def get_dims_and_offset(img_w, img_h):
    # Note this only works when in booting in desktop mode.
    # When running in terminal, the size is not correct (it displays small). Why?

    # based on output screen resolution, calculate how to display
    ratio_h = (config.monitor_w * img_h) / img_w

    if (ratio_h < config.monitor_h):
        # Use horizontal black bars
        transform_y = ratio_h
        transform_x = config.monitor_w
        offset_y = (config.monitor_h - ratio_h) / 2
        offset_x = 0
    elif (ratio_h > config.monitor_h):
        # Use vertical black bars
        transform_x = (config.monitor_h * img_w) / img_h
        transform_y = config.monitor_h
        offset_x = (config.monitor_w - transform_x) / 2
        offset_y = 0
    else:
        # No need for black bars as photo ratio equals screen ratio
        transform_x = config.monitor_w
        transform_y = config.monitor_h
        offset_y = offset_x = 0
    return ((transform_x, transform_y), (offset_x, offset_y))


def show_image(screen, image):
    if isinstance(image, str):
        image = pygame.image.load(image)
    screen.fill((0, 0, 0))
    dims, offset = get_dims_and_offset(image.get_width(), image.get_height())
    image = pygame.transform.scale(image, dims)
    screen.blit(image, offset)
    pygame.display.flip()


def take_photos(camera, n_photos):
    # return mock_take_photos(n_photos)
    
#    camera.color_effects = (128,128)
    camera.hflip = False  # mirror image preview
    camera.start_preview()
    time.sleep(config.prev_delay_s)

    streams = [BytesIO() for _ in xrange(n_photos)]
    camera.capture_sequence(outputs=streams, format='gif')

    camera.stop_preview()
#    camera.close()
    for stream in streams:
        stream.seek(0)

    logging.debug('got image(s)')
    return streams


def loop(screen, bg_thread):
    NEXTFRAME = USEREVENT + 1  # custom pygame event ID
    gif_frame_delay = config.frame_duration_ms  # set to something else if you want
    clock = pygame.time.Clock()

    current_gif_frame = 0
    first_frame = True
    display_frames = []

    camera = picamera.PiCamera()
    camera.vflip = False
    camera.hflip = True
    camera.iso = 400
    camera.resolution = (204, 272)
    camera.brightness = 50
    camera.contrast = 50
  #  camera.shutter_speed = 800

    while True:
        events = pygame.event.get()
        check_input(events, bg_thread)

        if bg_thread.done.is_set():
            pygame.time.set_timer(NEXTFRAME, 0)  # remove frame display event triggers
            pygame.event.clear()
            bg_thread.done.clear()
            qr_stream = bg_thread.upload_q.get_nowait()
            show_image(screen, pygame.image.load(qr_stream).convert())
#           show_image(screen, real_path + "/code.png")
            time.sleep(config.done_delay_s)
            show_image(screen, real_path + "/intro.png")
            continue
        elif not bg_thread.processing.is_set():
            # wait for button press, then start
            GPIO.wait_for_edge(btn_pin, GPIO.FALLING)
#            while not pygame.key.get_pressed()[K_SPACE]:
#                check_input(pygame.event.get(), bg_thread)
            first_frame = True
            display_frames = []
            logging.debug('Get ready')
            show_image(screen, real_path + "/instructions.png")
            time.sleep(config.prep_delay_s)
            screen.fill( (0,0,0) )
            pygame.display.flip()
            photos = take_photos(camera, bg_thread.gifmaker.n_photos)
            logging.debug('putting photos')
            show_image(screen, real_path + "/processing.png")
            bg_thread.input_q.put_nowait(photos)
            bg_thread.processing.set()
        elif not bg_thread.upload.is_set():
            # check for processed frames
            try:
                frame = bg_thread.frame_q.get_nowait()
                pygame_frame = bg_thread.gifmaker.make_pygame_frame(frame)
                display_frames.append(pygame_frame)
                if first_frame:
                    first_frame = False
                    current_gif_frame = 0
                    # start recurring pygame event for manually displaying gif frames
                    pygame.time.set_timer(NEXTFRAME, gif_frame_delay)
                    show_image(screen, pygame_frame)
            except QueueEmpty:
                pass

            # check for processed gif
            n_frames = len(display_frames)
            if n_frames == config.n_frames:
                try:
                    gif = bg_thread.gif_q.get_nowait()
                    logging.debug('got gif, flagging for upload')
                    bg_thread.upload.set()
                except QueueEmpty:
                    pass

        # display next frame of the animation
        n_frames = len(display_frames)
        if n_frames > 1 and any(e.type == NEXTFRAME for e in events):
            current_gif_frame = (current_gif_frame + 1) % n_frames
            show_image(screen, display_frames[current_gif_frame])

        clock.tick(1000.0/gif_frame_delay)

def main():
    # pygame setup
    pygame.init()
    screen = pygame.display.set_mode((config.monitor_w, config.monitor_h), pygame.DOUBLEBUF | pygame.HWSURFACE)
    pygame.display.set_caption('Photobooth')
    pygame.mouse.set_visible(False)  # hide the mouse cursor
    pygame.display.toggle_fullscreen()

    # thread setup
    # can't put gifmaker class setting in config without circular import problems unless we restructure stuff
    # Use WandGIFMaker if you want to use ImageMagick instead of PIL
#    GIFMAKER_CLASS = PILGIFMaker
    GIFMAKER_CLASS = WandGIFMaker
    bg_thread = BoothBackgroundThread(Queue(), Queue(), Queue(), Queue(), gifmaker_cls=GIFMAKER_CLASS)
    bg_thread.start()

    logging.debug('Running')
    show_image(screen, real_path + "/intro.png")
    time.sleep(config.init_delay_s)

    loop(screen, bg_thread)


if __name__ == '__main__':
    # GPIO setup
    btn_pin = 18
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(btn_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
#    time.sleep(config.debounce) #debounce
    # bind cleanup handler
    atexit.register(cleanup)

    main()
