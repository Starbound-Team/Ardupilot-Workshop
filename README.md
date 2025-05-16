# Ardupilot-Workshop
This is our ardupilot workshop repository. Have fun!

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
