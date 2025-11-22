# TI MSPM0: development platform for [PlatformIO](https://platformio.org)

The Texas Instruments MSPM0 family of 32-bit Flash microcontrollers, based on the Arm® Cortex®-M0+ core, is designed to bring new levels of performance, efficiency, and integration to cost-sensitive and power-critical embedded applications. Running at up to 80 MHz, the MSPM0 series combines a highly efficient Cortex-M0+ processor with modern security features and a rich set of high-performance peripherals.

- [Home](https://github.com/Berkays/platform-ti-mspm0) (home page in the PlatformIO Registry)
- [Documentation](https://docs.platformio.org/en/latest/platforms/index.html) (advanced usage, packages, boards, frameworks, etc.)

# Usage

1. [Install PlatformIO](https://platformio.org)
2. Clone into this repository and run `pio platform install`
3. Create PlatformIO project and configure a platform option in [platformio.ini](https://docs.platformio.org/page/projectconf.html) file:
4. See [Sample Project](https://github.com/Berkays/platform-ti-mspm0-sample) for bare minimum setup.

## Stable version

```ini
[env:stable]
platform = timspm0
board = ...
...
```

## Development version

```ini
[env:development]
platform = https://github.com/Berkays/platform-ti-mspm0.git
board = ...
...
```

# Configuration

Please navigate to [documentation](https://docs.platformio.org/page/platforms/index.html).
