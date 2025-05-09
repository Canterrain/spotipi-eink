import time
import sys
import logging
from logging.handlers import RotatingFileHandler
import spotipy
import spotipy.util as util
import os
import traceback
import configparser
import requests
import signal
import random
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter

# Recursion limiter to avoid infinite loops in _get_song_info()
def limit_recursion(limit):
    def inner(func):
        func.count = 0
        def wrapper(*args, **kwargs):
            func.count += 1
            if func.count < limit:
                result = func(*args, **kwargs)
            else:
                result = None
            func.count -= 1
            return result
        return wrapper
    return inner

class SpotipiEinkDisplay:
    def __init__(self, delay=1):
        # Handle system signals
        signal.signal(signal.SIGTERM, self._handle_sigterm)

        self.delay = delay
        self.config = configparser.ConfigParser()
        # Reads ../config/eink_options.ini relative to this Python file's location
        self.config.read(os.path.join(os.path.dirname(__file__), '..', 'config', 'eink_options.ini'))

        # ---------------------------------------------------------------------
        # "idle" features
        # ---------------------------------------------------------------------
        self.idle_mode = self.config.get('DEFAULT', 'idle_mode', fallback='cycle')
        self.idle_display_time = self.config.getint('DEFAULT', 'idle_display_time', fallback=300)
        self.idle_shuffle = self.config.getboolean('DEFAULT', 'idle_shuffle', fallback=False)
        self.idle_folder = os.path.join(os.path.dirname(__file__), '..', 'config', 'idle_images')
        self.default_idle_image = self.config.get('DEFAULT', 'no_song_cover')
        self.idle_images = self._load_idle_images()
        self.idle_index = 0

        # ---------------------------------------------------------------------
        # Logging
        # ---------------------------------------------------------------------
        logging.basicConfig(
            format='%(asctime)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            filename=self.config.get('DEFAULT', 'spotipy_log'),
            level=logging.INFO
        )
        logger = logging.getLogger('spotipy_logger')
        handler = RotatingFileHandler(
            self.config.get('DEFAULT', 'spotipy_log'),
            maxBytes=2000,
            backupCount=3
        )
        logger.addHandler(handler)
        self.logger = logger
        self.logger.info('Logger test: initialization complete')

        # A more verbose console logger
        self.logger = self._init_logger()
        self.logger.info('Service instance created')

        # ---------------------------------------------------------------------
        # Set up display model
        # ---------------------------------------------------------------------
        if self.config.get('DEFAULT', 'model') == 'inky':
            from inky.auto import auto
            from inky.inky_uc8159 import CLEAN
            self.inky_auto = auto
            self.inky_clean = CLEAN
            self.logger.info('Loading Pimoroni Inky library')
        elif self.config.get('DEFAULT', 'model') == 'waveshare4':
            from lib import epd4in01f
            self.wave4 = epd4in01f
            self.logger.info('Loading Waveshare 4" library')

        # Track previous song and how many times we've refreshed
        self.song_prev = ''
        self.pic_counter = 0

    def _init_logger(self):
        """
        Creates a console logger at DEBUG level and attaches it
        to the 'spotipy_logger' we set up above.
        """
        logger = logging.getLogger('spotipy_logger')
        logger.setLevel(logging.DEBUG)
        stdout_handler = logging.StreamHandler()
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.setFormatter(logging.Formatter('Spotipi eInk Display - %(message)s'))
        logger.addHandler(stdout_handler)
        return logger

    def _handle_sigterm(self, sig, frame):
        self.logger.warning('SIGTERM received, stopping')
        sys.exit(0)

    def _load_idle_images(self):
        """Load all valid image files from the idle folder for shuffle/cycle."""
        images = []
        try:
            if os.path.isdir(self.idle_folder):
                for f in os.listdir(self.idle_folder):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                        images.append(os.path.join(self.idle_folder, f))
        except Exception as e:
            self.logger.error(f"Failed to load idle images: {e}")
            self.logger.error(traceback.format_exc())
        return images

    def _get_idle_image(self):
        """
        Returns an idle image according to idle_mode and idle_shuffle:
          - If no images are found, returns the default image.
          - If shuffle is True, picks randomly.
          - Otherwise cycles through the list in order.
        """
        if not self.idle_images:
            return Image.open(self.default_idle_image)

        if self.idle_shuffle:
            return Image.open(random.choice(self.idle_images))
        else:
            img_path = self.idle_images[self.idle_index]
            self.idle_index = (self.idle_index + 1) % len(self.idle_images)
            return Image.open(img_path)

    def _break_fix(self, text: str, width: int, font: ImageFont, draw: ImageDraw):
        """
        Break a string into lines so that each line does not exceed 'width'.
        """
        if not text:
            return
        if isinstance(text, str):
            text = text.split()
        lo = 0
        hi = len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            t = ' '.join(text[:mid])
            w = int(draw.textlength(text=t, font=font))
            if w <= width:
                lo = mid
            else:
                hi = mid - 1
        t = ' '.join(text[:lo])
        w = int(draw.textlength(text=t, font=font))
        yield t, w
        yield from self._break_fix(text[lo:], width, font, draw)

    def _fit_text_top_down(
        self, img: Image, text: str, text_color: str, shadow_text_color: str,
        font: ImageFont, y_offset: int, font_size: int,
        x_start_offset: int = 0, x_end_offset: int = 0,
        offset_text_px_shadow: int = 0
    ) -> int:
        """
        Draw text from top to bottom, wrapping as needed, and return the height used.
        """
        width = img.width - x_start_offset - x_end_offset - offset_text_px_shadow
        draw = ImageDraw.Draw(img)
        pieces = list(self._break_fix(text, width, font, draw))
        y = y_offset
        h_taken_by_text = 0
        for t, _ in pieces:
            if offset_text_px_shadow > 0:
                draw.text((x_start_offset + offset_text_px_shadow, y + offset_text_px_shadow),
                          t, font=font, fill=shadow_text_color)
            draw.text((x_start_offset, y), t, font=font, fill=text_color)
            y += font_size
            h_taken_by_text += font_size
        return h_taken_by_text

    def _fit_text_bottom_up(
        self, img: Image, text: str, text_color: str, shadow_text_color: str,
        font: ImageFont, y_offset: int, font_size: int,
        x_start_offset: int = 0, x_end_offset: int = 0,
        offset_text_px_shadow: int = 0
    ) -> int:
        """
        Draw text from bottom upward, wrapping as needed, and return the height used.
        """
        width = img.width - x_start_offset - x_end_offset - offset_text_px_shadow
        draw = ImageDraw.Draw(img)
        pieces = list(self._break_fix(text, width, font, draw))
        if len(pieces) > 1:
            y_offset -= (len(pieces) - 1) * font_size
        h_taken_by_text = 0
        for t, _ in pieces:
            if offset_text_px_shadow > 0:
                draw.text((x_start_offset + offset_text_px_shadow, y_offset + offset_text_px_shadow),
                          t, font=font, fill=shadow_text_color)
            draw.text((x_start_offset, y_offset), t, font=font, fill=text_color)
            y_offset += font_size
            h_taken_by_text += font_size
        return h_taken_by_text

    def _display_clean(self):
        """
        Clears the display (two passes) for Inky or Waveshare.
        """
        try:
            if self.config.get('DEFAULT', 'model') == 'inky':
                inky = self.inky_auto()
                for _ in range(2):
                    for y in range(inky.height):
                        for x in range(inky.width):
                            inky.set_pixel(x, y, self.inky_clean)
                    inky.show()
                    time.sleep(1.0)
            elif self.config.get('DEFAULT', 'model') == 'waveshare4':
                epd = self.wave4.EPD()
                epd.init()
                epd.Clear()
        except Exception as e:
            self.logger.error(f'Display clean error: {e}')
            self.logger.error(traceback.format_exc())

    def _convert_image_wave(self, img: Image, saturation: int = 2) -> Image:
        """
        Convert an Image to the 7-color format needed by Waveshare 4".
        """
        converter = ImageEnhance.Color(img)
        img = converter.enhance(saturation)
        palette_data = [
            0x00, 0x00, 0x00,   # black
            0xff, 0xff, 0xff,   # white
            0x00, 0xff, 0x00,   # green
            0x00, 0x00, 0xff,   # blue
            0xff, 0x00, 0x00,   # red
            0xff, 0xff, 0x00,   # yellow
            0xff, 0x80, 0x00    # orange
        ]
        palette_image = Image.new('P', (1, 1))
        palette_image.putpalette(palette_data + [0, 0, 0] * 248)
        img.load()
        palette_image.load()
        im = img.im.convert('P', True, palette_image.im)
        return img._new(im)

    def _display_image(self, image: Image, saturation: float = 0.5):
        """
        Shows the Image on the Inky or Waveshare display.
        """
        try:
            if self.config.get('DEFAULT', 'model') == 'inky':
                inky = self.inky_auto()
                inky.set_image(image, saturation=saturation)
                inky.show()
            elif self.config.get('DEFAULT', 'model') == 'waveshare4':
                epd = self.wave4.EPD()
                epd.init()
                epd.display(epd.getbuffer(self._convert_image_wave(image)))
                epd.sleep()
        except Exception as e:
            self.logger.error(f'Display image error: {e}')
            self.logger.error(traceback.format_exc())

    def _gen_pic(self, image: Image, artist: str, title: str, show_small_cover: bool) -> Image:
        """
        Generates the final composite image with the album artwork (or idle image),
        background blur (if configured), and optional text (title/artist).
        'show_small_cover' controls whether we paste a small overlay of 'image'.
        """
        album_cover_small_px = self.config.getint('DEFAULT', 'album_cover_small_px')
        offset_px_left = self.config.getint('DEFAULT', 'offset_px_left')
        offset_px_right = self.config.getint('DEFAULT', 'offset_px_right')
        offset_px_top = self.config.getint('DEFAULT', 'offset_px_top')
        offset_px_bottom = self.config.getint('DEFAULT', 'offset_px_bottom')
        offset_text_px_shadow = self.config.getint('DEFAULT', 'offset_text_px_shadow', fallback=0)
        text_direction = self.config.get('DEFAULT', 'text_direction', fallback='top-down')
        background_blur = self.config.getint('DEFAULT', 'background_blur', fallback=0)

        bg_w, bg_h = image.size

        # Fit or repeat background
        bg_mode = self.config.get('DEFAULT', 'background_mode', fallback='fit')
        if bg_mode == 'fit':
            target_size = (self.config.getint('DEFAULT', 'width'),
                           self.config.getint('DEFAULT', 'height'))
            if bg_w != target_size[0] or bg_h != target_size[1]:
                image_new = ImageOps.fit(image, target_size, centering=(0.0, 0.0))
            else:
                image_new = image.crop((0, 0, target_size[0], target_size[1]))
        elif bg_mode == 'repeat':
            target_w = self.config.getint('DEFAULT', 'width')
            target_h = self.config.getint('DEFAULT', 'height')
            image_new = Image.new('RGB', (target_w, target_h))
            for x in range(0, target_w, bg_w):
                for y in range(0, target_h, bg_h):
                    image_new.paste(image, (x, y))
        else:
            # fallback
            target_size = (self.config.getint('DEFAULT', 'width'),
                           self.config.getint('DEFAULT', 'height'))
            image_new = image.crop((0, 0, target_size[0], target_size[1]))

        # Optional blur: apply only if small artwork is enabled
        if self.config.getboolean('DEFAULT', 'album_cover_small') and background_blur > 0:
            image_new = image_new.filter(ImageFilter.GaussianBlur(background_blur))

        # Paste smaller cover if show_small_cover and config says album_cover_small = True
        if show_small_cover and self.config.getboolean('DEFAULT', 'album_cover_small'):
            cover_smaller = image.resize((album_cover_small_px, album_cover_small_px), Image.LANCZOS)
            album_pos_x = (image_new.width - album_cover_small_px) // 2
            image_new.paste(cover_smaller, (album_pos_x, offset_px_top))

        # Prepare fonts
        font_title = ImageFont.truetype(self.config.get('DEFAULT', 'font_path'),
                                        self.config.getint('DEFAULT', 'font_size_title'))
        font_artist = ImageFont.truetype(self.config.get('DEFAULT', 'font_path'),
                                         self.config.getint('DEFAULT', 'font_size_artist'))

        draw = ImageDraw.Draw(image_new)

        # Render text
        if text_direction == 'top-down':
            # Use the fixed offsets as in the older version
            title_position_y = album_cover_small_px + offset_px_top + 10
            title_height = self._fit_text_top_down(
                img=image_new,
                text=title,
                text_color='white',
                shadow_text_color='black',
                font=font_title,
                font_size=self.config.getint('DEFAULT', 'font_size_title'),
                y_offset=title_position_y,
                x_start_offset=offset_px_left,
                x_end_offset=offset_px_right,
                offset_text_px_shadow=offset_text_px_shadow
            )
            artist_position_y = album_cover_small_px + offset_px_top + 10 + title_height
            self._fit_text_top_down(
                img=image_new,
                text=artist,
                text_color='white',
                shadow_text_color='black',
                font=font_artist,
                font_size=self.config.getint('DEFAULT', 'font_size_artist'),
                y_offset=artist_position_y,
                x_start_offset=offset_px_left,
                x_end_offset=offset_px_right,
                offset_text_px_shadow=offset_text_px_shadow
            )
        elif text_direction == 'bottom-up':
            artist_position_y = image_new.height - (offset_px_bottom + self.config.getint('DEFAULT', 'font_size_artist'))
            artist_height = self._fit_text_bottom_up(
                img=image_new,
                text=artist,
                text_color='white',
                shadow_text_color='black',
                font=font_artist,
                font_size=self.config.getint('DEFAULT', 'font_size_artist'),
                y_offset=artist_position_y,
                x_start_offset=offset_px_left,
                x_end_offset=offset_px_right,
                offset_text_px_shadow=offset_text_px_shadow
            )
            title_position_y = image_new.height - (offset_px_bottom + self.config.getint('DEFAULT', 'font_size_title')) - artist_height
            self._fit_text_bottom_up(
                img=image_new,
                text=title,
                text_color='white',
                shadow_text_color='black',
                font=font_title,
                font_size=self.config.getint('DEFAULT', 'font_size_title'),
                y_offset=title_position_y,
                x_start_offset=offset_px_left,
                x_end_offset=offset_px_right,
                offset_text_px_shadow=offset_text_px_shadow
            )

        return image_new

    def _display_update_process(self, song_request: list):
        """
        Generates and displays the final image. Cleans after 'display_refresh_counter' cycles.
        """
        if song_request:
            # song_request: [song_title, album_url, artist]
            try:
                resp = requests.get(song_request[1], stream=True)
                resp.raise_for_status()
                cover = Image.open(resp.raw)

                # show_small_cover=True for active track
                image = self._gen_pic(
                    cover,
                    artist=song_request[2],
                    title=song_request[0],
                    show_small_cover=True
                )
            except Exception as e:
                self.logger.error(f"Failed to fetch/open album cover: {e}")
                self.logger.error(traceback.format_exc())

                fallback_cover = Image.open(self.default_idle_image)
                image = self._gen_pic(
                    fallback_cover,
                    artist=song_request[2],
                    title=song_request[0],
                    show_small_cover=True
                )
        else:
            # Idle: no text, no small cover
            idle_img = self._get_idle_image()
            image = self._gen_pic(
                idle_img,
                artist="",
                title="",
                show_small_cover=False
            )

        # Clean screen occasionally
        refresh_limit = self.config.getint('DEFAULT', 'display_refresh_counter', fallback=20)
        if self.pic_counter > refresh_limit:
            self._display_clean()
            self.pic_counter = 0

        # Show final image
        self._display_image(image)
        self.pic_counter += 1

    @limit_recursion(limit=10)
    def _get_song_info(self) -> list:
        """
        Returns [song_title, cover_url, artist] or [] if no track.
        """
        scope = 'user-read-currently-playing,user-modify-playback-state'
        username = self.config.get('DEFAULT', 'username')
        token_file = self.config.get('DEFAULT', 'token_file')
        token = util.prompt_for_user_token(username=username, scope=scope, cache_path=token_file)

        if token:
            sp = spotipy.Spotify(auth=token)
            result = sp.currently_playing(additional_types='episode')
            if result:
                try:
                    ctype = result.get('currently_playing_type', 'unknown')
                    if ctype == 'episode':
                        song = result["item"]["name"]
                        artist = result["item"]["show"]["name"]
                        cover_url = result["item"]["images"][0]["url"]
                        return [song, cover_url, artist]
                    elif ctype == 'track':
                        song = result["item"]["name"]
                        # combine all artist names
                        artist = ', '.join(a["name"] for a in result["item"]["artists"])
                        cover_url = result["item"]["album"]["images"][0]["url"]
                        return [song, cover_url, artist]
                    elif ctype == 'ad':
                        # Spotify ad playing
                        return []
                    elif ctype == 'unknown':
                        time.sleep(0.01)
                        return self._get_song_info()
                    self.logger.error(f"Unsupported currently_playing_type: {ctype}")
                    return []
                except TypeError:
                    self.logger.error("TypeError from Spotipy, retrying...")
                    time.sleep(0.01)
                    return self._get_song_info()
            else:
                # None -> no track playing
                return []
        else:
            self.logger.error(f"Error: Can't get token for {username}")
            return []

    def start(self):
        """
        Main loop: polls Spotify for current track, or idle if none.
        """
        self.logger.info('Service started')
        self._display_clean()

        try:
            while True:
                try:
                    song_request = self._get_song_info()
                    self.logger.debug(f"Song info returned: {song_request}")
                    if song_request:
                        new_song_key = song_request[0] + song_request[1]
                        if self.song_prev != new_song_key:
                            self.logger.info(f"New song detected: {song_request[0]} by {song_request[2]}")
                            self.song_prev = new_song_key
                            self._display_update_process(song_request)
                    else:
                        self.logger.info("No track detected - switching to idle image.")
                        self.song_prev = 'NO_SONG'
                        self._display_update_process([])

                        # Instead of a long sleep, break the idle wait into increments
                        self.logger.debug(f"Entering idle sleep mode: up to {self.idle_display_time} seconds, polling every 5 seconds")
                        sleep_increment = 5
                        elapsed = 0
                        while elapsed < self.idle_display_time:
                            time.sleep(sleep_increment)
                            elapsed += sleep_increment
                            if self._get_song_info():
                                self.logger.info("Track detected during idle sleep; breaking idle sleep early.")
                                break
                        continue  # Skip the usual delay
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}")
                    self.logger.error(traceback.format_exc())

                time.sleep(self.delay)

        except KeyboardInterrupt:
            self.logger.info("Service stopping via KeyboardInterrupt")
            sys.exit(0)


if __name__ == "__main__":
    service = SpotipiEinkDisplay()
    service.start()
