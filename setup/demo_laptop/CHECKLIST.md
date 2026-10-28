# Coconut VTOL demo laptop: setup and demo-day checklist

Unzip this folder anywhere (e.g. the Desktop) and double-click the `.cmd`
files in order. Each one opens a window that says what it is doing and stops
with a clear message if something fails.

| Level | What you can show | Steps | Time |
|---|---|---|---|
| **1. Dashboard** | farm map, ripeness prediction, mission plan + export, phone camera, alerts, a fake aircraft flying, review video | SETUP-1 | 20-30 min |
| **2. Live simulator** | the real ArduPilot autopilot flying the dashboard's plan in JSBSim, battery draining, flight replay + post-flight report | SETUP-1, 2, 3 | + 1.5-2.5 h, mostly unattended |

Level 1 is enough for most demos. Do Level 2 at least a day before.

## Before you start

- Windows 10/11, 15 GB free on C: (5 GB for Level 1 only), plugged in, good Wi-Fi.
- An administrator account on the laptop (Level 2 only; college/company laptops may block WSL).
- The review video: copy `js_demo_v4_review.mp4` onto the laptop separately (not in git).

## Level 1: dashboard

1. Double-click **SETUP-1-dashboard.cmd**.
   - Installs Git, Python 3.13 and Node.js if missing (Windows may ask for permission),
     clones the code into a `vtol-quadcopter` folder next to this folder (or uses the clone
     these scripts are in), installs packages, builds the dashboard.
   - If it stops right after installing a tool, close the window and run it again.
2. Double-click **RUN-demo-fake.cmd**: the dashboard opens at http://localhost:8080 and
   a fake aircraft starts circling the field. Close its window to stop it.
3. The first time the dashboard starts, Windows Firewall asks about Python:
   allow **Private networks** (needed for phones and tablets).

## Level 2: live simulator (optional)

1. Right-click **SETUP-2-wsl.cmd** -> **Run as administrator**. Restart the laptop.
2. After the restart Ubuntu opens and asks for a new username and password.
   Pick any and **remember the password**. Close Ubuntu.
3. Double-click **SETUP-3-simulator.cmd** (1-2 h). It asks for the Ubuntu password once,
   downloads and builds ArduPilot, then flies a 1-minute hover test.
   It ends with `Simulator ready`.
4. Demo: **RUN-demo-with-sim.cmd** flies the plan currently shown on the dashboard
   (~1 min to boot, ~10 min of flight, in real time). Afterwards open **Flights**
   (left rail) for the replay and the post-flight report.

Don't run RUN-demo-fake and RUN-demo-with-sim at the same time (same port).

## Phone camera

- Phone and laptop on the **same Wi-Fi**. College/guest Wi-Fi often blocks
  device-to-device traffic: use a phone hotspot for the laptop instead.
- **Android app (recommended):** install *IP Webcam* (Play Store), tap *Start server*,
  type the address it shows (e.g. `192.168.1.20:8080`) into the dashboard's camera card.
- **Phone browser:** scan the QR code on the camera card. The browser warns about the
  certificate unless you install it on the phone: open `https://<laptop-ip>:8443/ca.crt`,
  then Settings -> Security -> Encryption & credentials -> Install a certificate -> CA certificate.

## Remove the browser warning on the laptop (optional)

The dashboard's https address uses its own certificate. To trust it, run the
`certutil -user -addstore Root ...` command that SETUP-1 printed at the end
(Windows asks you to confirm; check the thumbprint), then close and reopen the browser.
http://localhost:8080 works without this.

## Demo day

- [ ] Power plan: **Never sleep** while plugged in (Settings -> System -> Power).
      Sleep freezes the simulator mid-flight.
- [ ] Laptop plugged in; notifications off (Focus).
- [ ] Phone charged, IP Webcam installed, same Wi-Fi (or hotspot) tested.
- [ ] Do one full run of the demo you will show, on the same network, the day before.
- [ ] Review video copied and plays.
- [ ] Backup: if the simulator misbehaves, show RUN-demo-fake + the video + a
      replay from the Flights panel of an earlier simulator flight.

## Troubleshooting

| Problem | Fix |
|---|---|
| `winget is missing` | Install *App Installer* from the Microsoft Store. |
| A tool installed but "did not install" | Close the window, run the same `.cmd` again. |
| `wsl --install failed` / "virtualization" | Enable virtualization (Intel VT-x / AMD SVM) in the BIOS, then SETUP-2 again. |
| SETUP-3 stopped half way | Run it again: finished steps are skipped. Error log: `~/setup_check.log` in Ubuntu. |
| Dashboard says "port 8080 is busy" | Another copy is running: close the old "Coconut dashboard" window. |
| Phone can't open the dashboard | Same Wi-Fi? Firewall allowed for Private networks? Try a hotspot. |
| Drone doesn't appear with the simulator | Wait 1 min after RUN-demo-with-sim starts; make sure RUN-demo-fake is closed. |

Code: https://github.com/AkineHime/vtol-quadcopter (branch `dashboard-ml-mission-link`).
Details: `ground_station/README.md` and `flight_software/README.md` in the repo.
