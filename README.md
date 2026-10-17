# 🚁 ArduPilot Workshop

<div align="center">

![ArduPilot](https://img.shields.io/badge/ArduPilot-SITL-blue?style=for-the-badge&logo=drone&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-Compatible-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Windows](https://img.shields.io/badge/Windows-Compatible-0078D6?style=for-the-badge&logo=windows&logoColor=white)

</div>

## 📖 Overview

Welcome to the **ArduPilot Workshop** repository! This comprehensive guide provides everything you need to get started with ArduPilot's Software-in-the-Loop (SITL) simulation environment. Whether you're a beginner exploring drone development or an experienced developer testing flight algorithms, this workshop will help you set up and run ArduPilot simulations on your system.

### ✨ What You'll Learn
- 🐳 **Docker-based Setup**: Quick and isolated ArduPilot environment
- 🛠️ **Native Installation**: Direct system installation for advanced users
- 🎮 **SITL Simulation**: Run virtual drone missions without hardware
- 🗺️ **Mission Planning**: Visualize and control your virtual aircraft

---

# Sitl installation steps (docker):

**Official Docker installation guide:**
Refer to the official Docker documentation for your distribution: [Docker Engine Install Guide](https://docs.docker.com/engine/install/)

**Post-installation (all distributions):**
To manage Docker as a non-root user, add your user to the docker group:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

**For Arch-based distributions:**
```bash
sudo pacman -S docker
sudo usermod -aG docker $USER
newgrp docker
sudo systemctl enable docker
sudo systemctl start docker
```

**For Windows:**

Install Docker Desktop: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

Install VcXsrv: [VcXsrv](https://sourceforge.net/projects/vcxsrv/)

Configure VcXsrv to allow access from the Docker container:
1. Start XLaunch with the following options:
   - Multiple windows
   - Display number: -1
   - Start no client
   - Disable access control

2. Enable host networking in Docker Desktop:
   - Open Docker Desktop settings
   - Go to the "Resources" tab
    - Select "Network"
    - Enable "Host networking"
---

# Running the Docker image

**Linux:**
```bash
xhost +local:
docker run --rm -it --name ardupilot-sitl --net=host -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix -u "$(id -u):$(id -g)" manraf/ardupilot-sb:latest bash
```

**Windows:**

CMD:
```cmd
docker run --rm -it ^
  --name ardupilot-sitl ^
  --net=host ^
  -e DISPLAY=host.docker.internal:0.0 ^
  -u "1000:1000" ^
  manraf/ardupilot-sb:latest ^
  bash
```

PowerShell/Terminal:
```powershell
docker run --rm -it `
  --name ardupilot-sitl `
  --net=host `
  -e DISPLAY="host.docker.internal:0.0" `
  -u "1000:1000" `
  manraf/ardupilot-sb:latest `
  bash
```

# Connecting to the Docker container
```bash
docker exec -it ardupilot-sitl bash
```

# Running the simulation (Docker)

Inside the container, start a plane at the workshop field in Volos, where the mission waypoints are:
```bash
sim_vehicle.py -v plane -l 39.360886,22.945749,0,0 --console --map
```
> **TODO (plane branch):** the image's `/ardupilot/workshop/run.sh` still starts a copter. Until the image is updated, use the command above; the first run may need to build the plane, which takes a few minutes.

# Sitl installation steps (native):

***Clone the repository from the official ArduPilot github***
```bash
git clone https://github.com/ArduPilot/ardupilot.git --recurse-submodules
```

***Setup the virtual environment***

*Navigate to the clone repository, then Tools/environment_install, and execute the script that matches your distro*

For example on ubuntu (and ubuntu-based distros):
```bash
bash install-prereqs-ubuntu.sh
. ~/.profile
```
On arch
```bash
bash install-prereqs-arch.sh
```

***Configure the board and the vehicle type (Navigate to the initial directory first)***
```bash
./waf configure --board sitl
./waf plane
```

***Run the simulation***

For the first time:
```bash
cd Tools/autotest/
python sim_vehicle.py -w -v plane -l 39.360886,22.945749,0,0 --console --map
```
To run subsequently, avoid the -w flag as it is not needed

`-l` places the plane at the workshop field in Volos, and its last number is the direction the runway points (0 = north). Without it SITL starts in Australia, and the workshop missions will try to fly to Greece.

# Troubleshooting

**The map and console windows don't open (Docker)**
- Linux: if `xhost +local:` fails with "command not found", install it (`sudo pacman -S xorg-xhost` on Arch, `sudo apt install x11-xserver-utils` on Debian/Ubuntu), run it again, then start the container.
- Windows: XLaunch must already be running, with "Disable access control" ticked, before you run `docker run`. If you closed it, start it again and restart the container.

**The drone starts in Australia, or the simple mission never finishes**
SITL was started without the workshop location. Add `-l 39.360886,22.945749,0,0` to `sim_vehicle.py`.
