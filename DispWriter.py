import hid
import time
import re

LIST_RE = re.compile(r"\[\s*(.*?)\s*\]")
BYTE_RE = re.compile(r"(0x[0-9A-Fa-f]+|\d+)")
COLOR_RE = re.compile(r"\$\$color:(fg|bg):([a-z]+)\$\$")

class DispWriter:
    def __init__(self, PID=None, VID=None, writeDelay=0.01):
        self.INIT_PATH = "init.txt"
        # I found that if writeDelay is shorter than 0.01 it gets glitchy
        self.write_delay = writeDelay if writeDelay > 0.01 else 0.01

        self.PID = PID
        self.VID = VID
        self.writing = False

        print("Initialized with PID: " + str(PID) + " and VID: " + str(VID))

        self.device = hid.device()
        self.device.open(self.VID, self.PID)
        count = self.send_init_from_file()

        print(f"Sent {count} init packets from {self.INIT_PATH}")

    def send_init_from_file(self) -> int:
        sent = 0
        with open(self.INIT_PATH, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                pkt = self.parse_write_line(line)
                if pkt is None:
                    continue
                self.device.write(pkt)
                sent += 1
                time.sleep(0.001)
        return sent

    def parse_write_line(self, line: str) -> list[int] | None:
        m = LIST_RE.search(line)
        if not m:
            return None
        body = m.group(1)
        bytes_out: list[int] = []
        for token in BYTE_RE.findall(body):
            val = int(token, 0)
            if not (0 <= val <= 255):
                raise ValueError(f"Byte out of range 0..255: {val}")
            bytes_out.append(val)
        return bytes_out

    def get_bg(self, seg) -> bool:
        has_bg = "bg" in seg and seg["bg"] not in (None, "")
        return seg["bg"] if has_bg else "black"

    def get_fg(self, seg) -> bool:
        has_fg ="fg" in seg and seg["fg"] not in (None, "")
        return  seg["fg"] if has_fg else "white"

    def fix_text_length(self, text):
        """
        Enforce a total display text length of exactly 336 characters.
        - If combined length > 336: truncate across blocks in order; later blocks become empty once the limit is reached.
        - If combined length < 336: pad spaces at the end of the last block.
        Operates in place and returns the modified list.
        """
        max_length = 336
        total_len = sum(len(block.get("text", "")) for block in text)

        # Truncate if longer than max_length
        if total_len > max_length:
            remaining = max_length
            for i, block in enumerate(text):
                s = block.get("text", "")
                if remaining <= 0:
                    # No room left: clear all further text
                    block["text"] = ""
                    continue

                if len(s) > remaining:
                    # Cut this block to the remaining space
                    block["text"] = s[:remaining]
                    remaining = 0
                else:
                    # Keep this block as-is and reduce remaining
                    remaining -= len(s)

            # At this point, any blocks after remaining==0 have already been cleared

        # Pad if shorter than max_length
        elif total_len < max_length:
            spaces_needed = max_length - total_len
            if text:
                text[-1]["text"] = text[-1].get("text", "") + (" " * spaces_needed)
            # If text is empty, there is no block to pad; leave as-is.

        # If exactly max_length, no change needed
        return text

    # gets fixed text length with color as hex array
    def get_payload_from_block(self, text):
        fg_lookup = {
            "orange": 0, "white": 1, "cyan": 2, "green": 3,
            "magenta": 4, "red": 5, "yellow": 6,
        }
        bg_lookup = {
            "black": 0, "green": 1, "gray": 2, "orange": 3, "purple": 4,
        }
        text = self.fix_text_length(text);
        payload = []

        for block in text:
            fg = self.get_fg(block)
            fg = fg if fg in fg_lookup else "white"
            bg = self.get_bg(block)
            bg = bg if bg in bg_lookup else "black"

            prefix_byte = 0x21 + 0x21 * fg_lookup[fg] + 0xC * bg_lookup[bg]

            text_bytes = block.get("text", "").encode("ascii", "replace")

            block_payload = []
            if text_bytes:
                # Use the per-character triplet with this block's prefix
                for b in text_bytes:
                    block_payload.extend([prefix_byte, 0x00, b])
            else:
                # For an empty block, fill 21 spaces with this block's prefix
                block_payload = [prefix_byte, 0x00, 0x20] * 21

            payload.extend(block_payload)

        # If there were no blocks at all, seed with 21 spaces using the default prefix
        if not payload:
            payload = [0x42, 0x00, 0x20] * 21
        return payload

    # gets payload split into 64 long package
    def text_to_hex_packet(self, text):
        print(text)
        payload = self.get_payload_from_block(text)

        lines = []
        i = 0
        while i < len(payload):
            chunk = payload[i:i+63]
            i += 63
            if len(chunk) < 63:
                # pad with full triplets when possible, then zeros
                pad_triplet = [0x42, 0x00, 0x20]
                while len(chunk) + len(pad_triplet) <= 63:
                    chunk.extend(pad_triplet)
                while len(chunk) < 63:
                    chunk.append(0x00)

            packet = [0xF2] + chunk  # 64 bytes total
            hex_bytes = ", ".join(f"0x{b:02x}" for b in packet)
            lines.append(f"[{hex_bytes}]")

        return lines

    def send_text_to_disp(self, text):
        if not self.writing:
            self.writing =  True
            for line in self.text_to_hex_packet(text):
                start = line.find('[') + 1
                end = line.find(']')
                byte_strs = line[start:end].split(',')
                pkt = [int(b.strip(), 16) for b in byte_strs]
                self.device.write(pkt)
                time.sleep(self.write_delay)
            self.writing = False
