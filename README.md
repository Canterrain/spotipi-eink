# Spotipi E-Ink
![spotipi-eink Logo](/images/example.jpg)</br>
Table of Contents
- [Spotipi E-Ink](#spotipi-e-ink)
  - [Overview](#overview)
  - [Getting Started](#getting-started)
  - [Configuration](#configuration)
  - [Supported Hardware](#supported-hardware)
  - [Software](#software)
  - [3D printing](#3d-printing)
    - [Free cases](#free-cases)
    - [None free cases from Pimoroni](#none-free-cases-from-pimoroni)
  - [Show case](#show-case)
## Overview
This project displays album artwork and song info on a 4", 5.7" or 7,3" e-ink display from the Spotify web api.</br>
You can also control Spotify via the 4 Buttons on the Pimoroni Display.</br>

The original concept came from [Ryan Ward ](https://github.com/ryanwa18) and his video: [Youtube Video](https://www.youtube.com/watch?v=uQYIAYa27ds).
Additional work done by [GabbaJoe ](https://github.com/Gabbajoe) accounted for recent OS changes, handled virtual environments, and added button controlls. 
This version adds GPIO dependencies for button controls, changes button 4 to handle playlist functionality, and automatically accounts for recent updates to Raspberry Pi OS GPIO Kernel Module changes, without additional manual steps required. By default this version turns small artwork off.

Button functions:
* Button A - next track
* Button B - previous track
* Button C - play/pause
* Button D - switch playlist

I recommend a Raspberry Pi Zero 2 with GPIO pins, which is both powerful enough to run the project and small enough to make a sleek final product.

The display refresh time is ~30 seconds.

## Getting Started
* Create a new application within the [Spotify developer dashboard](https://developer.spotify.com/dashboard/applications)
* Edit the settings of the application within the dashboard.
    * Set the redirect to
      ```
      http://127.0.0.1:8888/callback/spotify
      ```

* Download the install script
```
wget https://raw.githubusercontent.com/Canterrain/spotipi-eink/main/setup.sh
```
```
chmod +x setup.sh
```

* Install the software: 
```
bash setup.sh
```

After the spotipi-eink is installed you will have 2 new systemd services:
* spotipi-eink-display.service
* spotipi-eink-buttons.service (only for Pimoroni displays)

These services run as the user you used to execute setup.sh.

You control the services via systemctl **start, stop, status** *(services-name)*. Example get the status of *spotipi-eink-display.service*:
```
spotipi@spotipi:~ $ sudo systemctl status spotipi-eink-display.service
● spotipi-eink-display.service - Spotipi eInk Display service
     Loaded: loaded (/etc/systemd/system/spotipi-eink-display.service; enabled; preset: enabled)
    Drop-In: /etc/systemd/system/spotipi-eink-display.service.d
             └─spotipi-eink-display_env.conf
     Active: active (running) since Tue 2023-10-31 09:30:05 CET; 27min ago
   Main PID: 4108 (python3)
      Tasks: 1 (limit: 383)
        CPU: 5min 13.455s
     CGroup: /system.slice/spotipi-eink-display.service
             └─4108 /home/spotipi/spotipi-eink/spotipienv/bin/python3 /home/spotipi/spotipi-eink/python/spotipiEinkDisplay.py

Oct 31 09:30:05 spotipi systemd[1]: Started spotipi-eink-display.service - Spotipi eInk Display service.
Oct 31 09:30:06 spotipi spotipi-eink-display[4108]: Spotipi eInk Display - Service instance created
Oct 31 09:30:07 spotipi spotipi-eink-display[4108]: Spotipi eInk Display - Loading Pimoroni inky lib
Oct 31 09:30:07 spotipi spotipi-eink-display[4108]: Spotipi eInk Display - Service started
```

## Configuration
In the file **spotipi/config/eink_options.ini** you can modify:
* the displayed *title* and *artist* text size
* the direction of how the title or artist text line break will be done, **top-down** or **bottom-up**
* the offset from display borders
* enable the small album cover
* the size of the small album cover
* the font that will be used

Example config:

```
width = 640
height = 400
album_cover_small_px = 200
; possible values are inky or waveshare4
model = inky
; disable smaller album cover set to False
; if disabled top offset is still calculated like as the following:
; offset_px_top + album_cover_small_px
album_cover_small = False
; cleans the display every 20 picture
; this takes ~60 seconds
display_refresh_counter = 20
username = theRockJohnson
token_file = /home/spotipi/spotipi-eink/config/.cache
spotipy_log = /home/spotipi/spotipi-eink/log/spotipy.log
no_song_cover = /home/spotipi/spotipi-eink/resources/default.jpg
font_path = /home/spotipi/spotipi-eink/resources/CircularStd-Bold.otf
font_size_title = 45
font_size_artist = 35
offset_px_left = 20
offset_px_right = 20
offset_px_top = 0
offset_px_bottom = 20
offset_text_px_shadow = 4
; text_direction possible values: top-down or bottom-up
text_direction = bottom-up
; possible modes are fit or repeat
background_mode = fit
```

# Idle Image Mode
When no song is playing, **Spotipi eInk Display** can show **custom idle images**. Users can choose between **static** and **cycling** idle images.

### Configuration Options:
Modify these settings in **eink_options.ini**:
```
[DEFAULT]
idle_mode = cycle
# Options: static, cycle
idle_display_time = 300
# Time to display each image in seconds (default: 5 minutes)
idle_shuffle = false
# If true, images will be displayed in random order
```

### Idle Image Modes:
- **static** - Displays a **single** idle image (set by `no_song_cover`).
- **cycle** - Rotates through multiple images from the `config/idle_images/` folder.

### How to Add Custom Idle Images:
1. Navigate to the **`config/idle_images/`** folder (create it if it doesn’t exist).
2. Add your images (**PNG, JPG, JPEG** formats supported).
3. If `idle_mode` is set to **cycle**, the display will cycle through all images in this folder.
4. Set `idle_shuffle = true` in `eink_options.ini` to shuffle the images randomly.

### Important Notes:
- If no images are found in `idle_images/`, the **default idle image** (`no_song_cover`) will be used.
- The screen refresh rate is controlled by `idle_display_time` (default: **5 minutes**).
- If music starts playing, the display **automatically** switches back to album art.


## Supported Hardware
* [Raspberry Pi Zero 2](https://amzn.to/4haKmgW)) (affiliate)
* [Pimoroni Inky Impression 4"](https://collabs.shop/p3uwlu) (affiliate)
* [Waveshare 4.01inch ACeP 7-Color E-Paper E-Ink Display HAT](https://amzn.to/409zZny) (affiliate)
* [Pimoroni Inky Impression 5.7"](https://collabs.shop/fmdbjx) (affiliate)
* [Pimoroni Inky Impression 7.3"](https://collabs.shop/cc4wfy) (affiliate)


## 3D Printed Case
A free STL for a case that fits the Pimoroni 5.7 display and Raspberry Pi is here:
[Free STL](https://makerworld.com/en/models/713543#profileId-644007)
It's a friction fit print, and no additional hardware is needed to snap everything together, this even includes buttons.

Here's a few examples of the final print and product put together:
![spotipi-eink Logo](/images/example.jpg)
![spotipi-eink Logo](/images/example2.jpg)


## Software
* [Raspberry Pi Imager](https://www.raspberrypi.com/software/)


With the latest Raspberry PI OS **Bookworm** */var/log/syslog* is no longer an option for logs. Instead, you have to use *journalctl*. To view the *spotipi-eink-display.service* and *spotipi-eink-buttons.service* logs use the following command:

```
# see all time logs
journalctl -u spotipi-eink-display.service -u spotipi-eink-buttons.service
```
or
```
# see only today logs
journalctl -u spotipi-eink-display.service -u spotipi-eink-buttons.service --since today
```

Spotipi-eink creates its own Python environment due to the fact that Raspberry PI OS **Bookworm** insists on protected environments for Python. See more here:
* [Python on Raspberry Pi](https://www.raspberrypi.com/documentation/computers/os.html#python-on-raspberry-pi)
* [PEP668](https://peps.python.org/pep-0668/)

This should be unnecessary, but if you wish to manually execute the Python script you can load into the Virtual Python environment with the following commands. When in the Virtual Python environment, Terminal will display **(spotipienv)**:
```
cd ~
. spotipi/spotipi-eink/spotipienv/bin/activate
```
Additionally you will need to export the following 3 environment variables on your shell where the spotipy library is working.
```
export SPOTIPY_CLIENT_ID=''
export SPOTIPY_CLIENT_SECRET=''
export SPOTIPY_REDIRECT_URI=''
```
To leave the Virtual Python environment just type: **deactivate**

