#!/usr/bin/env python3

import argparse
import os
import struct
import tempfile
import atexit

from sipyco import common_args

from artiq import __version__ as artiq_version
from artiq.master.databases import DeviceDB
from artiq.coredevice.comm_kernel import CommKernel
from artiq.coredevice.comm_mgmt import CommMgmt
from artiq.frontend.flash_tools import bit2bin, fetch_bin


def get_argparser():
    parser = argparse.ArgumentParser(description="ARTIQ core device "
                                                 "management tool")
    parser.add_argument("--version", action="version",
                        version="ARTIQ v{}".format(artiq_version),
                        help="print the ARTIQ version number")

    common_args.verbosity_args(parser)
    parser.add_argument("--device-db", default="device_db.py",
                       help="device database file (default: '%(default)s')")
    parser.add_argument("-D", "--device", default=None,
                        help="use specified core device address instead of "
                             "reading device database")

    tools = parser.add_subparsers(dest="tool")
    tools.required = True

    # logging
    t_log = tools.add_parser("log",
                             help="read logs and change log levels")

    subparsers = t_log.add_subparsers(dest="action")

    p_clear = subparsers.add_parser("clear",
                                    help="clear log buffer")

    p_set_level = subparsers.add_parser("set_level",
                                        help="set minimum level for messages to be logged")
    p_set_level.add_argument("level", metavar="LEVEL", type=str,
                             help="log level (one of: OFF ERROR WARN INFO DEBUG TRACE)")

    p_set_uart_level = subparsers.add_parser("set_uart_level",
                                             help="set minimum level for messages to be logged "
                                                  "to UART")
    p_set_uart_level.add_argument("level", metavar="LEVEL", type=str,
                                  help="log level (one of: OFF ERROR WARN INFO DEBUG TRACE)")

    # configuration
    t_config = tools.add_parser("config",
                                help="read and change core device configuration")

    subparsers = t_config.add_subparsers(dest="action")
    subparsers.required = True

    p_read = subparsers.add_parser("read",
                                   help="read key from core device config")
    p_read.add_argument("key", metavar="KEY", type=str,
                        help="key to be read from core device config")

    p_write = subparsers.add_parser("write",
                                    help="write key-value records to core "
                                         "device config")
    p_write.add_argument("-s", "--string", nargs=2, action="append",
                         default=[], metavar=("KEY", "STRING"), type=str,
                         help="key-value records to be written to core device "
                              "config")
    p_write.add_argument("-f", "--file", nargs=2, action="append",
                         type=str, default=[],
                         metavar=("KEY", "FILENAME"),
                         help="key and file whose content to be written to "
                              "core device config")

    p_remove = subparsers.add_parser("remove",
                                     help="remove key from core device config")
    p_remove.add_argument("key", metavar="KEY", nargs=argparse.REMAINDER,
                          default=[], type=str,
                          help="key to be removed from core device config")

    subparsers.add_parser("erase", help="fully erase core device config")

    # booting
    t_boot = tools.add_parser("reboot",
                              help="reboot the running system")

    # flashing
    t_flash = tools.add_parser("flash",
                               help="flash the running system")

    p_directory = t_flash.add_argument("directory",
                                       metavar="DIRECTORY", type=str,
                                       help="directory that contains the "
                                            "binaries")

    p_srcbuild = t_flash.add_argument("--srcbuild",
                                      help="board binaries directory is laid "
                                           "out as a source build tree",
                                      default=False, action="store_true")

    # misc debug
    t_debug = tools.add_parser("debug",
                               help="specialized debug functions")

    subparsers = t_debug.add_subparsers(dest="action")
    subparsers.required = True

    p_allocator = subparsers.add_parser("allocator",
                                        help="show heap layout")

    # manage target
    p_drtio_dest = parser.add_argument("-s", "--drtio-dest", default=0,
                                       metavar="DRTIO_DEST", type=int,
                                       help="specify DRTIO destination that "
                                            "receives this command")

    return parser


def main():
    args = get_argparser().parse_args()
    common_args.init_logger_from_args(args)

    if args.device is None:
        ddb = DeviceDB(args.device_db)
        core_addr = ddb.get("core", resolve_alias=True)["arguments"]["host"]
    else:
        core_addr = args.device
    mgmt = CommMgmt(core_addr, drtio_dest=args.drtio_dest)

    if args.tool == "log":
        if args.action == "set_level":
            mgmt.set_log_level(args.level)
        if args.action == "set_uart_level":
            mgmt.set_uart_log_level(args.level)
        if args.action == "clear":
            mgmt.clear_log()
        if args.action == None:
            print(mgmt.get_log(), end="")

    if args.tool == "config":
        if args.action == "read":
            value = mgmt.config_read(args.key)
            if not value:
                print("Key {} does not exist".format(args.key))
            else:
                print(value)
        if args.action == "write":
            for key, value in args.string:
                mgmt.config_write(key, value.encode("utf-8"))
            for key, filename in args.file:
                with open(filename, "rb") as fi:
                    mgmt.config_write(key, fi.read())
        if args.action == "remove":
            for key in args.key:
                mgmt.config_remove(key)
        if args.action == "erase":
            mgmt.config_erase()

    if args.tool == "flash":
        retrieved_bins = []
        bin_dict = {
            "zynq":[
                ["boot"]
            ],
            "riscv": [
                ["gateware"],
                ["bootloader"],
                ["runtime", "satman"],
            ],
        }

        for bin_list in bin_dict.values():
            try:
                bins = []
                for bin_name in bin_list:
                    bins.append(fetch_bin(
                        args.directory, bin_name, args.srcbuild))
                retrieved_bins.append(bins)
            except FileNotFoundError:
                pass

        if retrieved_bins is None:
            raise FileNotFoundError("neither risc-v nor zynq binaries were found")

        if len(retrieved_bins) > 1:
            raise ValueError("both risc-v and zynq binaries were found, "
                             "please clean up your build directory. ")

        bins = retrieved_bins[0]
        mgmt.flash(bins)

    if args.tool == "reboot":
        mgmt.reboot()

    if args.tool == "debug":
        if args.action == "allocator":
            mgmt.debug_allocator()


if __name__ == "__main__":
    main()
