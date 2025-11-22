import os
from os import makedirs
from os.path import join, isdir
import re
import sys

from platform import system # type: ignore

from SCons.Script import Default, DefaultEnvironment, AlwaysBuild, Builder, COMMAND_LINE_TARGETS, ARGUMENTS # type: ignore

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
PROJECT_SRC_DIR = env.get('PROJECT_DIR')
PROJECT_BUILD_DIR = join(env.get('PROJECT_BUILD_DIR'), BOARD_MCU_NAME)
PROJECT_INCLUDE_DIR = env.get('PROJECT_INCLUDE_DIR')

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

TI_MSPM0_SDK_PACKAGE_NAME = "toolchain-timspm0-sdk"
TI_MSPM0_SYSCONFIG_PACKAGE_NAME = "tool-timspm0-sysconfig"
GCC_ARM_COMPILER_PACKAGE_NAME = "toolchain-gccarmnoneeabi"
try:
    platform.get_package(TI_MSPM0_SDK_PACKAGE_NAME)
except KeyError:
    errAndExit("Error: MSP SDK Not found in platformio packages.\n")

try:
    platform.get_package(TI_MSPM0_SYSCONFIG_PACKAGE_NAME)
except KeyError:
    errAndExit("Error: Sysconfig Tool not found in platformio packages.\n")

MSPM0_SDK_DIR = join(platform.get_package_dir(TI_MSPM0_SDK_PACKAGE_NAME), "mspm0-sdk")
print(f"SDK Version: {platform.get_package_version(TI_MSPM0_SDK_PACKAGE_NAME)}")
MSPM0_SDK_METADATA_FILE = join(MSPM0_SDK_DIR,'.metadata/product.json')

COMPILER_PATH = platform.get_package_dir(GCC_ARM_COMPILER_PACKAGE_NAME)

TI_SYSCFG_PATH = join(platform.get_package_dir(TI_MSPM0_SYSCONFIG_PACKAGE_NAME), 'bin', 'sysconfig_cli.sh')
TI_C_COMPILER_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gcc')
TI_CPP_COMPILER_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-g++')
TI_BINSIZE_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-size')
TI_ARMARC_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gcc-ar')
TI_ARMASM_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-as')
TI_ARMOBJCOPY_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-objcopy')
TI_GDB_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gdb')
TI_RANLIB_PATH = join(COMPILER_PATH, 'bin', 'arm-none-eabi-gcc-ranlib')

SYSCONFIG_GEN_DIR = join(PROJECT_BUILD_DIR, 'syscfg')

# # Check if sysconfig compiler exists
if not os.path.exists(TI_SYSCFG_PATH):
    errAndExit(f"Error: TI SysConfig Compiler not found at {TI_SYSCFG_PATH}")

env.Replace( # type: ignore
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

# Locate .sysconfig file in project root directory
sysConfigFile = None
isUsingSyscfgTemplate = False
for filename in os.listdir(PROJECT_DIR):
        filepath = os.path.join(PROJECT_DIR, filename)
        if os.path.isfile(filepath) and filename.endswith('.syscfg'):
            sysConfigFile = filepath
        
# Generate template sysconfig file
if(sysConfigFile is None):

    if(os.path.exists(SYSCONFIG_GEN_DIR)):
        errAndExit(".syscfg file not found")
    # src = join(platform.get_dir(), 'builder', 'template.syscfg')

    sysConfigTemplate = f"""/**
 * @cliArgs --device "{board.get("build.product_line").upper()}" --part "Default" --product "mspm0_sdk@2.08.00.03"
 * @v2CliArgs --device "{board.get("build.mcu").upper()}" --product "mspm0_sdk@2.08.00.03"
 */

const ProjectConfig = scripting.addModule("/ti/project_config/ProjectConfig");

ProjectConfig.deviceSpin = "{board.get("build.mcu").upper()}";
ProjectConfig.compiler = "gcc";
"""
    sysConfigFile = join(PROJECT_DIR, 'template.syscfg')
    with open(sysConfigFile, mode='w') as file:
        file.write(sysConfigTemplate)
    file.close()
    print(f".syscfg file not found. Using default template...")
    isUsingSyscfgTemplate = True
else:
    print(f"Found .syscfg file: {sysConfigFile}")

# Get MCU Model from .syscfg file
fread = open(sysConfigFile, mode='r')
syscfgFileContents= fread.read(-1)
fread.close()

# Get MCU Designator from .syscfg file
pattern = r"@cliArgs\s*--device\s*\"(\w*)\""
match = re.search(pattern, syscfgFileContents)
startupDriverMCUDesignator = None
if match:
    startupDriverMCUDesignator = match.group(1).lower()  # Output: mspm0l110x
else:
    errAndExit("Failed to parse MCU from .syscfg file.")


# Run SysConfig Compiler
env.Execute(f'"{TI_SYSCFG_PATH}" --script "{sysConfigFile}" -o "{SYSCONFIG_GEN_DIR}" -s "{MSPM0_SDK_METADATA_FILE}" --compiler gcc')
if(isUsingSyscfgTemplate):
    os.remove(sysConfigFile)

if((isUsingSyscfgTemplate is False) and os.path.exists(join(SYSCONFIG_GEN_DIR, "ti_msp_dl_config.c")) is False):
    errAndExit("MSP configuration source files not found. Make sure to have a valid .syscfg file in your project")

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
fread = open(join(SYSCONFIG_GEN_DIR, 'device.opt'), mode='r')
deviceOptContents = fread.read(-1)
fread.close()

pattern = r'-D(\w*__)'
match = re.search(pattern, deviceOptContents)
if match:
    env.Append(CPPDEFINES=[match.group(1)])

# External source files
sources = [
    join(SYSCONFIG_GEN_DIR, 'ti_msp_dl_config.c'),
    join(MSPM0_SDK_DIR, 'source', 'ti', 'devices', 'msp', 'm0p', 'startup_system_files', 'gcc', f'startup_{startupDriverMCUDesignator}_gcc.c'),
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
            makedirs(build_dir)
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
