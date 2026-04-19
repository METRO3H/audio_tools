import customtkinter as ctk


class LogPanel(ctk.CTkFrame):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build()

    def _build(self):
        self.textbox = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.textbox.pack(fill="both", expand=True, padx=8, pady=8)

    def append(self, text: str) -> None:
        self.textbox.configure(state="normal")
        self.textbox.insert("end", text + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def clear(self) -> None:
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")