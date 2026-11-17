# System Monitor

[简体中文](README.md) ｜ **English**

A real-time monitor that runs entirely on your own machine. It reads system resources
(CPU / GPU / memory / storage / temperatures / top processes), network quality, and —
the part most tools skip — **explains how your hardware is affecting the network,
with evidence**.

Everything is served from a local HTTP server on `127.0.0.1`. No cloud, no telemetry,
no external CDN. The dashboard works even with the internet unplugged.

Bilingual UI (Chinese / English, switchable in the top-right corner) — including the
analysis text, not just the menus. GPU support covers NVIDIA, AMD and Intel.

---

## Quick start

### Option A — just run it (recommended)

1. Download `系统实时监测_v1.6_便携版.zip` from [Releases](../../releases)
2. Unzip anywhere, double-click `系统实时监测.exe`
3. A console window appears — **that is the program**, not an error. Your browser
   opens the dashboard automatically at `http://127.0.0.1:8770/`

Windows SmartScreen may say "Windows protected your PC" because the binary is not
code-signed (a certificate costs more than this tool is worth). Click **More info →
Run anyway**.

### Option B — run from source

```bash
pip install psutil
python server.py                 # default port 8770, opens the browser
python server.py --lang en       # English console output
python server.py --port 9000
python server.py --ping-target 1.1.1.1   # pick a closer probe target
```

**Only dependency: `psutil`.** No framework, no build step, no npm.

### Option C — installer

`系统实时监测_安装包_v1.6.exe` installs per-user to `%LOCALAPPDATA%\Programs`,
adds Start-menu shortcuts, registers a normal uninstaller, and asks once whether you
want the optional temperature component.

---

## What you get

```
Top bar: title · health score ring · live status · theme (dark/light) · language (中/EN)

KPI row: CPU · GPU · Memory · Disk I/O │ Download · Latency · Loss

──── SYSTEM ──────────────────────────────
CPU ─────────┬──── GPU
Memory ──────┼──── Storage
Temperatures (CPU / GPU / motherboard / drives)
Processes (top 10 by CPU │ top 10 by memory)

──── NETWORK ─────────────────────────────
Throughput (1/5/15 min)  │  Latency trend (gateway vs public)
Link details (NIC, band, channel, signal, jitter, errors, …)

▶ Findings (collapsed by default — one-line verdict, expand for the full reasoning)
```

The **Findings** panel is the point of this tool. Each item states *which piece of
hardware → through what mechanism → affects which metric*, plus what to do about it.
It refuses to emit filler advice like "optimize your network".

---

## Where the numbers come from

| Metric | Source | Requirements |
|---|---|---|
| GPU (NVIDIA) | `nvidia-smi` | NVIDIA driver, **no admin** |
| GPU (AMD / Intel) | LibreHardwareMonitor (ADL / IGCL behind the scenes) | LHM running |
| CPU / motherboard / drive temps | LibreHardwareMonitor HTTP API on `127.0.0.1:8085` | LHM running |
| Fallback temps | WMI `MSAcpi_ThermalZoneTemperature` | Admin; many AMD boards don't expose it |
| Everything else | `psutil` + `netsh` / WMI | none |

GPU data degrades gracefully: **nvidia-smi → LibreHardwareMonitor → an honest
"unavailable" with a reason**. It never invents a number to fill a cell.

### The temperature component is optional

Reading real temperatures on Windows requires a kernel driver, which means admin
rights and a third-party component. That is a decision we do not make for you:

- **Installer**: asks once, "install the temperature component too?" — Y unpacks
  LibreHardwareMonitor into the app folder, creates a shortcut, and starts it.
- **Portable zip**: ships a `LibreHardwareMonitor\` folder; run the exe inside if you
  want temperatures.
- **Skip it**: temperatures show "n/a" with the reason; everything else works.

LibreHardwareMonitor is MPL-2.0; its license ships inside the component folder.
It asks for UAC on every launch (that is how the driver loads) and lives in the tray.

**Integrated GPUs (AMD APU / Intel iGPU) usually have no temperature sensor of their
own** — they share the CPU die. Seeing "n/a" there is correct behaviour, not a bug.

---

## How packet loss is counted (so you can verify it)

People compare this number with `ping -t` and get confused. Four things matter:

| Item | What the tool actually does |
|---|---|
| Probe target | Default `223.5.5.5` (AliDNS). **Your `ping` may hit a different host** — use `--ping-target <same-host>` for an apples-to-apples comparison |
| Timeout window | **4000 ms**, matching Windows `ping`. A short window turns "slow reply" into a fake "loss" |
| Denominator | **Probes actually sent**, not UI frames, not including the first incomplete tick |
| Send failures | Unresolvable host / no route / ICMP blocked → recorded as `error`, **excluded from the loss rate**, and reported separately |

The subtitle under the loss cell is the ledger: `timeout 2/57` means 2 of 57 probes
timed out. Red dots on the latency chart mark *confirmed timeouts* only.

> An earlier version used a 900 ms window; with this machine's ~1000 ms public RTT it
> reported 90% "loss" while `ping -n 10` showed 10%. Hence the 4000 ms window and the
> timeout/error split.

---

## Why hardware matters for networking (the model behind the advice)

1. **The medium sets the ceiling.** Wi-Fi's cost isn't "slower speed" — it's
   *retransmission*. Shared medium, collisions, backoff. Wired is point-to-point
   full duplex with none of that. A gigabit port sitting idle while the machine runs
   on Wi-Fi is the highest-priority finding this tool can produce.
2. **2.4 GHz is a crowded band.** Only channels 1/6/11 don't overlap, and Bluetooth,
   peripherals, microwaves and neighbours' APs all live there. 5 GHz has an order of
   magnitude fewer interferers and 3-6× the bandwidth under 802.11ac.
3. **USB Wi-Fi adapters are physically compromised.** Bus-powered, tiny antennas, and
   USB 3.0 ports emit broadband noise right around 2.4 GHz — the closer your USB3
   drive/dock, the higher the 2.4 GHz receive error rate (reproducible).
4. **CPU affects interrupt latency, not bandwidth.** Every packet costs an interrupt
   and a trip through the stack. When CPU saturates, handling is deferred → throughput
   jitter, latency spikes, retransmits. Classic signature: **one core at 100% while
   total CPU reads 30%** (NIC interrupts pinned to a single core).
5. **Power plans quietly slow you down.** Balanced/power-saver enables PCIe ASPM and
   NIC power saving; waking from idle adds latency — the "pause then stutter" feel.
6. **A gigabit link negotiating 100 Mbps is a cable problem.** 4-wire cable, oxidised
   connectors, or miswired wall panels. Nothing in software fixes it.
7. **Memory and storage rarely matter.** Unless memory exhaustion compresses socket
   buffers, 48 GB of RAM and an SSD are not your network bottleneck. The tool will not
   invent "optimize your disk" advice to look thorough.

---

## Interface language

Top-right `中 / EN`. The choice persists in `localStorage`; on first visit it follows
the browser language, so an English system never sees a screen of Chinese first.

Coverage is four layers — miss one and you get a half-translated UI:

| Layer | File | Contents |
|---|---|---|
| Static page text | `web/i18n.js` | 136 keys: card titles, KPI labels, legends, buttons, footer |
| Dynamic text | `t()` calls in `web/app.js` | units, state descriptions, generated GPU/temp/storage/link text |
| Analysis output | `i18n_rules.py` | 24 rules × title/detail/advice + summary + grade |
| Console | `MSG` in `server.py` | banner, startup info, capability notices |

The server serves `/api/snapshot?lang=en` and `/api/stream?lang=en`; both language
variants of the analysis are computed in the same tick, so switching languages does
not wait for the next sample. Console language: `--lang en`, otherwise auto-detected
from the system UI language.

Tests enforce this: `tests/ui_smoke_test.js` checks that the `zh` and `en` key sets
match and that every `t('...')` key exists; `tests/test_analyzer_i18n.py` renders all
24 rules in both languages and fails if any English string still contains Chinese.

---

## Known limitations

- **Windows 10/11 64-bit only.** Wi-Fi band/channel, NIC enumeration and power plans
  rely on `netsh`, PowerShell and the registry.
- **This machine only.** It is not a LAN monitor.
- **Some strings stay Chinese in English mode by design**: NIC model names, power plan
  names, and some LHM sensor labels come from the operating system. Translating them
  would make them harder to match against Device Manager.
- **Process ranking merges by application name**, so Chrome's 20 renderer processes
  show as one row with `×20` — that is what makes "who is eating the CPU" readable.
- **No history on disk.** 30 minutes in memory, gone on exit.
- **Loss probing uses ICMP.** Networks that block ping will show `--`.
- **The temperature component needs admin on every start** (kernel driver). To avoid
  the UAC prompt, tick `Options → Run on Windows startup` in its tray menu.

---

## Building

```bat
build_all.bat
```

Produces, in order: environment → icon → single-file exe → installer (IExpress) →
portable zip. Takes 1-3 minutes.

The temperature component needs a local LibreHardwareMonitor folder as its source:
defaults to `C:\Tools\LibreHardwareMonitor`, override with the `LHM_SRC` environment
variable. If it is missing, the build stops rather than silently shipping a package
without the component.

Why IExpress instead of Inno Setup: zero extra tooling, extracts to `%TEMP%` and cleans
up after itself. Its one hard limit — no subdirectories in the CAB — is why the payload
is four flat files and LibreHardwareMonitor travels as a zip.

---

## Tests

```bash
python tests/test_lhm_gpu.py           # GPU parsing: AMD / Intel / CPU-not-GPU / warning-only
python tests/test_analyzer_i18n.py     # all rules in both languages, placeholder + leak checks
node tests/ui_smoke_test.js            # DOM ids, render pass, i18n key parity
```

---

## License

MIT — see [LICENSE](LICENSE). LibreHardwareMonitor, shipped as an optional component,
is MPL-2.0; its license is included with the component.
