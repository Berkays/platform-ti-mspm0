# TI MSPM0: development platform for [PlatformIO](https://platformio.org)

The Texas Instruments MSPM0 family of 32-bit Flash microcontrollers, based on the Arm® Cortex®-M0+ core, is designed to bring new levels of performance, efficiency, and integration to cost-sensitive and power-critical embedded applications. Running at up to 80 MHz, the MSPM0 series combines a highly efficient Cortex-M0+ processor with modern security features and a rich set of high-performance peripherals.

This platform integrates the [MSPM0 SDK](https://www.ti.com/tool/MSPM0-SDK) (DriverLib) and the [TI SysConfig](https://www.ti.com/tool/SYSCONFIG) code generator: you describe pins, clocks and peripherals in a `.syscfg` file, and the platform generates the HAL (`ti_msp_dl_config.c/h`, linker script, startup code) as part of every PlatformIO build. No CCS installation required.

- [Home](https://github.com/Berkays/platform-ti-mspm0) (home page in the PlatformIO Registry)
- [Documentation](https://docs.platformio.org/en/latest/platforms/index.html) (advanced usage, packages, boards, frameworks, etc.)

# Usage

1. [Install PlatformIO](https://platformio.org)
2. Create a PlatformIO project and configure a platform option in [platformio.ini](https://docs.platformio.org/page/projectconf.html) file:

```ini
[env:lp_mspm0g3507]
platform = timspm0
board = mspm0g3507
```

3. Drop a `.syscfg` file into your project (see below) and run `pio run`.

Everything else — the GCC ARM toolchain, the MSPM0 SDK and the SysConfig CLI
(with its own Node.js runtime) — is downloaded and installed automatically
from the PlatformIO Registry. Nothing is installed system-wide.

## Configuring hardware with SysConfig

Create your `.syscfg` file with the standalone [SysConfig GUI](https://www.ti.com/tool/SYSCONFIG)
(choose the "MSPM0" product when creating a new file), save it in the project
root (or `src/`), and build:

```console
$ pio run
```

The build validates that the `.syscfg` device matches the board selected in
`platformio.ini`, runs the SysConfig CLI to generate the HAL into the build
directory, compiles your application against the MSPM0 SDK DriverLib and
links everything into `firmware.elf` / `firmware.bin`.

If your project has **no** `.syscfg` file yet, the first build creates a
minimal starter `template.syscfg` (default clock configuration) that already
compiles — open it in the SysConfig GUI to configure peripherals from there.

The `examples/` directory of this repository contains a complete blinking-LED
project for the LaunchPad.

## Uploading and debugging

The default upload/debug protocol is [J-Link](https://docs.platformio.org/page/plus/debug-tools/jlink.html):

```ini
[env:lp_mspm0g3507]
platform = timspm0
board = mspm0g3507
upload_protocol = jlink      ; default
debug_tool = jlink           ; default
```

```console
$ pio run -t upload      ; flash firmware.bin
$ pio debug              ; start a debugging session
```

# Updating

```console
$ pio platform update timspm0        ; platform + packages (SDK, SysConfig)
```

New MSPM0 SDK releases published to the registry are picked up
automatically within the version range required by the platform.

## Development version

```ini
[env:development]
platform = https://github.com/Berkays/platform-ti-mspm0.git
board = mspm0g3507
```

Bleeding-edge SDK builds can be pinned per-project with `platform_packages`:

```ini
[env:edge]
platform = timspm0
board = mspm0g3507
platform_packages =
    toolchain-timspm0-sdk @ https://github.com/Berkays/toolchain-timspm0-sdk.git
```

# Maintainer notes

- `scripts/update_sdk.py` bumps the
  [toolchain-timspm0-sdk](https://github.com/Berkays/toolchain-timspm0-sdk)
  wrapper repository to a new release tag of TI's
  [mspm0-sdk](https://github.com/TexasInstruments/mspm0-sdk) repository
  (submodule pin, TI→semver version mapping, commit, tag, push, optional
  registry publish). It warns when the SDK requires a newer SysConfig tool
  than the one packaged. Run `python3 scripts/update_sdk.py` to list
  available TI releases.
- The TI version scheme (`2.09.00.00`) maps to PlatformIO semver versions as
  `2.9.0+0` (documented in the wrapper repository).

# Configuration

Please navigate to [documentation](https://docs.platformio.org/page/platforms/index.html).
