# 🚁 ArduPilot Workshop

<div align="center">

![ArduPilot](https://img.shields.io/badge/ArduPilot-SITL-blue?style=for-the-badge&logo=drone&logoColor=white)
![Python](https://img.shields.io/badge/Python-3-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-Compatible-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Windows](https://img.shields.io/badge/Windows-Compatible-0078D6?style=for-the-badge&logo=windows&logoColor=white)

</div>

## 📖 Overview

Welcome to the **ArduPilot Workshop**! You fly a simulated ArduPilot plane over Volos from a web Ground Control Station (GCS), and you teach it new tricks in Python with DroneKit: take off, fly to points, fly missions, and finally hunt landmarks to photograph in a game against everyone else in the room.

The planes run on the organisers' laptops, so **all you need is Python**. You don't have to install ArduPilot or Docker.

### ✨ What You'll Learn
- ✈️ **Flight modes, arming and takeoff** of an ArduPilot plane
- 🧭 **Flying with code**: going to points, missions, bearings and distances
- 📸 **Writing your own strategy** for the photo game, as buttons in your GCS
- 🗺️ **How a GCS talks to a drone** (MAVLink, through DroneKit)

---

# Setup and start

All you need is a laptop with **Windows** or **Linux** and an internet connection. Paste one line into a terminal:

**Windows** (open **PowerShell** from the Start menu):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.ps1 | iex"
```

**Linux:**
```bash
curl -LsSf https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.sh | sh
```

It gets everything the GCS needs into **`ardupilot-workshop` in your home folder** (its own Python too, so it doesn't matter which Python you have, or whether you have one), starts the GCS and opens it in your browser. Leave its window open: closing it stops the GCS. On Linux it also gets a small plane simulator (SITL) for your laptop, in case the organisers' planes can't be reached.

**Run it again whenever you like**, e.g. to start the GCS the next day: it only does what is still missing, and never touches your code. Once it's installed you can also start it from the folder: double-click `setup\start.bat` (Windows) or run `sh ~/ardupilot-workshop/setup/start.sh` (Linux).

Then:

1. **Your name and the game server.** At the top of `web-gcs/backend/workshop.py` (the setup prints where it is), fill in `PILOT_NAME` (short, different from everyone else's) and `GAME_SERVER_URL` (we write it on the board). Leave `SITL_ADDRESS` empty.

2. In the GCS page ([http://localhost:5000](http://localhost:5000)), click **Connect**. The game server starts a plane for you (a few seconds the first time), and it stays yours for the whole workshop. The arrow next to Connect chooses which plane: **Server plane** (this one) or **Local SITL** (one on your own laptop, see below); your choice is remembered.

From here on, follow [`web-gcs/CHEATSHEET.md`](web-gcs/CHEATSHEET.md) part by part. [`web-gcs/README.md`](web-gcs/README.md) has more on the GCS and on the game server.

> Saving `workshop.py` restarts the backend, and the page reconnects by itself. If the file has a mistake, the page says on which line; fix it and save.

## Setting it up by hand

If the line above doesn't work for you, with **Python 3** installed (on Windows from [python.org](https://www.python.org/downloads/), ticking **"Add python.exe to PATH"**; on Debian/Ubuntu also `sudo apt install python3-venv`):

```bash
git clone https://github.com/starbound-team/ardupilot-workshop.git   # or download the ZIP from GitHub and unpack it
cd ardupilot-workshop/web-gcs/backend
python3 -m venv venv                                   # Windows: python -m venv venv
venv/bin/python -m pip install -r requirements.txt     # Windows: venv\Scripts\python -m pip install -r requirements.txt
venv/bin/python app.py                                 # Windows: venv\Scripts\python app.py
```

Then open [http://localhost:5000](http://localhost:5000). Calling the venv's own Python like this means you never need to "activate" the venv (which PowerShell refuses by default).

---

# Fallback: running your own plane (SITL)

Only needed if the game server can't give you a plane, or to practise at home. Choose **Local SITL** with the arrow next to **Connect** (it's the default when `GAME_SERVER_URL` is empty). Connect then uses a SITL started with `sim_vehicle.py` if one is running; otherwise it starts one itself, if it finds ArduPilot with the plane built (it looks in `$ARDUPILOT_DIR`, next to `sim_vehicle.py` on your PATH, `~/.ardupilot/ardupilot` and `~/ardupilot`). A plane Connect started itself can also be put down at your start position when a round begins. There are two ways to get ArduPilot: Docker (easier, especially on Windows) or a native ArduPilot build (Linux).

## With Docker

**Install Docker:** follow the [Docker Engine Install Guide](https://docs.docker.com/engine/install/) for your distribution, then let your user run it without `sudo`:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

On Arch-based distributions:
```bash
sudo pacman -S docker
sudo usermod -aG docker $USER
newgrp docker
sudo systemctl enable docker
sudo systemctl start docker
```

**On Windows:**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Enable host networking: Docker Desktop settings → **Resources** → **Network** → **Enable host networking**.
3. Install [VcXsrv](https://sourceforge.net/projects/vcxsrv/) (it shows the SITL map and console windows), and start XLaunch with:
   - Multiple windows
   - Display number: -1
   - Start no client
   - Disable access control

**Start the container:**

Linux:
```bash
xhost +local:
docker run --rm -it --name ardupilot-sitl --net=host -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix -u "$(id -u):$(id -g)" manraf/ardupilot-sb:latest bash
```

Windows, CMD:
```cmd
docker run --rm -it ^
  --name ardupilot-sitl ^
  --net=host ^
  -e DISPLAY=host.docker.internal:0.0 ^
  -u "1000:1000" ^
  manraf/ardupilot-sb:latest ^
  bash
```

Windows, PowerShell:
```powershell
docker run --rm -it `
  --name ardupilot-sitl `
  --net=host `
  -e DISPLAY="host.docker.internal:0.0" `
  -u "1000:1000" `
  manraf/ardupilot-sb:latest `
  bash
```

A second terminal into the same container: `docker exec -it ardupilot-sitl bash`

**Start the plane**, inside the container, at the workshop field in Volos:
```bash
sim_vehicle.py -v plane -l 39.360886,22.945749,0,0 --console --map
```
> **TODO (image):** the image's `/ardupilot/workshop/run.sh` still starts a copter. Until the image is updated, use the command above; the first run may need to build the plane, which takes a few minutes.

## Native (Linux)

Clone ArduPilot:
```bash
git clone https://github.com/ArduPilot/ardupilot.git --recurse-submodules
cd ardupilot
```

Install its prerequisites with the script in `Tools/environment_install` that matches your distribution:
```bash
# Ubuntu and Ubuntu-based
Tools/environment_install/install-prereqs-ubuntu.sh
. ~/.profile
# Arch
Tools/environment_install/install-prereqs-arch.sh
```

Build the plane:
```bash
./waf configure --board sitl
./waf plane
```

Start it, the first time with `-w` (wipes the saved parameters), afterwards without:
```bash
cd Tools/autotest/
python sim_vehicle.py -w -v plane -l 39.360886,22.945749,0,0 --console --map
```

`-l` places the plane at the workshop field in Volos; its last number is the direction the runway points (0 = north). Without it SITL starts in Australia, and the workshop's landmarks are in Greece.

---

# Troubleshooting

**The setup stops with `[!!]`**
The line above it says what went wrong. Most often the internet dropped: run it again, it carries on from where it stopped. "Another program is using port 5000" usually means a GCS is already running in another window.

**`python` isn't found, or opens the Microsoft Store (Windows, setting up by hand)**
Python wasn't added to PATH. Use `py` instead of `python` in the commands above (e.g. `py -m venv venv`), or reinstall Python with **"Add python.exe to PATH"** ticked.

**`No module named venv` / `ensurepip is not available` (Debian/Ubuntu, setting up by hand)**
Install `python3-venv` (`sudo apt install python3-venv`), delete the half-made `venv` folder and make it again.

**The page doesn't load, or says "The backend isn't answering"**
The terminal running `app.py` was closed or the backend crashed: its last lines say why. Start it again; an open page reconnects by itself.

**Connect takes long, then fails**
With **Server plane** chosen, Connect keeps asking the game server for about a minute and a half before it gives up (the toasts say what it's waiting for). Check `GAME_SERVER_URL` against the board, check the board's address opens in your browser, and tell an organiser. To fly anyway, choose **Local SITL** with the arrow next to Connect.

**The map and console windows don't open (Docker)**
- Linux: if `xhost +local:` fails with "command not found", install it (`sudo pacman -S xorg-xhost` on Arch, `sudo apt install x11-xserver-utils` on Debian/Ubuntu), run it again, then start the container.
- Windows: XLaunch must already be running, with "Disable access control" ticked, before you run `docker run`. If you closed it, start it again and restart the container.

**Your own plane starts in Australia**
SITL was started without the workshop location. Add `-l 39.360886,22.945749,0,0` to `sim_vehicle.py`.
