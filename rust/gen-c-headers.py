#! /usr/bin/env python2

# This script will scan Rust source files looking for extern "C"
# functions and generate C header files from them with a filename
# based on the Rust filename.
#
# Usage: From the top suricata source directory:
#
#    ./rust/gen-c-headers.py
#

from __future__ import print_function

import sys
import os
import re
from io import StringIO

template = """/* Copyright (C) 2017 Open Information Security Foundation
 *
 * You can copy, redistribute or modify this Program under the terms of
 * the GNU General Public License version 2 as published by the Free
 * Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * version 2 along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
 * 02110-1301, USA.
 */

/*
 * DO NOT EDIT. This file is automatically generated.
 */

#ifndef __%(name)s__
#define __%(name)s__

%(prototypes)s
#endif /* ! __%(name)s__ */
"""

# Map of Rust types to C types.
type_map = {
    "bool": "bool",
    "i8": "int8_t",
    "i16" :"int16_t",
    "i32" :"int32_t",
    "i64" :"int64_t",

    "u8": "uint8_t",
    "u16" :"uint16_t",
    "u32" :"uint32_t",
    "u64" :"uint64_t",

    "libc::c_void": "void",

    "libc::c_char": "char",
    "libc::c_int": "int",
    "c_int": "int",
    "libc::int8_t": "int8_t",

    "libc::uint8_t": "uint8_t",
    "libc::uint16_t": "uint16_t",
    "libc::uint32_t": "uint32_t",
    "libc::uint64_t": "uint64_t",

    "SuricataContext": "SuricataContext",
    "SuricataFileContext": "SuricataFileContext",
    "FileContainer": "FileContainer",
    "core::Flow": "Flow",
    "Flow": "Flow",
    "DNSState": "RSDNSState",
    "DNSTransaction": "RSDNSTransaction",
    "NFSState": "NFSState",
    "NFSTransaction": "NFSTransaction",
    "NTPState": "NTPState",
    "NTPTransaction": "NTPTransaction",
    "TFTPTransaction": "TFTPTransaction",
    "TFTPState": "TFTPState",
    "JsonT": "json_t",
    "DetectEngineState": "DetectEngineState",
    "core::DetectEngineState": "DetectEngineState",
    "core::AppLayerDecoderEvents": "AppLayerDecoderEvents",
    "AppLayerDecoderEvents": "AppLayerDecoderEvents",
    "core::AppLayerEventType": "AppLayerEventType",
    "AppLayerEventType": "AppLayerEventType",
    "CLuaState": "lua_State",
    "Store": "Store",
    "AppProto": "AppProto",
}

def convert_type(rs_type):
    m = re.match("^[^\s]+$", rs_type)
    if m:
        if rs_type in type_map:
            return type_map[rs_type]

    m = re.match("^(.*)(\s[^\s]+)$", rs_type)
    if m:
        mod = m.group(1).strip()
        rtype = m.group(2).strip()
        if rtype in type_map:
            if mod in [
                    "*mut",
                    "* mut",
                    "&mut",
                    "&'static mut",
                    ]:
                return "%s *" % (type_map[rtype])
            elif mod in [
                    "*const",
                    "* const"]:
                return "const %s *" % (type_map[rtype])
            elif mod in [
                    "*mut *const",
                    "*mut*const"]:
                return "%s **" % (type_map[rtype])
            else:
                raise Exception("Unknown modifier '%s' in '%s'." % (
                    mod, rs_type))
        else:
            raise Exception("Unknown type: %s" % (rtype))

    raise Exception("Failed to parse Rust type: %s" % (rs_type))

def make_output_filename(filename):
    parts = filename.split(os.path.sep)[2:]
    last = os.path.splitext(parts.pop())[0]
    outpath = "./gen/c-headers/rust-%s-%s-gen.h" % (
        "-".join(parts), last)
    return outpath.replace("--", "-")

def write_header(fileobj, filename):
    filename = os.path.basename(filename).replace(
        "-", "_").replace(".", "_").upper()
    fileobj.write(file_header % {"name": filename})

def should_regen(input_filename, output_filename):
    """Check if a file should be regenerated. If the output doesn't exist,
    or the input is newer than the output return True. Otherwise
    return False.

    """
    if not os.path.exists(output_filename):
        return True
    if os.stat(input_filename).st_mtime > os.stat(output_filename).st_mtime:
        return True
    return False

def gen_headers(filename):

    output_filename = make_output_filename(filename)

    if not should_regen(filename, output_filename):
        return

    buf = open(filename).read()
    writer = StringIO()

    for fn in re.findall(
            r"^pub (unsafe )?extern \"C\" fn ([A_Za-z0-9_]+)\(([^{]+)?\)"
            r"(\s+-> ([^{]+))?",
            buf,
            re.M | re.DOTALL):

        args = []

        fnName = fn[1]

        for arg in fn[2].split(","):
            if not arg:
                continue
            arg_name, rs_type = arg.split(":", 1)
            arg_name = arg_name.strip()
            rs_type = rs_type.strip()
            c_type = convert_type(rs_type)

            if arg_name != "_":
                args.append("%s %s" % (c_type, arg_name))
            else:
                args.append(c_type)

        if not args:
            args.append("void")

        retType = fn[4].strip()
        if retType == "":
            returns = "void"
        else:
            returns = convert_type(retType)

        writer.write(u"%s %s(%s);\n" % (returns, fnName, ", ".join(args)))

    if writer.tell() > 0:
        print("Writing %s" % (output_filename))
        if not os.path.exists(os.path.dirname(output_filename)):
            os.makedirs(os.path.dirname(output_filename))
        with open(output_filename, "w") as output:
            output.write(template % {
                "prototypes": writer.getvalue(),
                "name": os.path.basename(output_filename).replace(
                    "-", "_").replace(".", "_").upper()
            })

def main():

    rust_top = os.path.dirname(sys.argv[0])
    os.chdir(rust_top)

    for dirpath, dirnames, filenames in os.walk("./src"):
        for filename in filenames:
            if filename.endswith(".rs"):
                path = os.path.join(dirpath, filename)
                gen_headers(path)

if __name__ == "__main__":
    sys.exit(main())
