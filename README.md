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
yay -Syy docker
sudo usermod -aG docker $USER
newgrp docker
sudo systemctl enable docker
sudo systemctl start docker
```

**For Windows:**

---

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
xhost +
docker run --rm -it --name ardupilot-sitl --net=host -e DISPLAY=$DISPLAY -v /.X11-unix:/tmp/.X11-unix -u "$(id -u):$(id -g)" manraf/ardupilot-sb:latest bash
```

**Windows:**

CMD:
```cmd
docker run --rm -it ^
  --name ardupilot-sitl ^
  --net=host ^
  -e DISPLAY=host.docker.internal:0.0 ^
  -v /.X11-unix:/tmp/.X11-unix ^
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
  -v /.X11-unix:/tmp/.X11-unix `
  -u "1000:1000" `
  manraf/ardupilot-sb:latest `
  bash
```

# Connecting to the Docker container
```bash
docker exec -it ardupilot-sitl bash
```

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
. ~/profile
```
On arch
```bash
bash install-prereqs-arch.sh
```

***Configure the board and the vehicle type (Navigate to the initial directory first)***
```bash
./waf configure --board CubeOrangePlus
./waf copter
```

***Run the simulation***

For the first time:
```bash
cd Tools/autotest/
python sim_vehicle.py -w -v copter --console --map
```
To run subsequently, avoid the -w flag as it is not needed
