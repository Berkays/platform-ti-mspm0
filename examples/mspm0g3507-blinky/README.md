# MSPM0G3507 LaunchPad - blinking LED

Blinks the RGB LEDs on the LP-MSPM0G3507 LaunchPad. Adapted from the
`gpio_toggle_output` example of TI's MSPM0 SDK (BSD-3-Clause, Copyright
(c) 2023 Texas Instruments Incorporated).

The hardware configuration (GPIO pins, SYSCTL power/clock) is described in
`gpio_toggle_output.syscfg` and processed by the TI SysConfig CLI during
`pio run`. Open the `.syscfg` file in the
[SysConfig GUI](https://www.ti.com/tool/SYSCONFIG) to change it.

```console
$ pio run           # build
$ pio run -t upload # flash via J-Link
```
