import asyncio
import wx
from wxasync import WxAsyncApp, StartCoroutine
from pynput.keyboard import Key, Controller
from bleak import BleakScanner, BleakClient, BleakError

# Key assignments
KEY_JUMP = 'a'
KEY_LEAN_FORWARD = Key.right
KEY_LEAN_BACKWARD = Key.left
KEY_RED_TILE = 'b'
KEY_GREEN_TILE = Key.down

# Timing
BUTTON_TIME_DEFAULT = 0.1
BUTTON_TIME_JUMP = 1.5

# BLE characteristics
LEGO_CHARACTERISTIC_UUID = "00001624-1212-efde-1623-785feabcd123"
SUBSCRIBE_IMU_COMMAND = bytearray([0x0A, 0x00, 0x41, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x01])
SUBSCRIBE_RGB_COMMAND = bytearray([0x0A, 0x00, 0x41, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00, 0x01])

# GUI class
class MarioFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title="Lego Mario Controller", size=(500, 250))  # Adjusted size for signal meter
        self.init_gui()
        self.controller = MarioController(self)
        wx.CallAfter(self.start_async_tasks)

    def init_gui(self):
        panel = wx.Panel(self)
        font = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)

        # Status Label
        self.status_field = wx.StaticText(panel, label="Status: Not Connected", style=wx.ALIGN_CENTER)
        self.status_field.SetFont(font)

        # Camera and Acceleration Labels
        self.cam_field = wx.StaticText(panel, label="Tile: None", style=wx.ALIGN_LEFT)
        self.accel_field = wx.StaticText(panel, label="X: 0 | Y: 0 | Z: 0", style=wx.ALIGN_LEFT)

        # Signal strength (RSSI) Label
        self.signal_field = wx.StaticText(panel, label="Signal Strength: N/A", style=wx.ALIGN_LEFT)

        # Checkbox for Key Sending
        self.key_switch = wx.CheckBox(panel, label="Enable Key Sending")

        # Layout
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self.status_field, flag=wx.ALL | wx.EXPAND, border=5)
        vbox.Add(self.cam_field, flag=wx.ALL, border=5)
        vbox.Add(self.accel_field, flag=wx.ALL, border=5)
        vbox.Add(self.signal_field, flag=wx.ALL, border=5)
        vbox.Add(self.key_switch, flag=wx.ALL, border=5)

        panel.SetSizer(vbox)

    def start_async_tasks(self):
        StartCoroutine(self.controller.run(), self)

# Controller class
class MarioController:
    def __init__(self, gui):
        self.gui = gui
        self.keyboard = Controller()
        self.current_tile = 0
        self.current_x = 0
        self.current_y = 0
        self.current_z = 0
        self.is_connected = False
        self.rssi = None  # To store RSSI value

    def signed(char):
        return char - 256 if char > 127 else char

    async def process_keys(self):
        if self.is_connected and self.gui.key_switch.GetValue():
            if self.current_tile == 1:
                self.keyboard.press(KEY_RED_TILE)
                await asyncio.sleep(BUTTON_TIME_DEFAULT)
                self.keyboard.release(KEY_RED_TILE)
                self.current_tile = 0
            elif self.current_tile == 2:
                self.keyboard.press(KEY_GREEN_TILE)
                await asyncio.sleep(BUTTON_TIME_DEFAULT)
                self.keyboard.release(KEY_GREEN_TILE)
                self.current_tile = 0

            if self.current_z > 10:
                self.keyboard.press(KEY_LEAN_BACKWARD)
            elif self.current_z < -10:
                self.keyboard.press(KEY_LEAN_FORWARD)
            else:
                self.keyboard.release(KEY_LEAN_BACKWARD)
                self.keyboard.release(KEY_LEAN_FORWARD)

            if self.current_x > 5:
                self.keyboard.press(KEY_JUMP)
                await asyncio.sleep(BUTTON_TIME_JUMP)
                self.keyboard.release(KEY_JUMP)

        await asyncio.sleep(0.05)

    def notification_handler(self, sender, data):
        # Camera sensor data
        if data[0] == 8:
            # RGB code
            if data[5] == 0x0:
                if data[4] == 0xb8:
                    self.gui.cam_field.SetLabel("Start tile")
                    self.current_tile = 3
                if data[4] == 0xb7:
                    self.gui.cam_field.SetLabel("Goal tile")
                    self.current_tile = 4
                print("Barcode: " + " ".join(hex(n) for n in data))

            # Red tile
            elif data[6] == 0x15:
                self.gui.cam_field.SetLabel("Red tile")
                self.current_tile = 1
            # Green tile
            elif data[6] == 0x25:
                self.gui.cam_field.SetLabel("Green tile")
                self.current_tile = 2
            # No tile
            elif data[6] == 0x1a:
                self.gui.cam_field.SetLabel("No tile")
                self.current_tile = 0

        # Accelerometer data
        elif data[0] == 7:
            self.current_x = int((self.current_x * 0.5) + (MarioController.signed(data[4]) * 0.5))
            self.current_y = int((self.current_y * 0.5) + (MarioController.signed(data[5]) * 0.5))
            self.current_z = int((self.current_z * 0.5) + (MarioController.signed(data[6]) * 0.5))
            self.gui.accel_field.SetLabel(f"X: {self.current_x} | Y: {self.current_y} | Z: {self.current_z}")

    async def run(self):
        while True:
            self.is_connected = False
            self.gui.status_field.SetLabel("Status: Searching for Mario...")
            self.gui.cam_field.SetLabel("Tile: None")
            self.gui.accel_field.SetLabel("X: 0 | Y: 0 | Z: 0")
            self.gui.signal_field.SetLabel("Signal Strength: N/A")  # Reset RSSI label

            devices = await BleakScanner.discover()
            found_device = None

            # Find the Mario device and update RSSI
            for d in devices:
                if d.name and d.name.lower().startswith("lego mario"):  # Fixed error here
                    self.gui.status_field.SetLabel("Status: Found Mario!")
                    self.rssi = d.rssi  # Grab the RSSI value from the discovered device
                    self.gui.signal_field.SetLabel(f"Signal Strength: {self.rssi} dBm")  # Display the RSSI in the GUI
                    found_device = d
                    break

            if found_device:
                try:
                    # Only connect if not already connected
                    if not self.is_connected:
                        async with BleakClient(found_device.address) as client:
                            self.is_connected = await client.is_connected()
                            if self.is_connected:
                                self.gui.status_field.SetLabel("Status: Connected")
                                await client.start_notify(LEGO_CHARACTERISTIC_UUID, self.notification_handler)
                                await asyncio.sleep(0.1)
                                await client.write_gatt_char(LEGO_CHARACTERISTIC_UUID, SUBSCRIBE_IMU_COMMAND)
                                await asyncio.sleep(0.1)
                                await client.write_gatt_char(LEGO_CHARACTERISTIC_UUID, SUBSCRIBE_RGB_COMMAND)

                                while await client.is_connected():
                                    await self.process_keys()
                            else:
                                self.gui.status_field.SetLabel("Status: Connection Failed")
                except BleakError as e:
                    self.gui.status_field.SetLabel(f"Status: Error - {e}")

            # Wait before re-checking
            await asyncio.sleep(5)

# Run application
if __name__ == "__main__":
    app = WxAsyncApp()
    frm = MarioFrame()
    frm.Show()
    asyncio.run(app.MainLoop())
