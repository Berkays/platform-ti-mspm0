import json
import os
import re
import subprocess
import sys
from os.path import isdir, isfile, join
from shutil import which

from platform import system  # type: ignore

from SCons.Script import Default, DefaultEnvironment, AlwaysBuild, Builder, COMMAND_LINE_TARGETS, ARGUMENTS  # type: ignore

OS = system().lower()

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()

def errAndExit(msg):
    sys.stderr.write(f"{msg}\n")
    env.Exit(1)

BOARD_MCU_NAME = env.get("BOARD", None)
assert BOARD_MCU_NAME, "Missing MCU Board in platformio.ini"

PROJECT_DIR = env.get('PROJECT_DIR')
PROJECT_SRC_DIR = env.get('PROJECT_SRC_DIR')
PROJECT_BUILD_DIR = join(env.get('PROJECT_BUILD_DIR'), BOARD_MCU_NAME)
PROJECT_INCLUDE_DIR = env.get('PROJECT_INCLUDE_DIR')

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

TI_MSPM0_SDK_PACKAGE_NAME = "toolchain-timspm0-sdk"
TI_MSPM0_SYSCONFIG_PACKAGE_NAME = "tool-timspm0-sysconfig"
GCC_ARM_COMPILER_PACKAGE_NAME = "toolchain-gccarmnoneeabi"

MSPM0_SDK_DIR = join(platform.get_package_dir(TI_MSPM0_SDK_PACKAGE_NAME) or "", "mspm0-sdk")
if not isdir(MSPM0_SDK_DIR):
    errAndExit(
        "Error: TI MSPM0 SDK package not found.\n"
        "Re-install it with: pio pkg install -l \"%s\"" % TI_MSPM0_SDK_PACKAGE_NAME
    )
print("MSPM0 SDK package version: %s" % platform.get_package_version(TI_MSPM0_SDK_PACKAGE_NAME))

MSPM0_SDK_METADATA_FILE = join(MSPM0_SDK_DIR, '.metadata', 'product.json')
if not isfile(MSPM0_SDK_METADATA_FILE):
    errAndExit(f"Error: MSPM0 SDK metadata not found at {MSPM0_SDK_METADATA_FILE}")

# The authoritative SDK version (e.g. "2.08.00.03") comes from TI's metadata
# and is used when generating starter .syscfg files. Never hardcode it.
with open(MSPM0_SDK_METADATA_FILE, mode='r') as fp:
    MSPM0_SDK_PRODUCT = json.load(fp)
MSPM0_SDK_VERSION = MSPM0_SDK_PRODUCT.get("version", "")
print("MSPM0 SDK version: %s" % MSPM0_SDK_VERSION)

SYSCONFIG_PACKAGE_DIR = platform.get_package_dir(TI_MSPM0_SYSCONFIG_PACKAGE_NAME) or ""
SYSCONFIG_BIN_DIR = join(SYSCONFIG_PACKAGE_DIR, 'bin')
TI_SYSCONFIG_CLI = join(SYSCONFIG_BIN_DIR, 'dist', 'cli.js')
if not isfile(TI_SYSCONFIG_CLI):
    errAndExit(
        f"Error: TI SysConfig CLI not found at {TI_SYSCONFIG_CLI}\n"
        "Re-install it with: pio pkg install -l \"%s\"" % TI_MSPM0_SYSCONFIG_PACKAGE_NAME
    )

# Resolve a Node.js runtime for the SysConfig CLI. Prefer the one bundled by
# the tool package (downloaded by its post-install script), fall back to any
# Node.js available on PATH. Works on Windows, macOS and Linux.
NODE_EXE_NAME = "node.exe" if OS == "windows" else "node"
TI_SYSCONFIG_NODE = join(SYSCONFIG_BIN_DIR, 'nodejs', NODE_EXE_NAME)
if isfile(TI_SYSCONFIG_NODE):
    print("SysConfig Node.js: %s" % TI_SYSCONFIG_NODE)
else:
    TI_SYSCONFIG_NODE = which(NODE_EXE_NAME)
    if TI_SYSCONFIG_NODE:
        print("SysConfig Node.js (from PATH): %s" % TI_SYSCONFIG_NODE)
    else:
        errAndExit(
            "Error: Node.js runtime for TI SysConfig not found.\n"
            "Re-install the tool package (its post-install script downloads Node.js):\n"
            "  pio pkg update -g -t \"%s\"" % TI_MSPM0_SYSCONFIG_PACKAGE_NAME
        )

COMPILER_PATH = platform.get_package_dir(GCC_ARM_COMPILER_PACKAGE_NAME)

TI_C_COMPILER_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gcc')
TI_CPP_COMPILER_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-g++')
TI_BINSIZE_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-size')
TI_ARMARC_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gcc-ar')
TI_ARMASM_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-as')
TI_ARMOBJCOPY_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-objcopy')
TI_GDB_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gdb')
TI_RANLIB_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gcc-ranlib')

SYSCONFIG_GEN_DIR = join(PROJECT_BUILD_DIR, 'syscfg')

env.Replace(  # type: ignore
    CC=TI_C_COMPILER_PATH,       # TI ARM compiler
    CXX=TI_CPP_COMPILER_PATH,      # TI ARM compiler
    LINK=TI_C_COMPILER_PATH,     # TI ARM linker
    AS=TI_ARMASM_PATH,     # TI ARM assembler
    AR=TI_ARMARC_PATH,     # TI ARM archiver
    OBJCOPY=TI_ARMOBJCOPY_PATH,     # TI ARM OBJCOPY
    GDB=TI_GDB_PATH,
    RANLIB=TI_RANLIB_PATH,
    SIZETOOL=TI_BINSIZE_PATH,
    ARFLAGS=["rc"]
)

env.Replace(
    PROGSUFFIX=".elf",
    SIZEPRINTCMD="$SIZETOOL -B -d $SOURCES",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPROGREGEXP=r"^(?:\.text|\.data|\.rodata|\.text.align|\.ARM.exidx)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.data|\.bss|\.noinit)\s+(\d+).*"
)


def mcu_to_syscfg_family(mcu):
    """Map an exact part to its SysConfig device family.

    MSPM0G3507 -> mspm0g350x, MSPM0L1117 -> mspm0l111x, ...
    """
    mcu = (mcu or "").lower()
    if mcu and mcu[-1].isdigit():
        return mcu[:-1] + "x"
    return mcu


# Locate .syscfg file in the project (root first, then src/)
syscfg_candidates = []
for search_dir in (PROJECT_DIR, PROJECT_SRC_DIR):
    if not isdir(search_dir):
        continue
    for filename in sorted(os.listdir(search_dir)):
        filepath = join(search_dir, filename)
        if isfile(filepath) and filename.endswith('.syscfg'):
            syscfg_candidates.append(filepath)

if len(syscfg_candidates) > 1:
    sys.stderr.write(
        "Warning! Multiple .syscfg files found, using %s:\n" % syscfg_candidates[0])
    for candidate in syscfg_candidates:
        sys.stderr.write(" - %s\n" % candidate)

sysConfigFile = syscfg_candidates[0] if syscfg_candidates else None

# No .syscfg supplied: seed the project with a starter configuration that
# follows TI's "empty" example (SYSCTL + Board modules) so the project
# compiles out of the box and can be refined in the SysConfig GUI.
if sysConfigFile is None:
    board_mcu = board.get("build.mcu")
    board_family = mcu_to_syscfg_family(board_mcu)
    starter = f"""/**
 * Starter TI SysConfig configuration generated by the timspm0 PlatformIO platform.
 * Open this file in the TI SysConfig GUI (https://www.ti.com/tool/SYSCONFIG)
 * to configure clocks, peripherals and pins. It is re-processed on every build.
 * @cliArgs --device "{board_family.upper()}" --part "Default" --product "mspm0_sdk@{MSPM0_SDK_VERSION}"
 * @v2CliArgs --device "{board_mcu.upper()}" --product "mspm0_sdk@{MSPM0_SDK_VERSION}"
 */

/**
 * Import the modules used in this configuration.
 */
const SYSCTL = scripting.addModule("/ti/driverlib/SYSCTL");

/**
 * Write custom configuration values to the imported modules.
 */

const Board = scripting.addModule("/ti/driverlib/Board", {{}}, false);
"""
    sysConfigFile = join(PROJECT_DIR, 'template.syscfg')
    with open(sysConfigFile, mode='w') as fp:
        fp.write(starter)
    print("No .syscfg file found - created a starter configuration at %s" % sysConfigFile)
else:
    print("Found .syscfg file: %s" % sysConfigFile)

# Get MCU device from .syscfg file. The "@cliArgs --device" directive carries
# the device family (e.g. MSPM0G350X) and "@v2CliArgs --device" the exact
# part (e.g. MSPM0G3507).
with open(sysConfigFile, mode='r') as fp:
    syscfgFileContents = fp.read()

def _parse_cli_device(directive):
    device = None
    for m in re.finditer(r"@%s[^\n]*" % directive, syscfgFileContents):
        dm = re.search(r'--device\s+"([^"]+)"', m.group(0))
        if dm:
            device = dm.group(1)
    return (device or "").strip()

syscfg_family_raw = _parse_cli_device("cliArgs")
syscfg_part_raw = _parse_cli_device("v2CliArgs")

startupDriverMCUDesignator = mcu_to_syscfg_family(syscfg_family_raw or syscfg_part_raw)
if not startupDriverMCUDesignator or not startupDriverMCUDesignator.startswith("mspm0"):
    errAndExit(
        'Failed to parse the MCU device from "%s".\n'
        "Make sure the file contains a '@cliArgs --device \"...\"' or "
        "'@v2CliArgs --device \"...\"' directive (files generated by TI SysConfig do)."
        % sysConfigFile
    )

# Guard against board <-> .syscfg device mismatches that would otherwise
# fail much later with confusing linker/upload errors.
board_family = mcu_to_syscfg_family(board.get("build.mcu"))
if startupDriverMCUDesignator != board_family:
    errAndExit(
        "Error: device mismatch between board and .syscfg file:\n"
        "  board '%s' expects device family '%s'\n"
        "  '%s' targets device family '%s'\n"
        "Use a matching board in platformio.ini, or update your .syscfg file."
        % (BOARD_MCU_NAME, board_family, sysConfigFile, startupDriverMCUDesignator)
    )

startup_file = join(
    MSPM0_SDK_DIR, 'source', 'ti', 'devices', 'msp', 'm0p',
    'startup_system_files', 'gcc', f'startup_{startupDriverMCUDesignator}_gcc.c')
if not isfile(startup_file):
    errAndExit(
        "Error: startup file for device family '%s' not found in the MSPM0 SDK.\n"
        "Expected: %s" % (startupDriverMCUDesignator, startup_file)
    )

# Run SysConfig CLI (invoked directly through Node.js so that it works on
# every host OS without shell wrappers; a failure aborts the build).
sysconfig_cmd = [
    TI_SYSCONFIG_NODE,
    TI_SYSCONFIG_CLI,
    "--script", sysConfigFile,
    "--output", SYSCONFIG_GEN_DIR,
    "-s", MSPM0_SDK_METADATA_FILE,
    "--compiler", "gcc",
]
print("Running TI SysConfig: %s" % " ".join(sysconfig_cmd[1:]))
result = subprocess.run(sysconfig_cmd)
if result.returncode != 0:
    errAndExit(
        "Error: TI SysConfig code generation failed (exit code %d).\n"
        "Fix the issues reported above in %s" % (result.returncode, sysConfigFile)
    )

if not isfile(join(SYSCONFIG_GEN_DIR, "ti_msp_dl_config.c")):
    errAndExit(
        "MSP configuration source files were not generated. "
        "Make sure to have a valid .syscfg file in your project."
    )

common_compile_options = [
    f'@{join(SYSCONFIG_GEN_DIR, "device.opt")}',
    '-march=armv6-m',
    '-mcpu=cortex-m0plus',
    '-mfloat-abi=soft',
    '-mlittle-endian',
    '-mthumb',
    '-g',
    '-gdwarf-3',
    '-gstrict-dwarf',
    '-Wall',
    '-O2',
    '-ffunction-sections',
    '-fdata-sections',
    '-MMD',
    '-MP',
    '-nostdlib',
    f'-I"{join(COMPILER_PATH, "arm-none-eabi", "include")}"',
    f'-I"{join(COMPILER_PATH, "arm-none-eabi", "include", "newlib-nano")}"'
]

# Compiler flags
env.Append(
    CCFLAGS=common_compile_options,
    CXXFLAGS=common_compile_options + [
        '-std=gnu++17',
    ],
    CPPPATH=[
        join(MSPM0_SDK_DIR, "source", "third_party", "CMSIS", "Core", "Include"),
        join(MSPM0_SDK_DIR, "source"),
        SYSCONFIG_GEN_DIR
    ],
    LINKFLAGS=common_compile_options + [
        '-Wl,--gc-sections',
        '-static',
        '-std=gnu++17',
        '--specs=nano.specs',
        '--specs=nosys.specs',
        '-nostdlib',
        '-Wl,--no-warn-rwx-segments',
        f'-Wl,-Map,"{join(PROJECT_BUILD_DIR, "Test.map")}"',
        f'-L"{SYSCONFIG_GEN_DIR}"',
        f'-L"{join(MSPM0_SDK_DIR, "source")}"',
        f'-L"{join(MSPM0_SDK_DIR, "source", "ti")}"',
        f'-T"{join(SYSCONFIG_GEN_DIR, "device_linker.lds")}"'
    ],
    LIBS=['c','m','gcc', 'stdc++', 'g', 'nosys', ':device.lds.genlibs']
)

env.Append(
    BUILDERS=dict(
        ElfToBin=Builder(
            action=" ".join([
                "$OBJCOPY",
                "-O",
                "binary",
                "$SOURCES",
                "$TARGET"]),
            suffix=".bin"
        )
    ),
)

# Add MCU Compiler definition required for VSCode intellisense
with open(join(SYSCONFIG_GEN_DIR, 'device.opt'), mode='r') as fp:
    deviceOptContents = fp.read()

pattern = r'-D(\w*__)'
match = re.search(pattern, deviceOptContents)
if match:
    env.Append(CPPDEFINES=[match.group(1)])

# External source files
sources = [
    join(SYSCONFIG_GEN_DIR, 'ti_msp_dl_config.c'),
    startup_file,
]

# Source object files
objects = []
for source in sources:
    base_name = os.path.splitext(os.path.basename(source))[0]
    obj_target = os.path.join(PROJECT_BUILD_DIR, base_name + '.o')
    if(source.endswith(".c")):
        obj = env.Object(
            target=obj_target,
            source=source,
            CCFLAGS=env.get('CCFLAGS'),
            CXX=TI_C_COMPILER_PATH
        )
    elif(source.endswith(".cpp")):
        obj = env.Object(
            target=obj_target,
            source=source,
            CCFLAGS=env.get('CXXFLAGS'),
            CXX=TI_CPP_COMPILER_PATH
        )
    env.Depends(obj, join(SYSCONFIG_GEN_DIR, 'device.opt'))
    objects.append(obj)

target_elf = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join(PROJECT_BUILD_DIR, "${PROGNAME}.elf")
    target_firmware = join(PROJECT_BUILD_DIR, "${PROGNAME}.bin")
else:
    env.Append(PIOBUILDFILES=objects)
    target_elf = env.BuildProgram()

    target_firmware = env.ElfToBin(join(PROJECT_BUILD_DIR, "${PROGNAME}.bin"), target_elf)
    env.Depends(target_firmware, 'checkprogsize')

# Define aliases
AlwaysBuild(env.Alias("nobuild", target_firmware))
target_buildprog = env.Alias("buildprog", target_firmware, target_firmware)

# Target: Print binary size
target_size = env.Alias(
    "size",
    target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE")
)
AlwaysBuild(target_size)

#
# Target: Upload by default .bin file
#
upload_protocol = env.subst("$UPLOAD_PROTOCOL")
debug_tools = board.get("debug.tools", {})
upload_source = target_firmware
upload_actions = []

if upload_protocol.startswith("jlink"):
    def _jlink_cmd_script(env, source):
        build_dir = env.subst("$BUILD_DIR")
        if not isdir(build_dir):
            os.makedirs(build_dir)
        script_path = join(build_dir, "upload.jlink")
        commands = [
            "h",
            "loadbin %s, %s" % (source, board.get(
                "upload.offset_address", "0x00000000")),
            "r",
            "q"
        ]
        with open(script_path, "w") as fp:
            fp.write("\n".join(commands))
        return script_path

    env.Replace(
        __jlink_cmd_script=_jlink_cmd_script,
        UPLOADER="JLink.exe" if system() == "Windows" else "JLinkExe",
        UPLOADERFLAGS=[
            "-device", board.get("debug", {}).get("jlink_device"),
            "-speed", env.GetProjectOption("debug_speed", "4000"),
            "-if", ("jtag" if upload_protocol == "jlink-jtag" else "swd"),
            "-autoconnect", "1",
            "-NoGui", "1"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS -CommanderScript "${__jlink_cmd_script(__env__, SOURCE)}"'
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
elif upload_protocol in debug_tools:
    openocd_args = [
        "-d%d" % (2 if int(ARGUMENTS.get("PIOVERBOSE", 0)) else 1)
    ]
    openocd_args.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))
    if env.GetProjectOption("debug_speed", ""):
        openocd_args.extend(
            ["-c", "adapter speed %s" % env.GetProjectOption("debug_speed")]
        )
    openocd_args.extend([
        "-c", "program {$SOURCE} %s verify reset; shutdown;" %
        board.get("upload.offset_address", "")
    ])
    openocd_args = [
        f.replace("$PACKAGE_DIR",
                  platform.get_package_dir("tool-openocd") or "")
        for f in openocd_args
    ]
    env.Replace(
        UPLOADER="openocd",
        UPLOADERFLAGS=openocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")

    if not board.get("upload").get("offset_address"):
        upload_source = target_elf
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

AlwaysBuild(env.Alias("upload", upload_source, upload_actions))

#
# Default targets
#
env.Default([target_buildprog, target_size])
