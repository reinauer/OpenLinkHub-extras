# OpenLinkHub extras

Small, standalone tools that control an existing [OpenLinkHub](https://github.com/jurkovic-nikola/OpenLinkHub) installation through its local HTTP API. They are not an official OpenLinkHub plugin system and do not access hardware directly.

Everything here uses Python's standard library. Install Python 3 and run OpenLinkHub with its API available at `http://127.0.0.1:27003` (the default).

## Included tools

| Tool | Purpose |
| --- | --- |
| `load-lcd/openlinkhub_load_lcd.py` | Switches an AIO LCD image at high/low 1-minute system-load thresholds, with optional RGB changes. |
| `titan_heartbeat.py` | Pulses an OpenLinkHub device's brightness. It is primarily a diagnostic/demo tool for supported NVIDIA GPU lighting, with an optional throttled system-service example. |

## Load-driven LCD automation

The LCD tool uploads two images, sets the LCD to image mode, then switches image and optional RGB state only when the load state changes. It uses hysteresis: `high_threshold` enters the high state, while `low_threshold` returns to the low state.

1. Place the repository where the user service expects it (or adjust the unit below):

   ```bash
   git clone <your-OpenLinkHub-extras-repository-url> ~/.local/share/OpenLinkHub-extras
   ```

2. Create and edit your local configuration:

   ```bash
   mkdir -p ~/.config/openlinkhub-extras
   cp ~/.local/share/OpenLinkHub-extras/config/load-lcd.example.json \
      ~/.config/openlinkhub-extras/load-lcd.json
   ${EDITOR:-nano} ~/.config/openlinkhub-extras/load-lcd.json
   ```

   Replace `device_id` and both image paths. Get the device ID from the OpenLinkHub dashboard or `curl -s http://127.0.0.1:27003/api/devices/`.

3. Test the configuration once. This still performs the selected initial LCD/RGB update, but does not stay running:

   ```bash
   python3 ~/.local/share/OpenLinkHub-extras/load-lcd/openlinkhub_load_lcd.py \
       --config ~/.config/openlinkhub-extras/load-lcd.json --once
   ```

### Configuration notes

- Image filenames must have an alphanumeric stem, such as `water.gif`; OpenLinkHub accepts GIF, JPG/JPEG, WebP, and BMP files up to 5 MiB.
- `fan_channels`, `ring_channels`, and `memory_channels` are comma-separated channel IDs. An empty string enables auto-discovery for fan/memory channels; set `ring_channels` to `none` to leave the LCD ring unchanged.
- The example sets `no_memory_rgb` to `true`, so it works without a memory RGB device. Set it to `false` and provide `memory_device_id` to include memory RGB.
- Set `no_rgb` to `true` to make the tool control only the LCD.
- A host load average is not normalized by CPU count. Choose thresholds for your own machine.
- Command-line options override values in the JSON file. Run `python3 load-lcd/openlinkhub_load_lcd.py --help` for the full option list.

### Run as a system service

OpenLinkHub installations that use the standard `OpenLinkHub.service` should use the two examples in [`systemd/system`](systemd/system). They run as the `openlinkhub` user, require OpenLinkHub to be running, and restart whenever that service restarts.

```bash
sudo git clone https://github.com/reinauer/OpenLinkHub-extras.git /opt/OpenLinkHub-extras
sudo install -d -m 0755 /etc/openlinkhub-extras/images
sudo install -m 0644 /opt/OpenLinkHub-extras/load-lcd/sun.gif /etc/openlinkhub-extras/images/
sudo install -m 0644 /opt/OpenLinkHub-extras/load-lcd/water.gif /etc/openlinkhub-extras/images/
sudo install -m 0644 /opt/OpenLinkHub-extras/config/load-lcd.system.example.json \
    /etc/openlinkhub-extras/load-lcd.json
sudoedit /etc/openlinkhub-extras/load-lcd.json
```

Set your LCD `device_id` in `/etc/openlinkhub-extras/load-lcd.json`. To include memory RGB, set `no_memory_rgb` to `false` and provide its `memory_device_id`. List detected device IDs with:

```bash
curl -s http://127.0.0.1:27003/api/devices/ | jq -r '.devices | keys[]'
```

```bash
sudo install -m 0644 /opt/OpenLinkHub-extras/systemd/system/openlinkhub-load-lcd.service \
    /etc/systemd/system/
sudo install -m 0644 /opt/OpenLinkHub-extras/systemd/system/openlinkhub-titan-heartbeat.service \
    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openlinkhub-load-lcd.service openlinkhub-titan-heartbeat.service
```

Check the services and follow their logs with:

```bash
sudo systemctl status openlinkhub-load-lcd.service openlinkhub-titan-heartbeat.service
sudo journalctl -u openlinkhub-load-lcd.service -u openlinkhub-titan-heartbeat.service -f
```

The TITAN service uses a one-second update interval to limit profile writes. It is included as an example but is not recommended for permanent use with the current native GPU implementation, which saves the device profile for every update. Leave it disabled unless you explicitly want that effect:

```bash
sudo systemctl disable --now openlinkhub-titan-heartbeat.service
```

### Run as a user service

The provided unit assumes the clone and configuration locations used above. If you use another location or Python interpreter, edit its `WorkingDirectory` and `ExecStart` first.

```bash
mkdir -p ~/.config/systemd/user
cp ~/.local/share/OpenLinkHub-extras/systemd/openlinkhub-load-lcd.service \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now openlinkhub-load-lcd.service
systemctl --user status openlinkhub-load-lcd.service
```

View logs with:

```bash
journalctl --user -u openlinkhub-load-lcd.service -f
```

Stop and disable the automation with:

```bash
systemctl --user disable --now openlinkhub-load-lcd.service
```

## TITAN heartbeat demo

`titan_heartbeat.py` repeatedly calls OpenLinkHub's gradual-brightness endpoint. It is useful for short, supervised testing only: its default 50 ms interval makes frequent API calls and causes the active device profile to be updated repeatedly.

```bash
python3 titan_heartbeat.py --device-id nvidiagpu0 --period 5 --interval 0.05
```

Use `Ctrl-C` to stop it. Choose another OpenLinkHub device ID with `--device-id`, or use `--api-url` when the service is not on the default local address.

## License

This repository is available under the [BSD 2-Clause License](LICENSE.md).
