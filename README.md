# Ardupilot-Workshop
This is our ardupilot workshop repository. Have fun!

# Sitl instillation steps:

***Clone the repository from the official ArduPilot github***
```bash
git clone https://github.com/ArduPilot/ardupilot.git --recurse-submodules
```

***Setup the virtual environment***

*Navigate to the clone repositor, then Tools/environment_install, and execute the script that matches your distro*

For example on ubuntu (and ubuntu-based distros):
```bash
bash install-prereqs-ubuntu.sh
. ~/profile
```
On arch
```bash
bash install-prereques-arch.sh
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
