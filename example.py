from DispWriter import DispWriter

VID = 0x4098
PID = 0xBB35
WRITE_DELAY_S = 0.001

obj = DispWriter(PID, VID, WRITE_DELAY_S)
obj.send_text_to_disp([
    {"text":"This is some text", "bg":"black","fg":"white"},
    {"text":"This is some more text", "bg":"black","fg":"green"},
    {"text":"No formatting defaults to black and white"},
    {"text":"If total text is shorter than full display it gets padded with spaces"},
    {"text":"Too long it gets cut off at the end", "bg":"black","fg":"green"},
    ])
