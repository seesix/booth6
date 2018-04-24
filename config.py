monitor_w = 800
monitor_h = 480

photo_w = 240
photo_h = 320

frame_duration_ms = 400
n_frames = 4
photos_per_frame = 4

init_delay_s = 2.5
prep_delay_s = 2
prev_delay_s = 2
done_delay_s = 20

upload_ts_fmt = '%Y-%m-%d:%H:%M:%S'

upload_user = 'indika'
upload_server = 'indika.net'
upload_path_fmt = '/home/indika/webapps/indika/booth/{}-output.gif'
upload_path_lnk = 'http://indika.net/booth/{}-output.gif'
upload_path_qr = 'http://indika.net/booth/{}-output.html'
# upload_path_url = '/home/indika/webapps/indika/booth/output_' + (upload_ts_fmt) + '.html'
upload_path_url  = '/home/indika/webapps/indika/booth/{}-output.html'
upload_qr_url  = 'http://indika.net/booth/{}-output.html'






render_template = '/home/pi/booth6/template.j2'




debounce = 0.3
