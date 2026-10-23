# The workshop's plane simulator in a container: the last fallback, for a laptop where neither the organisers'
# planes nor the setup's own plane work (e.g. a Mac). Just ArduPilot's own ArduPlane 4.7.2 SITL (a static program),
# from the workshop's GitHub release; about 7 MB. Build and run it straight from GitHub:
#   docker build -t workshop-plane https://github.com/starbound-team/ardupilot-workshop.git#main:setup/docker
#   docker run --rm -p 5760:5760 workshop-plane
# then in workshop.py: SITL_ADDRESS = "tcp:127.0.0.1:5760" (that plane isn't moved to a corner: it flies there).
FROM scratch
ADD --chmod=755 https://github.com/starbound-team/ardupilot-workshop/releases/download/sitl-2026-10/arduplane /arduplane
ADD https://github.com/starbound-team/ardupilot-workshop/releases/download/sitl-2026-10/plane.parm /plane.parm
COPY start.parm /start.parm
WORKDIR /plane
EXPOSE 5760
ENTRYPOINT ["/arduplane", "--model", "plane", "--speedup", "1", "-w", "--defaults", "/plane.parm,/start.parm", "-I0"]
