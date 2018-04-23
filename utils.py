import logging
import paramiko
import pyqrcode
import config
import png
import time
import os
from itertools import izip_longest
from io import BytesIO
from threading import Event


def grouper(n, iterable, fillvalue=None):
    """ iterate iterable in chunks of n, padding if necessary """
    args = [iter(iterable)] * n
    return izip_longest(fillvalue=fillvalue, *args)

def upload(stream, server, user, path, path_qr):
    
    """ Upload a byte stream as a file to user@server:path via stfp """
    ssh = paramiko.SSHClient() 
    qr_stream = BytesIO()
#    qrcode = pyqrcode.create(booth.path_lnk, error='L', mode='binary')


    qrcode = pyqrcode.create(path_qr, error='L', mode='binary')


 #   qrcode = pyqrcode.create(config.upload_qr_url.format(time.strftime(config.upload_ts_fmt)), error='L', mode='binary')





    qrcode.png(qr_stream, scale=6)  # write png to the BytesIO stream
#   qr_code.png('code.png', scale=6) 
    qr_stream.seek(0)  # rewind the stream
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#   ssh.load_host_keys(os.path.expanduser(os.path.join("~", ".ssh", "known_hosts")))
    ssh.load_host_keys('/home/pi/.ssh/known_hosts')
    ssh.connect(server, username=user)
    sftp = ssh.open_sftp()
    sftp.putfo(stream, path)  # assumes the stream is at the start or wherever the user intended
    logging.debug('Uploaded {}'.format(path))
    sftp.close()
    ssh.close()
    return qr_stream  # return a reference to the stream so we can use it in booth.py


def _set_or_clear_with_callbacks(set_or_clear, callbacks):
    """ Helper for AnyEvent class """
    set_or_clear()
    for callback in callbacks:
        callback()


class AnyEvent(object):
    """ Class wrapping an event to allow waiting for any one of several events """

    def __init__(self, *events):
        self.events = events
        self._event = Event()
        self._bind()
        self._changed()

    def _bind(self):
        for e in self.events:
            e._set = getattr(e, '_set', e.set)
            e._clear = getattr(e, '_clear', e.clear)
            e._callbacks = getattr(e, '_callbacks', set())
            e._callbacks.add(self._changed)
            e.set = lambda o=e: _set_or_clear_with_callbacks(o._set, o._callbacks)
            e.clear = lambda o=e: _set_or_clear_with_callbacks(o._clear, o._callbacks)

    def _unbind(self):
        for e in self.events:
            e._callbacks.pop(self._changed)

    def _changed(self):
        if any(e.is_set() for e in self.events):
            self.set()
        else:
            self.clear()

    def set(self):
        self._event.set()

    def clear(self):
        self._event.clear()

    def is_set(self):
        return self._event.is_set()

    def isSet(self):
        return self.is_set()

    def wait(self, timeout=None):
        return self._event.wait(timeout)

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        self._unbind()


# Utils for desktop testing only
def _load_photo(filename):
    """ Return an image file as a bytestream """
    with open(filename, 'rb') as f:
        return BytesIO(f.read())  # do this because the Pi Camera writes to a stream


def mock_take_photos(n_photos):
    """ Fake taking photos by loading from file """
    for n in xrange(n_photos):
        yield _load_photo('test_pics/{:02d}.jpg'.format(n+1))
