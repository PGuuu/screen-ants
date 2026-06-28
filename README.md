# 🐜 Interactive Screen Ants

A playful desktop companion for Windows. When your mouse sits idle, a colony of ants
marches out from a nest in the corner of your screen, "discovers" your desktop icons and
the mouse cursor, swarms them, and carries them back home. A giant **queen** periodically
emerges to forage. Move the mouse and the whole colony instantly scatters away.

It runs as a transparent, click‑through overlay, so it never gets in the way of your work —
the ants live *on top of* your screen but every click passes straight through to whatever is
underneath.

> Not a real Windows screensaver (`.scr`) — it's a lightweight always‑available overlay you
> start and stop from a small control panel.

---

## ✨ Features

- **Idle‑activated colony** — ants appear after a configurable idle delay and vanish the moment you move the mouse.
- **Believable ant behaviour** — green scout ants recruit red workers, who surround items and haul them to the nest with steady, frame‑rate‑independent motion.
- **The Queen** — a giant queen comes out to eat food the workers deliver, and on a timer she charges out herself to forage a colourful chunk of your screen, hauling it home with a squad of workers at 1.5× speed.
- **Irregular soil anthill** in the corner that the ants emerge from.
- **Customisable colours** — pick the worker, scout and queen colours from the control panel.
- **Tunable** — idle delay and queen interval via the control panel; movement speed, turn rate, nest size and more via constants at the top of the source.

## 📥 Install (no Python needed)

1. Download **`ScreenAnts.exe`** from the [latest release](../../releases/latest).
2. Put it anywhere (e.g. your Desktop) and double‑click it.
3. The **Control Center** opens — pick your colours/timings and click **Start / Apply**.
4. Leave the mouse still for a couple of seconds and the ants appear. Move it to make them scatter; open the Control Center again and click **Stop** to turn them off.

Settings are saved to a `config.json` next to the exe.

## 🛠️ Run from source

Requires Python 3.9+ on Windows.

```bash
pip install -r requirements.txt
python screen_ants.py          # opens the control panel
```

The control panel's **Start** button launches the overlay (`ants_screensaver.py`).

## ⚙️ Configuration

From the **Control Center**:

| Setting | What it does |
|---|---|
| Start Idle Delay | Seconds of mouse stillness before the ants appear |
| Queen Outing Time | How often the queen charges out to forage (min 15 s) |
| Worker / Scout / Queen Color | Colour theme for each ant type |

For finer tuning, edit the knobs at the top of `ants_screensaver.py`:
`SPEED_SCALE`, `TURN_SPEED`, `NEST_SIZE`, `QUEEN_SPEED_MULT`, `QUEEN_FOOD_SIZE`, `QUEEN_FOLLOWERS`.

## 🧰 Build the exe yourself

```bash
pip install pyinstaller -r requirements.txt
pyinstaller --onefile --windowed --name ScreenAnts --icon ant.ico --add-data "ant.ico;." screen_ants.py
```

The exe is produced in `dist/ScreenAnts.exe`.

## 📄 License

[MIT](LICENSE) — free to use, modify and share.
