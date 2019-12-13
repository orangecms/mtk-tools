#!/usr/bin/env python3
"""
Simple tool for communicating with the MediaTek Preloader bootloader and dumping
firmware images
"""

import time
import struct
import sys

import serial

"""
Preloader Commands
"""
CMD_GET_VERSION = b"\xff"
CMD_GET_BL_VER = b"\xfe"
CMD_GET_HW_SW_VER = b"\xfc"
CMD_GET_HW_CODE = b"\xfd"
CMD_SEND_DA = b"\xd7"
CMD_JUMP_DA = b"\xd5"
CMD_GET_TARGE_CONFIG = b"\xd8"
CMD_READ16 = b"\xa2"
CMD_WRITE16 = b"\xd2"
CMD_READ32 = b"\xd1"
CMD_WRITE32 = b"\xd4"
CMD_PWR_INIT = b"\xc4"
CMD_PWR_DEINIT = b"\xc5"
CMD_PWR_READ16 = b"\xc6"
CMD_PWR_WRITE16 = b"\xc7"
AGENT_BINARY = "MTK_AllInOne_DA.bin"
AGENT_OFFSET = 0x8280c
BLOCK1_LENGTH = 0x00ea6c
BLOCK2_LENGTH = 0x027530
TOKEN = bytes.fromhex('a0004b0000000008a00a5005')

def split_by_n(seq, unit_count):
    """A generator to divide a sequence into chunks of n units."""
    while seq:
        yield seq[:unit_count]
        seq = seq[unit_count:]

class MTKtools():
    """
    :)
    """
    def __init__(self):
        self.ser_port = None

    def read_rom(self, filename, start, length):
        """
        read binary from the ROM and write to file
        """
        print("sending read mode")
        self.send_cmd("\x60\x08", 2)
        self.send_cmd("\xd6\x0c\x02"+start+length, 1)
        self.ser_port.write("\x00\x10\x00\x00") # just use it :D who cares why

        data = 0
        file = open(filename, 'wb')

        while data < struct.unpack('>q', length)[0]: #data length
            datwrite = self.ser_port.read(0x400)
            if len(datwrite) == 2: # and datwrite=="\xca\xfe":
                self.ser_port.write("\x5a")
            else:
                file.write(bytes(datwrite))
                sys.stdout.write('.')
                data += 0x400
        file.close()

        self.send_cmd("", 2)
        print("sending 5a")
        self.send_cmd("\x5a", 0)

    def send_cmd(self, cmd, res_length):
        """
        send a command to the bootloader
        """
        print("Sending ", cmd)
        written = self.ser_port.write(cmd)
        print(written, " bytes written")
        self.ser_port.flush()
        timeout = time.time() + 1
        print("Reading...")
        while True:
            if time.time() > timeout:
                print("Read timed out.")
                return False
            try:
                num_bytes_waiting = self.ser_port.in_waiting
                res = self.ser_port.read(res_length)
                print(res)
                return res
                break
            except IOError as err:
                print("Nooooooo... {0}".format(err))
                time.sleep(.2)

    def send_initial_commands(self):
        """
        send initial commands
        """
        print("sending token and start")
        self.send_cmd(TOKEN, 16)
        time.sleep(.1)
        print("sending CMD_GET_HW_CODE")
        self.send_cmd(CMD_GET_HW_CODE, 5)
        print("sending CMD_GET_HW_SW_VER")
        self.send_cmd(CMD_GET_HW_SW_VER, 9)
        print("sending  CMD_READ32")
        self.send_cmd(CMD_READ32+"\x10\x00\x91\x70\x00\x00\x00\x01", 17)
        print("sending CMD_WRITE32")
        self.send_cmd(CMD_WRITE32+"\x10\x00\x70\x00\x00\x00\x00\x01\x22\x00\x00\x00", 17)
        print("sending CMD_GET_BL_VER")
        self.send_cmd(CMD_GET_BL_VER, 1)
        print("sending CMD_GET_VERSION")
        # this will echo id security off and i assume it is for now
        self.send_cmd(CMD_GET_VERSION, 1)
        print("sending CMD_GET_BL_VER")
        self.send_cmd(CMD_GET_BL_VER, 1)

    def send_agent(self):
        """
        send the agent binary to the bootloader
        """
        timeout = time.time() + 10
        while True:
            if time.time() > timeout:
                print("Connection timed out.")
                return False
            try:
                data = self.ser_port.readline(5)
                print(data)
                if data.decode() == "READY":
                    break
            except IOError as err:
                print("Nooooooo... {0}".format(err))
                time.sleep(.1)

        self.ser_port.flush()
        self.send_initial_commands()
        print("sending CMD_SEND_DA fingers crossed ")
        self.send_cmd(CMD_SEND_DA+"\x02\x00\x70\x00\x00\x00\xea\x6c\x00\x00\x01\x00", 15)

        with open(AGENT_BINARY, 'rb') as agent_binary:
            agent_binary.seek(AGENT_OFFSET)
            block1 = agent_binary.read(BLOCK1_LENGTH)
            block2 = agent_binary.read(BLOCK2_LENGTH)
            agent_binary.close()

        self.send_cmd(block1, 4)
        print("sending CMD_JUMP_DA")
        self.send_cmd(CMD_JUMP_DA+"\x02\x00\x70\x00", 48) # this response needs investigating
        print("sending 0x5a") # what is this Z maybe just a ready symbol
        self.send_cmd("\x5a", 3)
        print("sending 0xff could be a sig.") # what is this
        self.send_cmd("\xff\x01\x00\x08\x00\x70\x07\xff\xff\x01\x01\x50\x00\x00\x02\x01\x02\x00", 2)
        self.send_cmd("\x80\x00\x00\x00\x00\x02\x75\x30\x00\x00\x10\x00", 3)

        chunkstwo = list(split_by_n(block2, 0x1000))

        for i in range(0, len(chunkstwo)):
            print("Sending block2 chunk", i)
            self.send_cmd(chunkstwo[i], 1)

        self.send_cmd("", 1)
        print("sending 5a")
        self.send_cmd("\x5a", 232)
        self.send_cmd("", 22)
        print("send 72")
        self.send_cmd("\x72", 2)
        print("send 72")
        self.send_cmd("\x72", 2)

        return True

    def open_serial(self, port):
        """
        open the serial port and send the download agent
        """
        timeout = time.time() + 10 # connection timeout 10 seconds

        print("Connecting...", port)
        while True:
            if time.time() > timeout:
                return False
            try:
                self.ser_port = serial.Serial(
                    port,
                    baudrate=115200,
                    timeout=100,
                    rtscts=False
                )
                break

            except serial.serialutil.SerialException:
                pass

        print("Connected.")
        if not self.send_agent():
            print("Error sending download agent.")
            return False
        return True

def main():
    """
    main function :)
    """
    phone = MTKtools()

    if sys.platform.startswith('linux'):
        tty_dev = "/dev/ttyACM0"
    elif sys.platform.startswith('freebsd'):
        tty_dev = "/dev/cuaU0"
    else:
        print("Install Linux or FreeBSD!", sys.platform)
        sys.exit(1)

    if phone.open_serial(tty_dev):
        print("Dumping binaries...")

        phone.read_rom(
            "bootrom.bin",
            "\x00\x00\x00\x00\x02\x3a\x00\x00",
            "\x00\x00\x00\x00\x00\xf0\x00\x00"
        )
        phone.read_rom(
            "recovery.bin",
            "\x00\x00\x00\x00\x03\x2a\x00\x00",
            "\x00\x00\x00\x00\x00\x5e\xd8\x00"
        )

    else:
        print("Fail :(")

if __name__ == "__main__":
    main()
