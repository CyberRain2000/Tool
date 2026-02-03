"""Tiny GUI horror game built with tkinter."""

import random
import tkinter as tk


WINDOW_SIZE = "720x480"

SCENES = {
    "start": {
        "title": "The Abandoned Ward",
        "text": (
            "You wake up on a cold metal table. The lights flicker. "
            "A distant scream echoes through the halls."
        ),
        "options": [
            ("Search the room", "room"),
            ("Open the metal door", "hall"),
        ],
    },
    "room": {
        "title": "The Room",
        "text": (
            "The room smells of disinfectant and rust. A locked cabinet rattles. "
            "Something scratches inside the walls."
        ),
        "options": [
            ("Break the cabinet", "cabinet"),
            ("Hide under the table", "hide"),
        ],
    },
    "hall": {
        "title": "The Hallway",
        "text": (
            "The hallway stretches into darkness. A red EXIT sign flickers. "
            "Footsteps approach from the left."
        ),
        "options": [
            ("Run toward EXIT", "exit"),
            ("Slip into the left wing", "wing"),
        ],
    },
    "cabinet": {
        "title": "Cabinet",
        "text": (
            "The door snaps open. You find a cracked flashlight and a keycard."
        ),
        "options": [
            ("Take both and return", "room_return"),
        ],
    },
    "hide": {
        "title": "Under the Table",
        "text": (
            "You hold your breath. A shadow crawls by. The table shakes."
        ),
        "options": [
            ("Make a break for the hall", "hall"),
            ("Stay still", "caught"),
        ],
    },
    "exit": {
        "title": "Exit Door",
        "text": (
            "The exit door is chained shut. The chain hums with electricity."
        ),
        "options": [
            ("Force the chain", "shock"),
            ("Look for a control panel", "panel"),
        ],
    },
    "wing": {
        "title": "Left Wing",
        "text": (
            "The left wing is flooded. You hear splashing in the dark water."
        ),
        "options": [
            ("Wade through", "flood"),
            ("Back to the hall", "hall"),
        ],
    },
    "panel": {
        "title": "Control Panel",
        "text": (
            "A corroded panel asks for a keycard. A door behind you creaks."
        ),
        "options": [
            ("Use the keycard", "escape"),
            ("Run back", "hall"),
        ],
    },
    "room_return": {
        "title": "Back in the Room",
        "text": (
            "With the flashlight, you spot a vent leading to the control wing."
        ),
        "options": [
            ("Crawl into the vent", "panel"),
            ("Return to the hall", "hall"),
        ],
    },
    "flood": {
        "title": "Flooded Passage",
        "text": (
            "Cold water rises to your chest. Something grabs your ankle."
        ),
        "options": [
            ("Kick free", "hall"),
            ("Give in", "caught"),
        ],
    },
    "shock": {
        "title": "Electric Chain",
        "text": (
            "A jolt surges through you. Your vision fades to black."
        ),
        "options": [
            ("Restart", "start"),
        ],
    },
    "caught": {
        "title": "Caught",
        "text": (
            "Cold fingers wrap around your throat. The world goes silent."
        ),
        "options": [
            ("Restart", "start"),
        ],
    },
    "escape": {
        "title": "Escape",
        "text": (
            "The chain falls away. Night air rushes in. You stagger into freedom."
        ),
        "options": [
            ("Play again", "start"),
        ],
    },
}


class HorrorGame(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Night Ward: Escape")
        self.geometry(WINDOW_SIZE)
        self.resizable(False, False)
        self.configure(bg="#0d0d0f")

        self.current_scene = "start"
        self.has_keycard = False

        self.header = tk.Label(
            self,
            text="",
            font=("Helvetica", 20, "bold"),
            bg="#0d0d0f",
            fg="#e6e6e6",
        )
        self.header.pack(pady=(20, 10))

        self.story = tk.Label(
            self,
            text="",
            font=("Helvetica", 14),
            wraplength=640,
            justify="left",
            bg="#0d0d0f",
            fg="#cfc9c9",
        )
        self.story.pack(pady=(0, 20))

        self.status = tk.Label(
            self,
            text="",
            font=("Helvetica", 12, "italic"),
            bg="#0d0d0f",
            fg="#8f8f8f",
        )
        self.status.pack(pady=(0, 20))

        self.button_frame = tk.Frame(self, bg="#0d0d0f")
        self.button_frame.pack()

        self.refresh_scene()

    def refresh_scene(self) -> None:
        scene = SCENES[self.current_scene]
        self.header.configure(text=scene["title"])
        self.story.configure(text=scene["text"])
        self.update_status()

        for widget in self.button_frame.winfo_children():
            widget.destroy()

        for label, target in scene["options"]:
            button = tk.Button(
                self.button_frame,
                text=label,
                command=lambda next_scene=target: self.choose(next_scene),
                font=("Helvetica", 12, "bold"),
                bg="#1e1e24",
                fg="#f5f5f5",
                activebackground="#5b0f16",
                activeforeground="#ffffff",
                relief="flat",
                padx=18,
                pady=8,
                cursor="hand2",
            )
            button.pack(pady=6)

    def update_status(self) -> None:
        status_parts = ["Flashlight: On" if self.current_scene in {"cabinet", "room_return", "panel"} else "Flashlight: Off"]
        if self.has_keycard:
            status_parts.append("Keycard: Acquired")
        else:
            status_parts.append("Keycard: Missing")
        self.status.configure(text=" • ".join(status_parts))

    def choose(self, next_scene: str) -> None:
        if next_scene == "cabinet":
            self.has_keycard = True
        if next_scene == "panel" and not self.has_keycard:
            self.trigger_lockout()
            return
        if next_scene in {"caught", "shock"}:
            self.flash_red()
        self.current_scene = next_scene
        self.refresh_scene()

    def trigger_lockout(self) -> None:
        self.header.configure(text="Locked")
        self.story.configure(
            text=(
                "The panel flashes red. You need a keycard. A whisper says, "
                "'The room remembers.'"
            )
        )
        self.status.configure(text="Keycard: Missing")
        for widget in self.button_frame.winfo_children():
            widget.destroy()
        retry = tk.Button(
            self.button_frame,
            text="Back",
            command=lambda: self.choose("hall"),
            font=("Helvetica", 12, "bold"),
            bg="#1e1e24",
            fg="#f5f5f5",
            activebackground="#5b0f16",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
        )
        retry.pack(pady=6)

    def flash_red(self) -> None:
        original = self.cget("bg")
        self.configure(bg="#3b0a0a")
        self.after(200, lambda: self.configure(bg=original))


def main() -> None:
    random.seed()
    app = HorrorGame()
    app.mainloop()


if __name__ == "__main__":
    main()
